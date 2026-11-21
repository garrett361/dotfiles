"""Log the host-side arguments of one Python function on every call, without editing the project: put this directory
on PYTHONPATH.

Enabled only when ARG_LOG_OUT and ARG_LOG_TARGET ("package.module:function") are set and the process command line
contains ARG_LOG_MATCH (default "prime_rl.trainer"). When the target module finishes executing, its function is
replaced by a wrapper, so later `from module import function` statements bind the wrapper. Each call made outside
torch.compile tracing appends one JSON line to $ARG_LOG_OUT/args_rank<RANK>.jsonl: the call index, wall time in ns,
and every positional and keyword argument, with CPU tensors of at most ARG_LOG_MAX_NUMEL (default 65536) elements
and ints, floats, strings and lists of them written as values, and anything else as its type and shape. Device
tensors are never read, so the hook adds no host sync.

Example: per-rank document lengths per micro-batch in prime-rl, from the host `seq_lens` its train loop passes:
  PYTHONPATH=<this dir> ARG_LOG_OUT=<dir> ARG_LOG_TARGET=prime_rl.utils.sequence:get_cu_seqlens_from_seq_lens ...
Shadows the interpreter's own sitecustomize (Ubuntu's only installs apport).
"""

import os
import sys

if (
    os.environ.get("ARG_LOG_OUT")
    and os.environ.get("ARG_LOG_TARGET")
    and os.environ.get("ARG_LOG_MATCH", "prime_rl.trainer") in " ".join(getattr(sys, "orig_argv", sys.argv))
):
    import functools
    import importlib.abc
    import importlib.util
    import json
    import time

    _module_name, _function_name = os.environ["ARG_LOG_TARGET"].split(":")
    _max_numel = int(os.environ.get("ARG_LOG_MAX_NUMEL", "65536"))
    os.makedirs(os.environ["ARG_LOG_OUT"], exist_ok=True)
    _path = os.path.join(os.environ["ARG_LOG_OUT"], f"args_rank{os.environ.get('RANK', '0')}.jsonl")
    _calls = [0]

    def _value(v):
        if isinstance(v, (bool, int, float, str)) or v is None:
            return v
        if isinstance(v, (list, tuple)) and all(isinstance(x, (bool, int, float, str)) for x in v):
            return list(v)
        torch = sys.modules.get("torch")
        if torch is not None and isinstance(v, torch.Tensor):
            if v.device.type == "cpu" and v.numel() <= _max_numel:
                return v.tolist()
            return {"tensor": str(v.dtype), "device": str(v.device), "shape": list(v.shape)}
        return {"type": type(v).__name__}

    def _wrap(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            torch = sys.modules.get("torch")
            if torch is None or not torch.compiler.is_compiling():
                record = {"call": _calls[0], "t_ns": time.time_ns(), "args": [_value(a) for a in args],
                          "kwargs": {k: _value(v) for k, v in kwargs.items()}}
                _calls[0] += 1
                with open(_path, "a") as out:
                    out.write(json.dumps(record) + "\n")
            return function(*args, **kwargs)

        return wrapper

    class _PatchLoader(importlib.abc.Loader):
        def __init__(self, loader):
            self._loader = loader

        def create_module(self, spec):
            return self._loader.create_module(spec)

        def exec_module(self, module):
            self._loader.exec_module(module)
            setattr(module, _function_name, _wrap(getattr(module, _function_name)))

    class _PatchFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != _module_name:
                return None
            sys.meta_path.remove(self)
            try:
                spec = importlib.util.find_spec(name)
            finally:
                sys.meta_path.insert(0, self)
            if spec is not None and spec.loader is not None:
                spec.loader = _PatchLoader(spec.loader)
            return spec

    sys.meta_path.insert(0, _PatchFinder())
