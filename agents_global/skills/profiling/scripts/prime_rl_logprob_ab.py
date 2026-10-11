"""Time prime-rl trainer forward+backward steps on real text and dump per-token logprobs, one arm per launch.

usage (one node, under torchrun, from the arm's worktree):
  uv run --no-sync torchrun --nproc-per-node 8 prime_rl_logprob_ab.py dump OUT.pt --tokens-per-gpu N
      [--steps S] [--warmup W] [--text-glob GLOB] [--module-types REGEX]
      -- <trainer ModelConfig CLI args, e.g. --name X --ep 8>
  uv run --no-sync python prime_rl_logprob_ab.py compare A.pt B.pt
  uv run --no-sync python prime_rl_logprob_ab.py table --row LABEL REF.pt ARM.pt [REF2.pt] [--row ...]

`dump` builds the model with prime-rl's own `setup_model` (FSDP, EP, AC, compile and weight loading as the
trainer does), feeds each rank a different contiguous slice of tokenized text (files matching --text-glob,
concatenated in sorted order and cycled if short), and runs S steps of forward plus `logprobs.sum().backward()`
with no optimizer. Step times come from CUDA events around each step; the first W steps are dropped. Rank 0
gathers every rank's step-1 logprobs and writes them with the step times to OUT.pt, together with the peak
allocated and reserved CUDA memory over all steps (max over ranks, GiB). With --module-types, rank 0 also
prints and stores the count of module class names among modules whose qualified name matches REGEX, after
setup_model's replacement passes (e.g. 'o_a_proj$' to check which class a projection became).

`compare` prints the step-time medians and peak memory of both dumps, how many tokens' logprobs differ at all, and
the per-token logprob difference (mean absolute, max absolute, signed mean, B minus A) over all gathered tokens.

`table` prints one markdown row per --row: the arm's median step time (ms) and peak allocated memory (GiB), its
mean absolute and signed mean logprob difference against REF (arm minus REF), and, when REF2 is given (a rerun
of the reference arm), the same two numbers for REF2 against REF as the run-to-run noise floor.
"""

import argparse
import collections
import glob
import re
import statistics
import sys


def dump(args, model_args):
    from datetime import timedelta
    from pathlib import Path

    import torch
    import torch.distributed as dist
    from transformers import AutoTokenizer

    from prime_rl.configs.trainer import ModelConfig
    from prime_rl.trainer.model import forward, setup_model
    from prime_rl.trainer.parallel_dims import get_parallel_dims, resolve_ep
    from prime_rl.trainer.utils import setup_torch_distributed
    from prime_rl.trainer.world import get_world
    from prime_rl.utils.config import cli

    config = cli(ModelConfig, args=model_args)
    paths = sorted(glob.glob(args.text_glob, recursive=True))
    if not paths:
        sys.exit(f"--text-glob {args.text_glob!r} matched no files (relative paths resolve from the working directory)")
    world = get_world()
    setup_torch_distributed(timeout=timedelta(hours=2))
    resolve_ep(config)
    parallel_dims = get_parallel_dims(config)
    model = setup_model(config, parallel_dims)
    module_types = {}
    if args.module_types:
        pattern = re.compile(args.module_types)
        names = (type(module).__name__ for name, module in model.named_modules() if pattern.search(name))
        module_types = dict(collections.Counter(names))
        if world.rank == 0:
            print(f"module types matching {args.module_types!r}: {module_types}")

    tokenizer = AutoTokenizer.from_pretrained(config.name, trust_remote_code=config.trust_remote_code)
    text = "\n".join(Path(path).read_text() for path in paths)
    ids = tokenizer(text, add_special_tokens=False, return_tensors="pt").input_ids[0]
    needed = (world.world_size + 1) * args.tokens_per_gpu
    ids = ids.repeat(needed // ids.numel() + 1)
    start = world.rank * args.tokens_per_gpu
    window = ids[start : start + args.tokens_per_gpu + 1].cuda()
    input_ids, labels = window[:-1][None], window[1:][None]
    position_ids = torch.arange(args.tokens_per_gpu, device="cuda")[None]
    seq_lens = torch.tensor([args.tokens_per_gpu], device="cuda", dtype=torch.int32)
    temperature = torch.ones(1, args.tokens_per_gpu, device="cuda")

    times, first_logprobs = [], None
    for step in range(args.steps):
        begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        begin.record()
        out = forward(model, input_ids, position_ids, seq_lens=seq_lens, labels=labels, temperature=temperature)
        out["logprobs"].sum().backward()
        end.record()
        torch.cuda.synchronize()
        times.append(begin.elapsed_time(end))
        if step == 0:
            first_logprobs = out["logprobs"].detach().float().flatten()
        model.zero_grad(set_to_none=True)

    peak = torch.tensor(
        [torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved()], device="cuda", dtype=torch.float64
    )
    dist.all_reduce(peak, op=dist.ReduceOp.MAX)
    peak_alloc_gib, peak_reserved_gib = (peak / 2**30).tolist()
    gathered = [torch.empty_like(first_logprobs) for _ in range(world.world_size)] if world.rank == 0 else None
    dist.gather(first_logprobs, gathered, dst=0)
    if world.rank == 0:
        result = {
            "logprobs": torch.cat(gathered).cpu(),
            "step_ms": times,
            "warmup": args.warmup,
            "peak_alloc_gib": peak_alloc_gib,
            "peak_reserved_gib": peak_reserved_gib,
            "module_types": module_types,
        }
        torch.save(result, args.out)
        print(f"step ms (after {args.warmup} warmup): {times[args.warmup:]}")
        print(f"peak memory (max over ranks): allocated {peak_alloc_gib:.2f} GiB, reserved {peak_reserved_gib:.2f} GiB")
    dist.destroy_process_group()


def logprob_diff(ref: dict, arm: dict):
    if ref["logprobs"].shape != arm["logprobs"].shape:
        sys.exit(
            f"dumps hold {ref['logprobs'].numel()} and {arm['logprobs'].numel()} tokens; "
            "rerun both arms with the same world size and --tokens-per-gpu"
        )
    return arm["logprobs"] - ref["logprobs"]


def compare(args):
    import torch

    a, b = torch.load(args.a), torch.load(args.b)
    for label, run in (("A", a), ("B", b)):
        steady = run["step_ms"][run["warmup"] :]
        print(f"{label}: median step {statistics.median(steady):.1f} ms, min {min(steady):.1f}, max {max(steady):.1f}")
        if "peak_alloc_gib" in run:
            print(f"{label}: peak allocated {run['peak_alloc_gib']:.2f} GiB, reserved {run['peak_reserved_gib']:.2f} GiB")
    diff = logprob_diff(a, b)
    print(f"tokens: {diff.numel()} ({int(diff.count_nonzero())} differ)")
    print(f"mean |logprob B - A|: {diff.abs().mean():.6f}")
    print(f"max |logprob B - A|: {diff.abs().max():.6f}")
    print(f"mean (logprob B - A): {diff.mean():.6f}")
    print(f"mean logprob A: {a['logprobs'].mean():.4f}, B: {b['logprobs'].mean():.4f}")


def table(args):
    import torch

    print("| arm | median step ms | peak alloc GiB | mean abs dlogprob | signed dlogprob | noise abs | noise signed |")
    print("|---|---|---|---|---|---|---|")
    for label, *paths in args.row:
        ref, arm = torch.load(paths[0]), torch.load(paths[1])
        diff = logprob_diff(ref, arm)
        step_ms = statistics.median(arm["step_ms"][arm["warmup"] :])
        cells = [label, f"{step_ms:.1f}", f"{arm.get('peak_alloc_gib', float('nan')):.2f}"]
        cells += [f"{diff.abs().mean():.4f}", f"{diff.mean():+.4f}"]
        if len(paths) > 2:
            noise = logprob_diff(ref, torch.load(paths[2]))
            cells += [f"{noise.abs().mean():.4f}", f"{noise.mean():+.4f}"]
        else:
            cells += ["", ""]
        print("| " + " | ".join(cells) + " |")


def main():
    argv = sys.argv[1:]
    model_args = []
    if "--" in argv:
        split = argv.index("--")
        argv, model_args = argv[:split], argv[split + 1 :]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    dump_parser = sub.add_parser("dump")
    dump_parser.add_argument("out")
    dump_parser.add_argument("--tokens-per-gpu", type=int, required=True)
    dump_parser.add_argument("--steps", type=int, default=6)
    dump_parser.add_argument("--warmup", type=int, default=2)
    dump_parser.add_argument("--text-glob", default="src/**/*.py")
    dump_parser.add_argument("--module-types", default=None)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("a")
    compare_parser.add_argument("b")
    table_parser = sub.add_parser("table")
    table_parser.add_argument("--row", nargs="+", action="append", required=True, metavar="LABEL REF ARM [REF2]")
    args = parser.parse_args(argv)
    if args.command == "dump" and not 0 <= args.warmup < args.steps:
        dump_parser.error("--warmup must be at least 0 and less than --steps")
    if args.command == "dump":
        dump(args, model_args)
    elif args.command == "table":
        table(args)
    else:
        compare(args)


if __name__ == "__main__":
    main()
