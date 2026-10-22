"""Time GPU callables with triton.testing.do_bench and print a markdown table.

usage: python bench_ops.py CASES.py [--only SUBSTR] [--warmup MS] [--rep MS] [--csv OUT] [--memory] [--check]
       [--cudagraph] [--trace DIR [--trace-iters N]] [--distributed]
       torchrun --nproc-per-node=N bench_ops.py CASES.py --distributed [...]

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
--whole-trace --csv OUT` (the CSV is in us; divide totals by --trace-iters for per-call numbers).
With --distributed, for callables that run collectives (launch under torchrun): the NCCL process group is initialized
from the torchrun environment and the device set from LOCAL_RANK before `cases()` runs, so cases may use
torch.distributed. Every rank must make the same calls in the same order, so do_bench's per-rank call counts are
replaced by counts from the slowest rank's estimate (the same warmup/estimate/L2-flush/event loop otherwise), with a
barrier before each callable's check, timing, memory and trace runs. Each table cell is the maximum over ranks (the
slowest rank's median, p20, p80 and peak memory; the largest abs diff, FAIL if any rank fails); rank 0 prints the
table and writes the CSV, and traces are written per rank as DIR/<case>__<label>__rank<r>.json.gz. --cudagraph is
not supported with --distributed. A callable that raises on only some ranks leaves the others waiting in a collective.
A case may be a 3-tuple (case_name, {label: callable}, work) where work is a dict with "flops" and/or "bytes", the
work one call does (the same for every label). The table and CSV then add throughput columns computed from each
median: TFLOP/s (flops / median) and GB/s (bytes / median, 1 GB = 1e9 bytes); cases without work leave them blank.
Say in the investigation's notes what the byte count covers (e.g. read plus write, or one link direction).
CASES.py may also define `teardown()`, called once after all timing (before the process group is destroyed), to
release resources such as communication contexts.
Build inputs inside `cases()` so they are allocated once. Keep CASES.py in the investigation's `inputs/`: it is an
input, like a config. Run it with the interpreter of the project under test (e.g. `uv run
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


def init_distributed():
    import os

    import torch
    import torch.distributed as dist

    device = torch.device("cuda", int(os.environ["LOCAL_RANK"]))
    torch.cuda.set_device(device)
    dist.init_process_group("nccl", device_id=device)


def max_over_ranks(values):
    import torch
    import torch.distributed as dist

    reduced = torch.tensor(values, dtype=torch.float64, device="cuda")
    dist.all_reduce(reduced, op=dist.ReduceOp.MAX)
    return reduced.tolist()


def do_bench_distributed(fn, warmup, rep, quantiles):
    import torch
    import torch.distributed as dist
    import triton

    driver = triton.runtime.driver.active
    fn()
    torch.cuda.synchronize()
    cache = driver.get_empty_cache_for_benchmark()
    dist.barrier()
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(5):
        driver.clear_cache(cache)
        fn()
    end.record()
    torch.cuda.synchronize()
    (estimate_ms,) = max_over_ranks([start.elapsed_time(end) / 5])
    n_warmup = max(1, int(warmup / estimate_ms))
    n_repeat = max(1, int(rep / estimate_ms))
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(n_repeat)]
    ends = [torch.cuda.Event(enable_timing=True) for _ in range(n_repeat)]
    for _ in range(n_warmup):
        fn()
    dist.barrier()
    for start, end in zip(starts, ends):
        driver.clear_cache(cache)
        start.record()
        fn()
        end.record()
    torch.cuda.synchronize()
    times = torch.tensor([start.elapsed_time(end) for start, end in zip(starts, ends)], dtype=torch.float64)
    return max_over_ranks(torch.quantile(times, torch.tensor(quantiles, dtype=torch.float64)).tolist())


def merge_check_over_ranks(result):
    import torch.distributed as dist

    results = [None] * dist.get_world_size()
    dist.all_gather_object(results, result)
    for rank, (message, failed, _) in enumerate(results):
        if failed:
            return f"rank {rank}: {message}", True, None
    diffs = [max_diff for _, _, max_diff in results if max_diff is not None]
    if not diffs:
        return results[0]
    return f"ok, max abs diff over ranks {max(diffs):.3g}", False, max(diffs)


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
        return (
            f"shape mismatch: {[tuple(t.shape) for t in reference]} vs {[tuple(t.shape) for t in output]}",
            True,
            None,
        )
    if not reference:
        return "no tensor outputs", False, None
    max_diff = max(
        ((r.double() - o.double()).abs().max().item() if r.numel() else 0.0) for r, o in zip(reference, output)
    )
    try:
        for r, o in zip(reference, output):
            torch.testing.assert_close(o, r, equal_nan=True)
    except AssertionError:
        return f"FAIL, max abs diff {max_diff:.3g}", True, max_diff
    return f"ok, max abs diff {max_diff:.3g}", False, max_diff


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
    parser.add_argument("--distributed", action="store_true", help="run under torchrun; see the usage docstring")
    args = parser.parse_args()
    if args.distributed and args.cudagraph:
        parser.error("--cudagraph is not supported with --distributed")

    import torch
    import triton

    rank = 0
    if args.distributed:
        import torch.distributed as dist

        init_distributed()
        rank, world_size = dist.get_rank(), dist.get_world_size()

    rows = []
    checks = {}
    first_labels = {}
    works = {}
    failures = []
    for case_name, fns, *case_work in load_cases(args.cases_file):
        works[case_name] = case_work[0] if case_work else {}
        if args.only and args.only not in case_name:
            continue
        reference = None
        first_labels[case_name] = next(iter(fns), None)
        for label, fn in fns.items():
            try:
                if args.check:
                    if args.distributed:
                        dist.barrier()
                    output = output_tensors(fn())
                    if label == first_labels[case_name]:
                        reference = output
                        checks[case_name, label] = "reference"
                    elif reference is None:
                        checks[case_name, label] = "no reference (first label failed)"
                    else:
                        result = compare_outputs(reference, output)
                        if args.distributed:
                            result = merge_check_over_ranks(result)
                        checks[case_name, label] = result[0]
                    del output
                if args.cudagraph:
                    p50, p20, p80 = triton.testing.do_bench_cudagraph(fn, rep=args.rep, quantiles=[0.5, 0.2, 0.8])
                elif args.distributed:
                    p50, p20, p80 = do_bench_distributed(fn, args.warmup, args.rep, [0.5, 0.2, 0.8])
                else:
                    p50, p20, p80 = triton.testing.do_bench(
                        fn, warmup=args.warmup, rep=args.rep, quantiles=[0.5, 0.2, 0.8]
                    )
                row = [case_name, label, p50, p20, p80]
                if args.memory:
                    torch.cuda.synchronize()
                    if args.distributed:
                        dist.barrier()
                    baseline = torch.cuda.memory_allocated()
                    torch.cuda.reset_peak_memory_stats()
                    fn()
                    torch.cuda.synchronize()
                    peak_mib = (torch.cuda.max_memory_allocated() - baseline) / 2**20
                    row.append(max_over_ranks([peak_mib])[0] if args.distributed else peak_mib)
                if args.trace:
                    trace_name = f"{case_name}__{label}"
                    if args.distributed:
                        dist.barrier()
                        trace_name += f"__rank{rank}"
                    write_trace(fn, args.trace, trace_name, args.trace_iters)
            except Exception as error:  # noqa: BLE001
                message = str(error).splitlines()[0] if str(error) else ""
                failures.append(f"{case_name} | {label}: {type(error).__name__}: {message}")
                print(f"{f'rank {rank} ' if args.distributed else ''}failed: {failures[-1]}", file=sys.stderr)
                continue
            rows.append(tuple(row))
        del reference
        torch.cuda.empty_cache()

    teardown = getattr(sys.modules["bench_cases"], "teardown", None)
    if teardown is not None:
        teardown()
    if args.distributed:
        dist.destroy_process_group()
        if rank != 0:
            sys.exit(1 if failures else 0)
    timer = (
        f"do_bench_cudagraph rep {args.rep} ms"
        if args.cudagraph
        else f"do_bench warmup {args.warmup} ms, rep {args.rep} ms"
    )
    if args.distributed:
        timer += f", {world_size} ranks, max over ranks"
    print(f"device: {torch.cuda.get_device_name()}, {timer}\n")
    work_keys = [key for key in ("flops", "bytes") if any(key in work for work in works.values())]
    work_units = {"flops": ("TFLOP/s", 1e12), "bytes": ("GB/s", 1e9)}

    def throughputs(case_name, median_ms):
        work = works.get(case_name, {})
        return [work[key] / (median_ms * 1e-3) / work_units[key][1] if key in work else None for key in work_keys]

    work_header = "".join(f" {work_units[key][0]} |" for key in work_keys)
    memory_header = " peak MiB above baseline |" if args.memory else ""
    check_header = " check vs first label |" if args.check else ""
    print(
        f"| case | label | median ms | p20 ms | p80 ms | first label / this |{work_header}{memory_header}{check_header}"
    )
    print(
        "|---|---|---|---|---|---|"
        + "---|" * len(work_keys)
        + ("---|" if args.memory else "")
        + ("---|" if args.check else "")
    )
    medians = {(case_name, label): p50 for case_name, label, p50, *_ in rows}
    for case_name, label, p50, p20, p80, *memory in rows:
        reference_median = medians.get((case_name, first_labels[case_name]))
        speedup = f"{reference_median / p50:.2f}x" if reference_median else "n/a"
        work_cells = "".join(f" {value:.1f} |" if value is not None else " |" for value in throughputs(case_name, p50))
        memory_cell = f" {memory[0]:.1f} |" if memory else ""
        check_cell = f" {checks.get((case_name, label), '')} |" if args.check else ""
        print(
            f"| {case_name} | {label} | {p50:.4f} | {p20:.4f} | {p80:.4f} | {speedup} |"
            f"{work_cells}{memory_cell}{check_cell}"
        )
    if failures:
        print("\n" + "\n".join(f"failed: {failure}" for failure in failures))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            csv_work_names = {"flops": "tflops", "bytes": "gbps"}
            writer.writerow(
                ["case", "label", "median_ms", "p20_ms", "p80_ms"]
                + (["peak_mib"] if args.memory else [])
                + [csv_work_names[key] for key in work_keys]
            )
            for row in rows:
                values = throughputs(row[0], row[2])
                writer.writerow(list(row) + ["" if value is None else f"{value:.3f}" for value in values])
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
