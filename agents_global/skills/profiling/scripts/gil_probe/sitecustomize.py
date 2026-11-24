"""Measure how long a Python process's threads wait for the GIL, and every garbage collection, from inside the process
without editing the project: put this directory on PYTHONPATH.

Answers "is a background thread (an async checkpoint writer, a metrics or data thread) starving the training thread of
the GIL, when, and by how much", and "does a GC pause line up with a stall". A daemon thread sleeps 1 ms in a loop and
measures how late it wakes: a thread that wants the GIL waits up to the switch interval (5 ms) behind a holder that
releases it on schedule, and much longer behind one stuck in a C call that keeps it (a tokenizer save, a long pickle).
Each window of GIL_PROBE_WINDOW seconds (default 1) whose longest wake-up delay exceeds GIL_PROBE_MS (default 20) is
written as one line; quiet windows are not. The probe costs about 1000 wake-ups per second, a few percent of one core;
set GIL_PROBE_MS high to keep the files small, not to save time. gc.callbacks records every collection with its
generation, duration and thread, automatic or explicit. To name the thread that holds the GIL in a flagged window, run
`py-spy record --gil --threads` over it and summarize with ../pyspy_frames.py.

Enabled only when GIL_PROBE_OUT is set, the process command line contains GIL_PROBE_MATCH (default "prime_rl.trainer",
which leaves out data loader workers that inherit the environment), and $RANK is in GIL_PROBE_RANKS (default "all").
Output: $GIL_PROBE_OUT/gil_rank<RANK>.jsonl, lines `{"gil": [t0, t1], "max_ms": .., "late_s": .., "late": n}` (late_s
sums each wake-up's delay beyond 1 ms over the wake-ups more than 2 ms late; late counts them) and `{"gc": generation,
"t0": .., "t1": .., "th": thread, "collected": n}`. Analyze with ../gil_probe.py. If HOST_PHASES_OUT or STACK_SAMPLER_OUT is
set, the sibling host_phases or stack_sampler sitecustomize starts too, since only one sitecustomize is imported per
interpreter.
"""

import os
import sys


def _start():
    import gc
    import json
    import threading
    import time

    out = open(os.path.join(os.environ["GIL_PROBE_OUT"], f"gil_rank{os.environ['RANK']}.jsonl"), "a", buffering=1)
    lock = threading.Lock()
    threshold = float(os.environ.get("GIL_PROBE_MS", "20")) / 1e3
    window = float(os.environ.get("GIL_PROBE_WINDOW", "1"))

    def write(record):
        with lock:
            out.write(json.dumps(record) + "\n")

    collection = {}

    def on_gc(phase, info):
        if phase == "start":
            collection[threading.get_ident()] = time.time()
            return
        t0 = collection.pop(threading.get_ident(), None)
        if t0 is not None:
            write(
                {
                    "gc": info["generation"],
                    "t0": t0,
                    "t1": time.time(),
                    "th": threading.current_thread().name,
                    "collected": info["collected"],
                }
            )

    def probe():
        start = last = time.perf_counter()
        wall = time.time()
        worst = late_s = 0.0
        late = 0
        while True:
            time.sleep(0.001)
            now = time.perf_counter()
            gap = now - last
            last = now
            worst = max(worst, gap)
            if gap > 0.002:
                late_s += gap - 0.001
                late += 1
            if now - start >= window:
                if worst > threshold:
                    write({"gil": [wall, wall + now - start], "max_ms": worst * 1e3, "late_s": late_s, "late": late})
                start, wall = now, time.time()
                worst = late_s = 0.0
                late = 0

    gc.callbacks.append(on_gc)
    threading.Thread(target=probe, daemon=True, name="gil-probe").start()


_ranks = os.environ.get("GIL_PROBE_RANKS", "all")
if (
    os.environ.get("GIL_PROBE_OUT")
    and os.environ.get("GIL_PROBE_MATCH", "prime_rl.trainer") in " ".join(getattr(sys, "orig_argv", sys.argv))
    and os.environ.get("RANK") is not None
    and (_ranks == "all" or os.environ["RANK"] in _ranks.split(","))
):
    os.makedirs(os.environ["GIL_PROBE_OUT"], exist_ok=True)
    _start()

for _variable, _sibling in (("HOST_PHASES_OUT", "host_phases"), ("STACK_SAMPLER_OUT", "stack_sampler")):
    if os.environ.get(_variable):
        import runpy

        runpy.run_path(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _sibling, "sitecustomize.py")
        )
        break
