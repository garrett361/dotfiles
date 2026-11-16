"""Record the CUDA caching allocator's history (every alloc and free with its Python stack) and dump it as JSON at
exit, without editing the project: put this directory on PYTHONPATH. Read the dump with `memory_peak.py`.

Enabled only when MEMORY_HISTORY_OUT is set, the process command line contains MEMORY_HISTORY_MATCH (default
"prime_rl"), and $RANK (set by torchrun; set it by hand for a single process) is in MEMORY_HISTORY_RANKS (default "0").
Recording starts at the MEMORY_HISTORY_START_CALL-th call (default 1) of MEMORY_HISTORY_HOOK (default
"torch.cuda.reset_peak_memory_stats", which training loops and benches call where they start measuring a peak), so
CUDA is initialized and the window matches the peak the run reports; MEMORY_HISTORY_MAX_ENTRIES (default 2000000)
bounds the ring buffer. At exit, $MEMORY_HISTORY_OUT/memory_rank<RANK>.json holds `torch.cuda.memory._snapshot()`
(segments, blocks and `device_traces`) plus the hook call at which recording started and `memory_allocated()` then and
at the dump, and `max_memory_allocated()` read just before each later hook call and at the dump (when the hook is a
peak reset, the peak of each interval between calls, e.g. each training step). JSON, never pickle. Recording
python stacks slows allocation-heavy steps; time nothing in a recorded run.
Shadows the interpreter's own sitecustomize (Ubuntu's only installs apport).
"""

import os
import sys

if (
    os.environ.get("MEMORY_HISTORY_OUT")
    and os.environ.get("MEMORY_HISTORY_MATCH", "prime_rl") in " ".join(getattr(sys, "orig_argv", sys.argv))
    and os.environ.get("RANK", "0") in os.environ.get("MEMORY_HISTORY_RANKS", "0").split(",")
):
    import atexit
    import importlib
    import json

    import torch

    _out_dir = os.environ["MEMORY_HISTORY_OUT"]
    _start_call = int(os.environ.get("MEMORY_HISTORY_START_CALL", "1"))
    _max_entries = int(os.environ.get("MEMORY_HISTORY_MAX_ENTRIES", "2000000"))
    _module_name, _attr = os.environ.get("MEMORY_HISTORY_HOOK", "torch.cuda.reset_peak_memory_stats").rsplit(".", 1)
    _module = importlib.import_module(_module_name)
    _original = getattr(_module, _attr)
    _calls = [0]
    _recording = [False]
    _start_allocated = [None]

    _peaks_before_call = []

    def _hooked(*args, **kwargs):
        if _recording[0]:
            _peaks_before_call.append(torch.cuda.max_memory_allocated())
        result = _original(*args, **kwargs)
        _calls[0] += 1
        if _calls[0] == _start_call and not _recording[0]:
            torch.cuda.memory._record_memory_history(
                enabled="all", context="all", stacks="python", max_entries=_max_entries
            )
            _recording[0] = True
            _start_allocated[0] = torch.cuda.memory_allocated()
        return result

    setattr(_module, _attr, _hooked)

    def _dump():
        if not _recording[0]:
            return
        snapshot = torch.cuda.memory._snapshot()
        snapshot["memory_history_hook"] = {
            "hook": f"{_module_name}.{_attr}",
            "start_call": _start_call,
            "start_allocated": _start_allocated[0],
            "end_allocated": torch.cuda.memory_allocated(),
            "peaks_before_call": _peaks_before_call,
            "peak_at_dump": torch.cuda.max_memory_allocated(),
        }
        os.makedirs(_out_dir, exist_ok=True)
        path = os.path.join(_out_dir, f"memory_rank{os.environ.get('RANK', '0')}.json")
        with open(path, "w") as f:
            json.dump(snapshot, f, default=str)

    atexit.register(_dump)
