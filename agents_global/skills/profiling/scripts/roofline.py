# /// script
# requires-python = ">=3.11"
# ///
"""Analytical roofline of a training micro batch from a TOML ops file: what each op should cost in principle.

Answers "is this op compute- or bandwidth-bound, what is its ideal time, and what MFU could the whole micro batch
reach if every op ran at its roofline?" from shapes alone, with no GPU. Each op's ideal time per call is
`max(flops / peak, bytes / bandwidth)`, using the compute peak the op names and the device's memory bandwidth, and
the micro batch's ideal time is the sum over ops (no overlap between ops). An op is bandwidth-bound when its
arithmetic intensity (FLOP/byte) is below its peak's ridge point (peak / bandwidth).

The ops file (all expressions are strings evaluated over `[params]`; a param is a number or such a string):
- `[params]`: named numbers or expressions over other params. `--set NAME=EXPR` overrides or adds one (repeatable).
  Expressions allow + - * / // % **, parentheses, and min, max, ceil, floor, log2, sqrt.
- `[device]`: `bandwidth = "<name>"` picks the memory entry (default the first). `[device.compute.<name>]` and
  `[device.memory.<name>]` and `[device.links.<name>]` each hold `value` (FLOP/s or bytes/s), `source` and optional
  `verified` (default true; false prints the value as UNVERIFIED) and `dense` (compute peaks: dense or sparse).
- `[layers]`: layer kind -> count expression. The kind `all` is shared: its ops run in every layer, and the
  per-layer view adds them to each other kind.
- `[schedule]`: `micro_batches_per_step` expression; ops with `per = "step"` are amortized over it.
- `[mfu]`: `flops` (FLOPs the MFU definition counts per micro batch per GPU), `peak` (compute peak it divides by),
  `tokens` (tokens per micro batch per GPU, for ideal tokens/s) and `definition` (text).
- `assumptions`: list of strings, printed verbatim.
- `[[ops]]`: `name`, `group`, any other string fields (e.g. `kind`, usable with `--group-by`), `peak` (a compute
  name) or `link` (a link name: a communication op, reported separately and excluded from the compute roofline),
  `flops` and `bytes` per call (default 0), `calls` per layer if `layer` is set, else per micro batch (or per step
  with `per = "step"`), `ref` (source reference) and `mfu_counted` (bool, informational).

Output (markdown, stdout): device peaks with ridge points, one table per group (`--group-by FIELD`, default
`group`) with per-op FLOPs, bytes, intensity, ridge, bound, ideal ms per micro batch and share, a group summary, a
per-layer-kind view, totals (ideal ms, compute- vs bandwidth-bound share, ideal MFU under the file's definition),
a communication table, and every op's formulas. With `--measured CSV` (e.g. `step_accounting.py --csv`: first
column row names, one column of ms), `--map LABEL:REGEX` (repeatable; CSV rows whose name matches REGEX, first map
wins, are summed into LABEL, a value of `--measured-by FIELD`, default the group-by field) adds measured vs ideal
per label. `--measured-column` picks the CSV column (default the first data column) and `--measured-scale`
multiplies measured values (e.g. 0.5 for a two-micro-batch step).

Usage:
  uv run --script roofline.py OPS.toml [--set n_layers=6] [--set micro_batches=100] [--group-by kind]
       [--measured step_accounting.csv --measured-scale 0.5 --map "moe_gemm:MoE expert GEMM" ...]
"""

import argparse
import ast
import csv
import math
import operator
import re
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass

FUNCTIONS = {"min": min, "max": max, "ceil": math.ceil, "floor": math.floor, "log2": math.log2, "sqrt": math.sqrt}
BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
SHARED_LAYER = "all"


class Params:
    """Lazily resolved named expressions, with cycle detection."""

    def __init__(self, raw: dict):
        self.raw = dict(raw)
        self.values: dict[str, float] = {}
        self.resolving: list[str] = []

    def get(self, name: str) -> float:
        if name in self.values:
            return self.values[name]
        if name not in self.raw:
            raise KeyError(f"unknown param {name!r}")
        if name in self.resolving:
            raise ValueError(f"param cycle: {' -> '.join(self.resolving + [name])}")
        self.resolving.append(name)
        value = self.eval(self.raw[name])
        self.resolving.pop()
        self.values[name] = value
        return value

    def eval(self, expr) -> float:
        if isinstance(expr, bool):
            raise TypeError(f"boolean is not a number: {expr!r}")
        if isinstance(expr, (int, float)):
            return expr
        return self._node(ast.parse(str(expr), mode="eval").body, str(expr))

    def _node(self, node, expr: str) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            return self.get(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            return BINARY[type(node.op)](self._node(node.left, expr), self._node(node.right, expr))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = self._node(node.operand, expr)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            return FUNCTIONS[node.func.id](*(self._node(arg, expr) for arg in node.args))
        raise ValueError(f"unsupported syntax in expression {expr!r}: {ast.dump(node)}")


@dataclass
class Resource:
    name: str
    value: float
    source: str
    verified: bool
    dense: bool | None


@dataclass
class Op:
    spec: dict
    calls: float
    flops: float
    bytes: float
    seconds_per_call: float
    compute_bound: bool

    @property
    def name(self) -> str:
        return self.spec["name"]

    @property
    def seconds(self) -> float:
        return self.calls * self.seconds_per_call

    @property
    def total_flops(self) -> float:
        return self.calls * self.flops

    @property
    def total_bytes(self) -> float:
        return self.calls * self.bytes

    def field(self, name: str) -> str:
        return str(self.spec.get(name, "-"))


def resources(table: dict) -> dict[str, Resource]:
    return {
        name: Resource(
            name,
            float(entry["value"]),
            entry.get("source", "no source given"),
            entry.get("verified", True) and "source" in entry,
            entry.get("dense"),
        )
        for name, entry in table.items()
    }


def num(value: float, digits: int = 3) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.{digits}g}"


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def build_ops(spec: dict, params: Params, compute: dict, memory: Resource, links: dict) -> tuple[list[Op], list[Op]]:
    layer_counts = {kind: params.eval(expr) for kind, expr in spec.get("layers", {}).items()}
    per_step = params.eval(spec.get("schedule", {}).get("micro_batches_per_step", 1))
    compute_ops, comm_ops = [], []
    for entry in spec["ops"]:
        calls = params.eval(entry.get("calls", 1))
        if "layer" in entry:
            if entry["layer"] not in layer_counts:
                raise KeyError(f"op {entry['name']!r} names layer kind {entry['layer']!r}, not in [layers]")
            calls *= layer_counts[entry["layer"]]
        if entry.get("per", "micro_batch") == "step":
            calls /= per_step
        flops = params.eval(entry.get("flops", 0))
        nbytes = params.eval(entry.get("bytes", 0))
        if "link" in entry:
            link = links[entry["link"]]
            comm_ops.append(Op(entry, calls, flops, nbytes, nbytes / link.value, False))
            continue
        peak = compute[entry["peak"]]
        compute_s, memory_s = flops / peak.value, nbytes / memory.value
        compute_ops.append(Op(entry, calls, flops, nbytes, max(compute_s, memory_s), compute_s >= memory_s))
    return compute_ops, comm_ops


def ridge(op: Op, compute: dict, memory: Resource) -> float:
    return compute[op.spec["peak"]].value / memory.value


def intensity(op: Op) -> str:
    return num(op.flops / op.bytes, 3) if op.bytes else "inf"


def device_section(compute: dict, memory: Resource, links: dict) -> list[str]:
    lines = ["## Device", "", "| resource | value | ridge FLOP/B | dense | status |", "|---|---:|---:|---|---|"]
    for res in compute.values():
        dense = "-" if res.dense is None else ("dense" if res.dense else "sparse")
        status = "sourced" if res.verified else "UNVERIFIED"
        lines.append(f"| {res.name} | {res.value:.4g} FLOP/s | {num(res.value / memory.value)} | {dense} | {status} |")
    for res in (memory, *links.values()):
        status = "sourced" if res.verified else "UNVERIFIED"
        lines.append(f"| {res.name} | {res.value:.4g} B/s | - | - | {status} |")
    lines += ["", "Sources:", ""]
    lines += [f"- {res.name}: {res.source}" for res in (*compute.values(), memory, *links.values())]
    return lines + [""]


def group_tables(ops: list[Op], by: str, total_s: float, compute: dict, memory: Resource) -> list[str]:
    lines = ["## Ops by " + by, ""]
    groups = defaultdict(list)
    for op in ops:
        groups[op.field(by)].append(op)
    for label, members in sorted(groups.items(), key=lambda item: -sum(op.seconds for op in item[1])):
        group_s = sum(op.seconds for op in members)
        lines += [f"### {label}: {group_s * 1e3:.3f} ms ({pct(group_s, total_s)})", ""]
        lines += ["| op | peak | calls | GFLOP | GB | FLOP/B | ridge | bound | ms | % |"]
        lines += ["|---|---|---:|---:|---:|---:|---:|---|---:|---:|"]
        for op in sorted(members, key=lambda op: -op.seconds):
            bound = "compute" if op.compute_bound else "bw"
            lines.append(
                f"| {op.name} | {op.spec['peak']} | {num(op.calls)} | {num(op.total_flops / 1e9)} | "
                f"{num(op.total_bytes / 1e9)} | {intensity(op)} | {num(ridge(op, compute, memory))} | {bound} | "
                f"{op.seconds * 1e3:.3f} | {pct(op.seconds, total_s)} |"
            )
        lines.append("")
    return lines


def summary_table(ops: list[Op], by: str, total_s: float) -> list[str]:
    lines = [f"## Summary by {by}", "", f"| {by} | GFLOP | GB | ideal ms | share | bw-bound ms | bw-bound share |"]
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    groups = defaultdict(list)
    for op in ops:
        groups[op.field(by)].append(op)
    for label, members in sorted(groups.items(), key=lambda item: -sum(op.seconds for op in item[1])):
        group_s = sum(op.seconds for op in members)
        bw_s = sum(op.seconds for op in members if not op.compute_bound)
        lines.append(
            f"| {label} | {num(sum(op.total_flops for op in members) / 1e9)} | "
            f"{num(sum(op.total_bytes for op in members) / 1e9)} | {group_s * 1e3:.3f} | {pct(group_s, total_s)} | "
            f"{bw_s * 1e3:.3f} | {pct(bw_s, group_s)} |"
        )
    return lines + [""]


def peak_table(ops: list[Op], total_s: float) -> list[str]:
    lines = ["## Summary by peak", "", "| peak | GFLOP | ideal ms | share | compute-bound ms | bw-bound ms |"]
    lines.append("|---|---:|---:|---:|---:|---:|")
    peaks = defaultdict(list)
    for op in ops:
        peaks[op.spec["peak"]].append(op)
    for peak, members in sorted(peaks.items(), key=lambda item: -sum(op.seconds for op in item[1])):
        peak_s = sum(op.seconds for op in members)
        compute_s = sum(op.seconds for op in members if op.compute_bound)
        lines.append(
            f"| {peak} | {num(sum(op.total_flops for op in members) / 1e9)} | {peak_s * 1e3:.3f} | "
            f"{pct(peak_s, total_s)} | {compute_s * 1e3:.3f} | {(peak_s - compute_s) * 1e3:.3f} |"
        )
    return lines + [""]


def layer_table(spec: dict, params: Params, ops: list[Op]) -> list[str]:
    layer_counts = {kind: params.eval(expr) for kind, expr in spec.get("layers", {}).items()}
    if not layer_counts:
        return []
    per_layer = defaultdict(float)
    per_layer_bw = defaultdict(float)
    for op in ops:
        kind = op.spec.get("layer")
        if kind is None or not layer_counts[kind]:
            continue
        per_layer[kind] += op.seconds / layer_counts[kind]
        per_layer_bw[kind] += 0 if op.compute_bound else op.seconds / layer_counts[kind]
    kinds = [kind for kind in layer_counts if kind != SHARED_LAYER] or [SHARED_LAYER]
    lines = ["## Per layer", "", "| layer kind | count | ms per layer | bw-bound ms per layer | ms, all of this kind |"]
    lines.append("|---|---:|---:|---:|---:|")
    shared = per_layer[SHARED_LAYER] if kinds != [SHARED_LAYER] else 0.0
    shared_bw = per_layer_bw[SHARED_LAYER] if kinds != [SHARED_LAYER] else 0.0
    layers_s = 0.0
    for kind in kinds:
        one = per_layer[kind] + shared
        layers_s += one * layer_counts[kind]
        lines.append(
            f"| {kind} | {num(layer_counts[kind])} | {one * 1e3:.3f} | {(per_layer_bw[kind] + shared_bw) * 1e3:.3f} | "
            f"{one * layer_counts[kind] * 1e3:.3f} |"
        )
    other_s = sum(op.seconds for op in ops if "layer" not in op.spec)
    lines += ["", f"All layers: {layers_s * 1e3:.3f} ms per micro batch; ops outside layers: {other_s * 1e3:.3f} ms.", ""]
    if kinds != [SHARED_LAYER]:
        lines += [f"Each kind's row includes the `{SHARED_LAYER}` ops ({shared * 1e3:.3f} ms per layer).", ""]
    return lines


def totals_section(spec: dict, params: Params, ops: list[Op], compute: dict, total_s: float) -> list[str]:
    bw_s = sum(op.seconds for op in ops if not op.compute_bound)
    step_s = sum(op.seconds for op in ops if op.spec.get("per") == "step")
    per_step = params.eval(spec.get("schedule", {}).get("micro_batches_per_step", 1))
    lines = [
        "## Totals per micro batch",
        "",
        f"- Ideal time: {total_s * 1e3:.3f} ms, of which per-step ops amortized over {num(per_step)} micro batches: "
        f"{step_s * 1e3:.3f} ms.",
        f"- Compute-bound: {(total_s - bw_s) * 1e3:.3f} ms ({pct(total_s - bw_s, total_s)}); bandwidth-bound: "
        f"{bw_s * 1e3:.3f} ms ({pct(bw_s, total_s)}).",
        f"- Executed FLOPs: {sum(op.total_flops for op in ops) / 1e12:.3f} TFLOP; HBM bytes: "
        f"{sum(op.total_bytes for op in ops) / 1e9:.2f} GB.",
    ]
    mfu = spec.get("mfu")
    if mfu:
        counted = params.eval(mfu["flops"])
        peak = compute[mfu["peak"]]
        lines.append(
            f"- MFU-counted FLOPs: {counted / 1e12:.3f} TFLOP; ideal MFU against {peak.name} "
            f"({peak.value:.4g} FLOP/s): {100 * counted / (total_s * peak.value):.1f}%."
        )
        if "tokens" in mfu:
            tokens = params.eval(mfu["tokens"])
            lines.append(f"- Ideal throughput: {tokens / total_s:,.0f} tokens/s per GPU ({num(tokens)} tokens).")
        if "definition" in mfu:
            lines.append(f"- MFU definition: {mfu['definition']}")
        counted_ops = [op.name for op in ops if op.spec.get("mfu_counted")]
        if counted_ops:
            lines.append(f"- Ops whose FLOPs the MFU definition counts (once, no recompute): {', '.join(counted_ops)}.")
    return lines + [""]


def comm_section(comm_ops: list[Op], total_s: float) -> list[str]:
    if not comm_ops:
        return []
    comm_s = sum(op.seconds for op in comm_ops)
    lines = [
        "## Communication (not in the compute roofline)",
        "",
        f"Total {comm_s * 1e3:.3f} ms per micro batch at link bandwidth, {pct(comm_s, total_s)} of the compute "
        "ideal if none of it overlapped.",
        "",
        "| op | group | link | calls | GB | ms |",
        "|---|---|---|---:|---:|---:|",
    ]
    for op in sorted(comm_ops, key=lambda op: -op.seconds):
        lines.append(
            f"| {op.name} | {op.field('group')} | {op.spec['link']} | {num(op.calls)} | {num(op.total_bytes / 1e9)} | "
            f"{op.seconds * 1e3:.3f} |"
        )
    return lines + [""]


def measured_section(args, ops: list[Op], total_s: float) -> list[str]:
    with open(args.measured, newline="") as handle:
        rows = list(csv.reader(handle))
    header, body = rows[0], rows[1:]
    column = header.index(args.measured_column) if args.measured_column else 1
    maps = []
    for item in args.map:
        label, _, pattern = item.partition(":")
        maps.append((label, re.compile(pattern)))
    measured = defaultdict(float)
    unmapped = []
    for row in body:
        if len(row) <= column or not row[column]:
            continue
        value = float(row[column]) * args.measured_scale
        label = next((label for label, pattern in maps if pattern.search(row[0])), None)
        if label is None:
            unmapped.append((row[0], value))
        else:
            measured[label] += value
    by = args.measured_by or args.group_by
    ideal = defaultdict(float)
    for op in ops:
        ideal[op.field(by)] += op.seconds * 1e3
    labels = list(dict.fromkeys(label for label, _ in maps))
    lines = [
        f"## Measured vs ideal by {by}",
        "",
        f"Measured: `{args.measured}` column `{header[column]}` x {num(args.measured_scale)}.",
        "",
        "| label | measured ms | ideal ms | measured / ideal | gap ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in sorted(labels, key=lambda label: -(measured[label] - ideal[label])):
        ratio = f"{measured[label] / ideal[label]:.2f}x" if ideal[label] else "-"
        lines.append(
            f"| {label} | {measured[label]:.3f} | {ideal[label]:.3f} | {ratio} | {measured[label] - ideal[label]:.3f} |"
        )
    mapped_ms, ideal_mapped = sum(measured.values()), sum(ideal[label] for label in labels)
    ratio = f"{mapped_ms / ideal_mapped:.2f}x" if ideal_mapped else "-"
    lines += [
        f"| **mapped total** | **{mapped_ms:.3f}** | **{ideal_mapped:.3f}** | **{ratio}** | "
        f"**{mapped_ms - ideal_mapped:.3f}** |",
        "",
    ]
    unmatched_ideal = [label for label in ideal if label not in labels]
    if unmatched_ideal:
        lines.append(
            "Ideal labels with no measured mapping: "
            + ", ".join(f"{label} ({ideal[label]:.3f} ms)" for label in sorted(unmatched_ideal))
            + "."
        )
    if unmapped:
        lines.append(
            "Measured rows not mapped: " + ", ".join(f"{name} ({value:.3f} ms)" for name, value in unmapped) + "."
        )
    return lines + [""]


def formulas_section(spec: dict, params: Params, overrides: list[str]) -> list[str]:
    lines = ["## Inputs", ""]
    if overrides:
        lines += ["Overrides: " + ", ".join(f"`{item}`" for item in overrides), ""]
    lines += ["Params (resolved):", ""]
    lines += [f"- `{name}` = `{spec_value}` = {num(params.get(name), 6)}" for name, spec_value in params.raw.items()]
    lines += ["", "Ops (per call; `calls` per layer of `layer`, or per micro batch, or per step):", ""]
    for entry in spec["ops"]:
        where = f"layer {entry['layer']}, " if "layer" in entry else ""
        resource = f"peak {entry['peak']}" if "peak" in entry else f"link {entry['link']}"
        lines.append(
            f"- {entry['name']} ({where}{resource}, per {entry.get('per', 'micro_batch')}): calls `{entry.get('calls', 1)}`, "
            f"flops `{entry.get('flops', 0)}`, bytes `{entry.get('bytes', 0)}`; ref {entry.get('ref', '-')}"
        )
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ops_file")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=EXPR", help="override or add a param")
    parser.add_argument("--group-by", default="group", help="op field to group tables by (default: group)")
    parser.add_argument("--title", default=None, help="heading for the report (default: the ops file name)")
    parser.add_argument("--measured", default=None, help="CSV of measured ms per row name (step_accounting.py --csv)")
    parser.add_argument("--map", action="append", default=[], metavar="LABEL:REGEX", help="measured rows -> label")
    parser.add_argument("--measured-by", default=None, help="op field the --map labels refer to (default: --group-by)")
    parser.add_argument("--measured-column", default=None, help="CSV column with the values (default: second column)")
    parser.add_argument("--measured-scale", type=float, default=1.0, help="multiply measured values (default 1)")
    args = parser.parse_args()

    with open(args.ops_file, "rb") as handle:
        spec = tomllib.load(handle)
    raw = dict(spec.get("params", {}))
    for item in args.set:
        name, sep, expr = item.partition("=")
        if not sep:
            parser.error(f"--set expects NAME=EXPR, got {item!r}")
        raw[name.strip()] = expr.strip()
    params = Params(raw)

    device = spec["device"]
    compute = resources(device["compute"])
    memories = resources(device["memory"])
    memory = memories[device["bandwidth"]] if "bandwidth" in device else next(iter(memories.values()))
    links = resources(device.get("links", {}))
    ops, comm_ops = build_ops(spec, params, compute, memory, links)
    total_s = sum(op.seconds for op in ops)

    lines = [f"# Roofline: {args.title or args.ops_file}", ""]
    lines += totals_section(spec, params, ops, compute, total_s)
    if spec.get("assumptions"):
        lines += ["## Assumptions", ""] + [f"- {item}" for item in spec["assumptions"]] + [""]
    lines += device_section(compute, memory, links)
    lines += summary_table(ops, args.group_by, total_s)
    lines += peak_table(ops, total_s)
    lines += layer_table(spec, params, ops)
    if args.measured:
        lines += measured_section(args, ops, total_s)
    lines += comm_section(comm_ops, total_s)
    lines += group_tables(ops, args.group_by, total_s, compute, memory)
    lines += formulas_section(spec, params, args.set)
    sys.stdout.write("\n".join(lines))


if __name__ == "__main__":
    main()
