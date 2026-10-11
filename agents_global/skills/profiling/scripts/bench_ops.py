"""Time GPU callables with triton.testing.do_bench and print a markdown table.

usage: python bench_ops.py CASES.py [--only SUBSTR] [--warmup MS] [--rep MS] [--csv OUT] [--memory]
       [--trace DIR [--trace-iters N]]

CASES.py defines `cases()`, returning a list of (case_name, {label: zero-arg callable}). Every callable in a
case is timed with do_bench (CUDA events, L2 flushed between reps) and reported as median, p20 and p80 in ms.
With --memory, each callable also runs once on its own after timing, and the table adds its peak allocated
memory above what was allocated just before the call (MiB): the transient cost of the op, inputs excluded.
With --trace DIR, each callable is also run --trace-iters times (after timing) under torch.profiler, and the
chrome trace is written to DIR/<case>__<label>.json.gz for a per-kernel breakdown with `top_kernels.py
--whole-trace` (divide totals by --trace-iters for per-call numbers).
Build inputs inside `cases()` so they are allocated once. Run it with the interpreter of the project under
test (e.g. `uv run --no-sync python bench_ops.py ...`) so its imports resolve. Check numerics separately before
timing: this script only times.
"""

import argparse
import csv
import importlib.util
import sys


def load_cases(path):
    spec = importlib.util.spec_from_file_location("bench_cases", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_cases"] = module
    spec.loader.exec_module(module)
    return module.cases()


def write_trace(fn, trace_dir, name, iters):
    import os
    import re

    import torch
    from torch.profiler import ProfilerActivity, profile

    os.makedirs(trace_dir, exist_ok=True)
    torch.cuda.synchronize()
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA], record_shapes=True) as prof:
        for _ in range(iters):
            fn()
        torch.cuda.synchronize()
    safe_name = re.sub(r"[^A-Za-z0-9_.=+-]+", "_", name)
    prof.export_chrome_trace(os.path.join(trace_dir, f"{safe_name}.json.gz"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases_file")
    parser.add_argument("--only", default=None, help="keep cases whose name contains this substring")
    parser.add_argument("--warmup", type=int, default=25)
    parser.add_argument("--rep", type=int, default=200)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--memory", action="store_true", help="also report peak MiB above the pre-call baseline")
    parser.add_argument("--trace", default=None, help="directory for one torch.profiler chrome trace per callable")
    parser.add_argument("--trace-iters", type=int, default=10)
    args = parser.parse_args()

    import torch
    import triton

    rows = []
    for case_name, fns in load_cases(args.cases_file):
        if args.only and args.only not in case_name:
            continue
        for label, fn in fns.items():
            p50, p20, p80 = triton.testing.do_bench(fn, warmup=args.warmup, rep=args.rep, quantiles=[0.5, 0.2, 0.8])
            row = [case_name, label, p50, p20, p80]
            if args.memory:
                torch.cuda.synchronize()
                baseline = torch.cuda.memory_allocated()
                torch.cuda.reset_peak_memory_stats()
                fn()
                torch.cuda.synchronize()
                row.append((torch.cuda.max_memory_allocated() - baseline) / 2**20)
            rows.append(tuple(row))
            if args.trace:
                write_trace(fn, args.trace, f"{case_name}__{label}", args.trace_iters)
        torch.cuda.empty_cache()

    print(f"device: {torch.cuda.get_device_name()}, do_bench warmup {args.warmup} ms, rep {args.rep} ms\n")
    memory_header = " peak MiB above baseline |" if args.memory else ""
    print(f"| case | label | median ms | p20 ms | p80 ms |{memory_header}")
    print("|---|---|---|---|---|" + ("---|" if args.memory else ""))
    for case_name, label, p50, p20, p80, *memory in rows:
        memory_cell = f" {memory[0]:.1f} |" if memory else ""
        print(f"| {case_name} | {label} | {p50:.3f} | {p20:.3f} | {p80:.3f} |{memory_cell}")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["case", "label", "median_ms", "p20_ms", "p80_ms"] + (["peak_mib"] if args.memory else []))
            writer.writerows(rows)


if __name__ == "__main__":
    main()
