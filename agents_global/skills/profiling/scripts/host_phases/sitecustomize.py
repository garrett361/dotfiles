"""Time named Python functions in every rank from inside the process, without editing the project: put this directory
on PYTHONPATH. Answers "which host phase holds each rank, and which rank is last", for any CPU-side phase (checkpoint
load or save, startup, data loading) at call granularity instead of sampling.

HOST_PHASES (comma-separated `module:Qualified.name`) are timed per call: each call writes one event line. Use it for
calls that happen a few thousand times or fewer (planning, collectives, per-file reads). HOST_PHASES_AGG targets are
summed per thread instead (calls, seconds, and bytes when the call returns bytes or an int count such as `readinto`),
for hot calls such as `torch.load` per tensor or a file view's `read`. A target is wrapped when its module is first
imported (or at startup if already imported); a missing target is reported once on stderr and skipped. Builtins that
are looked up as attributes at call time can be wrapped too (e.g. `gc:collect`, `torch:load`,
`torch:Tensor.copy_`).

Enabled only when HOST_PHASES_OUT is set, the command line contains HOST_PHASES_MATCH (default "prime_rl.trainer"),
and $RANK is in HOST_PHASES_RANKS (default "all"). If STACK_SAMPLER_OUT is also set, the sibling stack_sampler
sitecustomize is started too, since only one sitecustomize is imported per interpreter; to add ../gil_probe, put its
directory on PYTHONPATH instead of this one (it starts this one, which starts the stack sampler).

Output: $HOST_PHASES_OUT/phases_rank<RANK>.jsonl. A first line `{"host": hostname, "pid": pid}`; event lines `{"n": name, "t0": unix, "t1": unix, "th": thread}`; a
`{"agg": {name: {thread: [calls, seconds, bytes]}}, "t": unix}` snapshot after every event and at exit (the last one
wins). Analyze with ../host_phases.py.
"""

import os
import sys


def _start():
    import atexit
    import functools
    import importlib
    import importlib.abc
    import json
    import socket
    import threading
    import time

    rank = os.environ["RANK"]
    dumps, now, clock = json.dumps, time.time, time.perf_counter
    inside = threading.local()
    out = open(os.path.join(os.environ["HOST_PHASES_OUT"], f"phases_rank{rank}.jsonl"), "a", buffering=1)
    lock = threading.Lock()
    agg = {}

    def parse(var):
        targets = {}
        for spec in filter(None, (s.strip() for s in os.environ.get(var, "").split(","))):
            module, qualname = spec.split(":")
            targets.setdefault(module, []).append(qualname)
        return targets

    events, aggregated = parse("HOST_PHASES"), parse("HOST_PHASES_AGG")
    out.write(json.dumps({"host": socket.gethostname(), "pid": os.getpid()}) + "\n")

    def write(record):
        inside.busy = True
        try:
            with lock:
                out.write(dumps(record) + "\n")
        finally:
            inside.busy = False

    def snapshot():
        write({"agg": agg, "t": now()})

    def timed_event(fn, name):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if getattr(inside, "busy", False):
                return fn(*args, **kwargs)
            t0 = now()
            try:
                return fn(*args, **kwargs)
            finally:
                write({"n": name, "t0": t0, "t1": now(), "th": threading.current_thread().name})
                snapshot()

        return wrapper

    def timed_agg(fn, name):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if getattr(inside, "busy", False):
                return fn(*args, **kwargs)
            t0 = clock()
            result = fn(*args, **kwargs)
            seconds = clock() - t0
            size = len(result) if isinstance(result, (bytes, bytearray, memoryview)) else 0
            if isinstance(result, int) and not isinstance(result, bool):
                size = result
            with lock:
                entry = agg.setdefault(name, {}).setdefault(threading.current_thread().name, [0, 0.0, 0])
                entry[0] += 1
                entry[1] += seconds
                entry[2] += size
            return result

        return wrapper

    def patch(module_name, qualnames, wrap):
        module = sys.modules[module_name]
        for qualname in qualnames:
            *path, attr = qualname.split(".")
            owner = module
            try:
                for part in path:
                    owner = getattr(owner, part)
                original = owner.__dict__[attr] if attr in getattr(owner, "__dict__", {}) else getattr(owner, attr)
            except (AttributeError, KeyError):
                print(f"host_phases: no {module_name}:{qualname}", file=sys.stderr)
                continue
            name = f"{module_name}:{qualname}"
            if isinstance(original, staticmethod):
                wrapped = staticmethod(wrap(original.__func__, name))
            elif isinstance(original, classmethod):
                wrapped = classmethod(wrap(original.__func__, name))
            else:
                wrapped = wrap(original, name)
            try:
                setattr(owner, attr, wrapped)
            except TypeError as error:
                print(f"host_phases: cannot wrap {name}: {error}", file=sys.stderr)

    pending = {module: [] for module in {*events, *aggregated}}
    for module, qualnames in events.items():
        pending[module].append((qualnames, timed_event))
    for module, qualnames in aggregated.items():
        pending[module].append((qualnames, timed_agg))

    def apply(module_name):
        for qualnames, wrap in pending.pop(module_name, []):
            patch(module_name, qualnames, wrap)

    class PatchOnImport(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname not in pending:
                return None
            for finder in sys.meta_path:
                if finder is self:
                    continue
                spec = finder.find_spec(fullname, path, target) if hasattr(finder, "find_spec") else None
                if spec is not None and spec.loader is not None:
                    exec_module = spec.loader.exec_module

                    def exec_and_patch(module, exec_module=exec_module):
                        exec_module(module)
                        apply(fullname)

                    spec.loader.exec_module = exec_and_patch
                    return spec
            return None

    for module_name in [m for m in pending if m in sys.modules]:
        apply(module_name)
    sys.meta_path.insert(0, PatchOnImport())
    atexit.register(snapshot)


if (
    os.environ.get("HOST_PHASES_OUT")
    and os.environ.get("HOST_PHASES_MATCH", "prime_rl.trainer") in " ".join(getattr(sys, "orig_argv", sys.argv))
    and os.environ.get("RANK") is not None
    and (
        os.environ.get("HOST_PHASES_RANKS", "all") == "all"
        or os.environ["RANK"] in os.environ["HOST_PHASES_RANKS"].split(",")
    )
):
    os.makedirs(os.environ["HOST_PHASES_OUT"], exist_ok=True)
    _start()

if os.environ.get("STACK_SAMPLER_OUT"):
    import runpy

    runpy.run_path(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stack_sampler", "sitecustomize.py")
    )
