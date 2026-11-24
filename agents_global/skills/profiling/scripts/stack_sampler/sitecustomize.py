"""Sample every Python thread's stack at a fixed wall-clock rate from inside the process, without py-spy or ptrace and
without editing the project: put this directory on PYTHONPATH.

For host-side time attribution where py-spy cannot attach (ptrace_scope = 1 on cluster nodes) or is not installed:
startup phases, a slow first step (JIT compiles, autotuning, cache loads, lazy communicator setup), checkpoint load
or save, data loader warm-up. A daemon thread calls sys._current_frames() every 1/STACK_SAMPLER_HZ seconds and
writes one line per thread per sample, so idle and blocked threads are sampled too (the leaf frame is the Python call
that blocks, e.g. `item` for a host sync or `wait` for a subprocess). Overhead: one frame walk per thread per sample
under the GIL, well under 1% of one core at the default 20 Hz.

Enabled only when STACK_SAMPLER_OUT is set, the process command line contains STACK_SAMPLER_MATCH (default
"prime_rl.trainer"), and $RANK (set by torchrun; the launcher has none and is skipped, set it by hand for a single
process) is in STACK_SAMPLER_RANKS (default "0"; "all" samples every rank). STACK_SAMPLER_HZ (default 20) sets the
rate, STACK_SAMPLER_SECONDS (default 0, no limit) stops sampling that many seconds after the process starts.

Output: $STACK_SAMPLER_OUT/stacks_rank<RANK>.txt, one line per thread per sample:
`<unix time>\t<thread name> (<thread id>)\t<frame>;<frame>;...`, outermost frame first, each frame
`function (file:line)`, flushed every second. Analyze with ../stack_timeline.py.
Shadows the interpreter's own sitecustomize (Ubuntu's only installs apport).
"""

import os
import sys

_ranks = os.environ.get("STACK_SAMPLER_RANKS", "0")
if (
    os.environ.get("STACK_SAMPLER_OUT")
    and os.environ.get("STACK_SAMPLER_MATCH", "prime_rl.trainer") in " ".join(getattr(sys, "orig_argv", sys.argv))
    and os.environ.get("RANK") is not None
    and (_ranks == "all" or os.environ["RANK"] in _ranks.split(","))
):
    import threading
    import time

    def _frames(frame):
        stack = []
        while frame is not None:
            code = frame.f_code
            stack.append(f"{code.co_name} ({code.co_filename}:{frame.f_lineno})")
            frame = frame.f_back
        return ";".join(reversed(stack))

    def _sample_forever(path, period, deadline):
        own = threading.get_ident()
        last_flush = time.monotonic()
        with open(path, "a", buffering=1 << 20) as out:
            while deadline is None or time.monotonic() < deadline:
                now = time.time()
                names = {thread.ident: thread.name for thread in threading.enumerate()}
                for ident, frame in sys._current_frames().items():
                    if ident != own:
                        out.write(f"{now:.3f}\t{names.get(ident, 'unknown')} ({ident})\t{_frames(frame)}\n")
                del frame
                if time.monotonic() - last_flush >= 1.0:
                    out.flush()
                    last_flush = time.monotonic()
                time.sleep(period)

    os.makedirs(os.environ["STACK_SAMPLER_OUT"], exist_ok=True)
    _seconds = float(os.environ.get("STACK_SAMPLER_SECONDS", "0"))
    threading.Thread(
        target=_sample_forever,
        args=(
            os.path.join(os.environ["STACK_SAMPLER_OUT"], f"stacks_rank{os.environ['RANK']}.txt"),
            1.0 / float(os.environ.get("STACK_SAMPLER_HZ", "20")),
            time.monotonic() + _seconds if _seconds > 0 else None,
        ),
        name="stack_sampler",
        daemon=True,
    ).start()
