# /// script
# requires-python = ">=3.10"
# dependencies = ["torch"]
# ///
"""CUDA-event timer for named regions, meant to be copied into a project as one file.

Wrap each timed region in `with timer("name"):`. Every entry records a pair of CUDA events on the current stream, so
timing never stalls the host. Events are only read in `summary()`, which waits on the last end event, so call it once
after the measured iterations, not inside the loop. Regions can repeat and nest; each name aggregates every entry.

Events time the current stream's timeline: work launched on another stream counts only if the current stream waits on
it (e.g. `work.wait()` on an async collective) before the region ends.

Usage:
  timer = CudaTimer()
  for step in range(steps):
      with timer("forward"):
          loss = model(batch)
      with timer("optimizer"):
          optimizer.step()
  timer.reset_after_warmup(2)  # optional: drop the first 2 entries of every region
  print(timer.table())         # count, total, mean, median, min, max in ms per region

Self-test on one GPU:
  uv run --script cuda_timer.py
"""

import statistics
from collections import defaultdict
from contextlib import contextmanager

import torch


class CudaTimer:
    def __init__(self):
        self._events: dict[str, list[tuple[torch.cuda.Event, torch.cuda.Event]]] = defaultdict(list)

    @contextmanager
    def __call__(self, name: str):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        try:
            yield
        finally:
            end.record()
            self._events[name].append((start, end))

    def reset_after_warmup(self, num_warmup: int):
        """Drop the first `num_warmup` entries of every region."""
        for name in self._events:
            self._events[name] = self._events[name][num_warmup:]

    def times_ms(self) -> dict[str, list[float]]:
        """Elapsed milliseconds of every entry, per region."""
        for pairs in self._events.values():
            if pairs:
                pairs[-1][1].synchronize()
        return {name: [start.elapsed_time(end) for start, end in pairs] for name, pairs in self._events.items()}

    def summary(self) -> dict[str, dict[str, float]]:
        """Count, total, mean, median, min and max milliseconds per region."""
        return {
            name: {
                "count": len(times),
                "total_ms": sum(times),
                "mean_ms": statistics.fmean(times),
                "median_ms": statistics.median(times),
                "min_ms": min(times),
                "max_ms": max(times),
            }
            for name, times in self.times_ms().items()
            if times
        }

    def table(self) -> str:
        """The summary as a markdown table."""
        rows = ["| region | count | total ms | mean ms | median ms | min ms | max ms |", "|---|---|---|---|---|---|---|"]
        for name, s in self.summary().items():
            rows.append(
                f"| {name} | {s['count']} | {s['total_ms']:.3f} | {s['mean_ms']:.3f} | {s['median_ms']:.3f} "
                f"| {s['min_ms']:.3f} | {s['max_ms']:.3f} |"
            )
        return "\n".join(rows)


if __name__ == "__main__":
    a = torch.randn(4096, 4096, device="cuda")
    timer = CudaTimer()
    for _ in range(12):
        with timer("step"):
            with timer("matmul"):
                a @ a
            with timer("two matmuls"):
                a @ a
                a @ a
    timer.reset_after_warmup(2)
    summary = timer.summary()
    assert summary["matmul"]["count"] == 10
    assert summary["two matmuls"]["median_ms"] > 1.5 * summary["matmul"]["median_ms"]
    assert summary["step"]["median_ms"] >= summary["two matmuls"]["median_ms"] + summary["matmul"]["median_ms"]
    print(timer.table())
