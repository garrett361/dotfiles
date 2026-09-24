"""Record a Python stack for every CUDA host sync, without editing the project: put this directory on PYTHONPATH.

Enabled only when SYNC_STACKS_OUT is set, the process command line contains SYNC_STACKS_MATCH (default
"prime_rl.trainer"), and $RANK (set by torchrun, so the launcher is skipped; set it by hand for a single
process) is in SYNC_STACKS_RANKS (default "0"). Hooks go in at the first call of
SYNC_STACKS_STEP_HOOK (default "torch.cuda.reset_peak_memory_stats", called once at the top of each prime-rl
training step), so CUDA is already initialized; each call increments the recorded step and flushes the records
buffered in memory (stacks come from a frame walk without source lookup, to keep the per-sync cost low).

Two sources, one JSON line per sync in $SYNC_STACKS_OUT/syncs_rank<RANK>.jsonl:
- "warn" (default, SYNC_STACKS_WARN=1): torch.cuda.set_sync_debug_mode("warn") warnings, recorded as the op
  returns. Misses Event.synchronize and torch.cuda.synchronize. Warnings raised inside C++ autograd nodes are
  replayed on the main thread after backward, so their stack ends at `.backward()`.
- "stream"/"event"/"device" (opt-in, SYNC_STACKS_CALLBACKS=1): torch's GPU-trace sync callbacks (the CUDA sanitizer
  hooks), fired in the syncing thread before the blocking call; they also cover event and device syncs.
  Activating GPU trace calls into Python on every allocation and event, and it crashed prime-rl's first backward
  under activation checkpointing (SystemError from the trace hook inside torch.utils.checkpoint's unpack_hook), so
  use it only without activation checkpointing.
Records made in the autograd thread carry the running autograd node as "node" (e.g. IndexBackward0).
Shadows the interpreter's own sitecustomize (Ubuntu's only installs apport).
"""

import os
import sys

if (
    os.environ.get("SYNC_STACKS_OUT")
    and os.environ.get("SYNC_STACKS_MATCH", "prime_rl.trainer") in " ".join(getattr(sys, "orig_argv", sys.argv))
    and os.environ.get("RANK") in os.environ.get("SYNC_STACKS_RANKS", "0").split(",")
):
    import atexit
    import importlib
    import json
    import threading
    import time
    import warnings

    import torch

    _out = open(os.path.join(os.environ["SYNC_STACKS_OUT"], f"syncs_rank{os.environ['RANK']}.jsonl"), "a")
    _pending = []
    _step = [0]
    _skip = (__file__, os.sep + "warnings.py", os.path.join("torch", "_utils.py"))

    def _record(source, detail=""):
        t_ns = time.time_ns()
        stack, frame = [], sys._getframe(1)
        while frame is not None:
            if not frame.f_code.co_filename.endswith(_skip):
                stack.append([frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name])
            frame = frame.f_back
        node = torch._C._current_autograd_node() if threading.current_thread() is not threading.main_thread() else None
        _pending.append({"step": _step[0], "t_ns": t_ns, "tid": threading.get_native_id(),
                         "thread": threading.current_thread().name, "source": source, "detail": detail,
                         "node": node.name() if node is not None else None, "stack": stack[::-1]})

    def _flush():
        records = _pending[:]
        del _pending[: len(records)]
        _out.write("".join(json.dumps(r) + "\n" for r in records))
        _out.flush()

    atexit.register(_flush)

    _orig_showwarning = warnings.showwarning

    def _showwarning(message, category, filename, lineno, file=None, line=None):
        if "called a synchronizing CUDA operation" in str(message):
            _record("warn", f"{filename}:{lineno}")
        else:
            _orig_showwarning(message, category, filename, lineno, file, line)

    def _install():
        if os.environ.get("SYNC_STACKS_CALLBACKS", "0") == "1":
            import torch.cuda._gpu_trace as gpu_trace

            torch._C._activate_gpu_trace()
            gpu_trace.register_callback_for_stream_synchronization(lambda stream: _record("stream"))
            gpu_trace.register_callback_for_event_synchronization(lambda event: _record("event"))
            gpu_trace.register_callback_for_device_synchronization(lambda: _record("device"))
        if os.environ.get("SYNC_STACKS_WARN", "1") == "1":
            warnings.showwarning = _showwarning
            torch.cuda.set_sync_debug_mode("warn")

    _hook_path = os.environ.get("SYNC_STACKS_STEP_HOOK", "torch.cuda.reset_peak_memory_stats")
    _mod_name, _attr = _hook_path.rsplit(".", 1)
    _mod = importlib.import_module(_mod_name)
    _orig_hook = getattr(_mod, _attr)

    def _step_hook(*args, **kwargs):
        if _step[0] == 0:
            _install()
        _flush()
        _step[0] += 1
        warnings.filterwarnings("always", message=".*called a synchronizing CUDA operation")
        return _orig_hook(*args, **kwargs)

    setattr(_mod, _attr, _step_hook)
