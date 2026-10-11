"""Time GPU callables with triton.testing.do_bench and print a markdown table.

usage: python bench_ops.py CASES.py [--only SUBSTR] [--warmup MS] [--rep MS] [--csv OUT] [--memory] [--check]
       [--cudagraph] [--trace DIR [--trace-iters N]]

CASES.py defines `cases()`, returning a list of (case_name, {label: zero-arg callable}). Every callable in a
case is timed with do_bench (CUDA events, L2 flushed between reps) and reported as median, p20 and p80 in ms,
plus the case's first label's median divided by this one's (above 1x means faster than the first label, so put
the reference first). A callable that raises is listed as failed after the table, the others still run, and the
exit code is 1.
With --memory, each callable also runs once on its own after timing, and the table adds its peak allocated
memory above what was allocated just before the call (MiB): the transient cost of the op, inputs excluded.
With --check, each callable runs once before timing and the tensors in its return value (any nesting of tuples,
lists and dicts) are compared with the first label's: shapes, max abs diff, and pass/FAIL under
torch.testing.assert_close's default tolerances for the dtype. Return gradients too when timing a backward.
With --cudagraph, timing uses do_bench_cudagraph instead: many calls replayed from one CUDA graph, no L2 flush,
no per-call event overhead (do_bench adds about 3 us per call, which dominates ops under ~20 us); p20/p80 then
come from only 10 replays. The callable must be capturable (no host syncs).
With --trace DIR, each callable is also run --trace-iters times (after timing) under torch.profiler, and the
chrome trace is written to DIR/<case>__<label>.json.gz for a per-kernel breakdown with `top_kernels.py
--whole-trace` (divide totals by --trace-iters for per-call numbers).
Build inputs inside `cases()` so they are allocated once. Keep CASES.py in the investigation root and list it in
NOTES.md: it is an input, like a config. Run it with the interpreter of the project under test (e.g. `uv run
--no-sync python bench_ops.py ...`) so its imports resolve.

Example CASES.py, forward and backward timed together (a callable may return its outputs for --check):
  def cases():
      x = torch.randn(4096, 4096, device="cuda", dtype=torch.bfloat16, requires_grad=True)
      dy = torch.randn_like(x)
      def fwd_bwd(impl):
          def run():
              x.grad = None
              y = impl(x)
              y.backward(dy)
              return y, x.grad
          return run
      return [("gelu 4096x4096 bf16 fwd+bwd", {"eager": fwd_bwd(F.gelu), "compiled": fwd_bwd(torch.compile(F.gelu))})]
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


def output_tensors(output):
    import torch
    from torch.utils._pytree import tree_leaves

    return [leaf.detach().clone() for leaf in tree_leaves(output) if isinstance(leaf, torch.Tensor)]


def compare_outputs(reference, output):
    import torch

    if len(reference) != len(output) or any(r.shape != o.shape for r, o in zip(reference, output)):
        return f"shape mismatch: {[tuple(t.shape) for t in reference]} vs {[tuple(t.shape) for t in output]}"
    if not reference:
        return "no tensor outputs"
    max_diff = max(
        ((r.double() - o.double()).abs().max().item() if r.numel() else 0.0) for r, o in zip(reference, output)
    )
    try:
        for r, o in zip(reference, output):
            torch.testing.assert_close(o, r, equal_nan=True)
    except AssertionError:
        return f"FAIL, max abs diff {max_diff:.3g}"
    return f"ok, max abs diff {max_diff:.3g}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases_file")
    parser.add_argument("--only", default=None, help="keep cases whose name contains this substring")
    parser.add_argument("--warmup", type=int, default=25)
    parser.add_argument("--rep", type=int, default=200)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--memory", action="store_true", help="also report peak MiB above the pre-call baseline")
    parser.add_argument("--check", action="store_true", help="compare each output with the case's first label")
    parser.add_argument("--cudagraph", action="store_true", help="time with do_bench_cudagraph (for ops under ~20 us)")
    parser.add_argument("--trace", default=None, help="directory for one torch.profiler chrome trace per callable")
    parser.add_argument("--trace-iters", type=int, default=10)
    args = parser.parse_args()

    import torch
    import triton

    rows = []
    checks = {}
    failures = []
    for case_name, fns in load_cases(args.cases_file):
        if args.only and args.only not in case_name:
            continue
        reference = None
        for label, fn in fns.items():
            try:
                if args.check:
                    output = output_tensors(fn())
                    if reference is None:
                        reference = output
                        checks[case_name, label] = "reference"
                    else:
                        checks[case_name, label] = compare_outputs(reference, output)
                    del output
                if args.cudagraph:
                    p50, p20, p80 = triton.testing.do_bench_cudagraph(fn, rep=args.rep, quantiles=[0.5, 0.2, 0.8])
                else:
                    p50, p20, p80 = triton.testing.do_bench(
                        fn, warmup=args.warmup, rep=args.rep, quantiles=[0.5, 0.2, 0.8]
                    )
                row = [case_name, label, p50, p20, p80]
                if args.memory:
                    torch.cuda.synchronize()
                    baseline = torch.cuda.memory_allocated()
                    torch.cuda.reset_peak_memory_stats()
                    fn()
                    torch.cuda.synchronize()
                    row.append((torch.cuda.max_memory_allocated() - baseline) / 2**20)
                if args.trace:
                    write_trace(fn, args.trace, f"{case_name}__{label}", args.trace_iters)
            except Exception as error:  # noqa: BLE001
                message = str(error).splitlines()[0] if str(error) else ""
                failures.append(f"{case_name} | {label}: {type(error).__name__}: {message}")
                print(f"failed: {failures[-1]}", file=sys.stderr)
                continue
            rows.append(tuple(row))
        del reference
        torch.cuda.empty_cache()

    timer = (
        f"do_bench_cudagraph rep {args.rep} ms"
        if args.cudagraph
        else f"do_bench warmup {args.warmup} ms, rep {args.rep} ms"
    )
    print(f"device: {torch.cuda.get_device_name()}, {timer}\n")
    memory_header = " peak MiB above baseline |" if args.memory else ""
    check_header = " check vs first label |" if args.check else ""
    print(f"| case | label | median ms | p20 ms | p80 ms | first label / this |{memory_header}{check_header}")
    print("|---|---|---|---|---|---|" + ("---|" if args.memory else "") + ("---|" if args.check else ""))
    first_median = {}
    for case_name, label, p50, p20, p80, *memory in rows:
        speedup = first_median.setdefault(case_name, p50) / p50
        memory_cell = f" {memory[0]:.1f} |" if memory else ""
        check_cell = f" {checks.get((case_name, label), '')} |" if args.check else ""
        print(
            f"| {case_name} | {label} | {p50:.4f} | {p20:.4f} | {p80:.4f} | {speedup:.2f}x |{memory_cell}{check_cell}"
        )
    if failures:
        print("\n" + "\n".join(f"failed: {failure}" for failure in failures))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["case", "label", "median_ms", "p20_ms", "p80_ms"] + (["peak_mib"] if args.memory else []))
            writer.writerows(rows)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
