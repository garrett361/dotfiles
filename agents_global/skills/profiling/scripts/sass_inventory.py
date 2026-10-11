"""Inventory the SASS a compiler emitted: MMA flavor and shapes, async copies, and registers per kernel.

Finds every `.cubin` and `.so` under the given paths (files or directories, e.g. a fresh
`TILELANG_CACHE_DIR`, a `CUTE_DSL_DUMP_DIR` written with `CUTE_DSL_KEEP=cubin`, or a Triton cache),
disassembles each with `cuobjdump -sass`, and prints one markdown table per kernel function:

- registers, stack and local memory from `cuobjdump --dump-resource-usage` (`STACK`/`LOCAL` > 0 means
  spills or local arrays);
- counts of the instruction classes that tell designs apart: `HGMMA` (sm90 WGMMA, split by shape),
  `HMMA` (`mma.sync`), `UTCHMMA` (sm100 `tcgen05.mma`), `WARPGROUP.ARRIVE`/`DEPBAR` (WGMMA issue and
  wait), `LDGSTS` (`cp.async`), `UTMALDG`/`UTMASTG` (TMA), `UBLKCP` (bulk copy), `LDSM`/`STSM`
  (`ldmatrix`/`stmatrix`), `BAR.SYNC`/`BAR.ARV` (named barriers), `SYNCS` (mbarrier), `MUFU.*`, global
  loads and stores, and `LDL`/`STL` (local memory traffic).

Counts are static (instructions in the binary), not executed counts: a loop body the compiler emitted
twice counts twice. Use ncu for executed counts.

`--by-line OPCODE ...` adds, per kernel, which source lines those opcodes come from (e.g. `LDL STL` to find
spills), via `nvdisasm --print-line-info`; the binary needs line info (`CUTE_DSL_LINEINFO=1`, `-lineinfo`).
For CuTe DSL kernels this is more precise than the `remarks{ptx}` spill remark, whose source frame marks a
register-pressure region rather than the spilling instructions.

Usage:
  python3 sass_inventory.py <path> [<path> ...] [--kernel REGEX] [--extra OPCODE ...] [--by-line OPCODE ...]
  python3 sass_inventory.py $TILELANG_CACHE_DIR ~/run/cute_dump/k.sm_90a.cubin --kernel 'attn|main_kernel'
"""

import argparse
import glob
import os
import re
import subprocess
import tempfile
from collections import Counter

DEFAULT_OPCODES = (
    "HMMA",
    "UTCHMMA",
    "WARPGROUP.ARRIVE",
    "WARPGROUP.DEPBAR",
    "LDGSTS",
    "UTMALDG",
    "UTMASTG",
    "UBLKCP",
    "LDSM",
    "STSM",
    "BAR.SYNC",
    "BAR.ARV",
    "SYNCS",
    "MUFU.EX2",
    "MUFU.LG2",
    "MUFU.RCP",
    "LDG",
    "STG",
    "LDS",
    "STS",
    "LDL",
    "STL",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="cubin/.so files or directories to search")
    parser.add_argument("--cuobjdump", default="/usr/local/cuda-13.0/bin/cuobjdump")
    parser.add_argument("--kernel", default=None, help="only functions whose name matches this regex")
    parser.add_argument("--extra", nargs="*", default=[], help="more opcode prefixes to count, e.g. FFMA SHFL.BFLY")
    parser.add_argument("--by-line", nargs="*", default=[], help="opcode prefixes to attribute to source lines")
    parser.add_argument("--nvdisasm", default="/usr/local/cuda-13.0/bin/nvdisasm")
    return parser.parse_args()


def find_binaries(paths: list[str]) -> list[str]:
    found = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, names in os.walk(path):
                found += [os.path.join(root, n) for n in sorted(names) if n.endswith((".cubin", ".so"))]
        else:
            found.append(path)
    return found


def split_functions(sass: str) -> dict[tuple[str, str], list[str]]:
    functions, current, arch = {}, None, ""
    for line in sass.splitlines():
        code_for = re.match(r"\s*code for (sm_\d+)", line)
        if code_for:
            arch = code_for.group(1)
        header = re.match(r"\s*Function : (\S+)", line)
        if header:
            current = (arch, header.group(1))
            functions[current] = []
        elif current is not None and re.match(r"\s*/\*[0-9a-f]{4,}\*/", line):
            functions[current].append(line)
    return functions


def resource_usage(cuobjdump: str, path: str) -> dict[tuple[str, str], str]:
    text = subprocess.run(
        [cuobjdump, "--dump-resource-usage", path], capture_output=True, text=True, check=False
    ).stdout
    usage, current, arch = {}, None, ""
    for line in text.splitlines():
        arch_line = re.match(r"\s*arch = (sm_\d+)", line)
        if arch_line:
            arch = arch_line.group(1)
        header = re.match(r"\s*Function (\S+):", line)
        if header:
            current = (arch, header.group(1))
        elif current and "REG:" in line:
            fields = dict(re.findall(r"(REG|STACK|SHARED|LOCAL):(\d+)", line))
            usage[current] = f"REG {fields.get('REG')}, STACK {fields.get('STACK')}, LOCAL {fields.get('LOCAL')}"
    return usage


def lines_by_source(cuobjdump: str, nvdisasm: str, path: str, opcodes: list[str]) -> dict[tuple[str, str], Counter]:
    per_function = {}
    with tempfile.TemporaryDirectory() as elf_dir:
        subprocess.run(
            [cuobjdump, "-xelf", "all", os.path.abspath(path)], cwd=elf_dir, capture_output=True, check=False
        )
        for cubin in sorted(glob.glob(os.path.join(elf_dir, "*.cubin"))) or [path]:
            arch = re.search(r"\.(sm_\d+)\w*\.cubin$", cubin)
            per_function.update(cubin_lines_by_source(nvdisasm, cubin, opcodes, arch.group(1) if arch else ""))
    return per_function


def cubin_lines_by_source(nvdisasm: str, path: str, opcodes: list[str], arch: str) -> dict[tuple[str, str], Counter]:
    text = subprocess.run([nvdisasm, "--print-line-info", path], capture_output=True, text=True, check=False).stdout
    per_function, function, source = {}, None, "unknown"
    for line in text.splitlines():
        header = re.match(r"\s*\.text\.(\S+):", line)
        if header:
            function, source = (arch, header.group(1)), "unknown"
            per_function[function] = Counter()
            continue
        located = re.match(r'\s*//## File "(.+)", line (\d+)', line)
        if located:
            source = f"{os.path.basename(located.group(1))}:{located.group(2)}"
            continue
        if function and re.match(r"\s*/\*[0-9a-f]{4,}\*/", line):
            instruction = re.sub(r"^@!?U?P[T0-9]+\s+", "", line.split("*/", 1)[-1].strip())
            opcode = instruction.split(" ")[0]
            if any(opcode == prefix or opcode.startswith(prefix + ".") for prefix in opcodes):
                per_function[function][source] += 1
    return per_function


def count_opcodes(lines: list[str], opcodes: list[str]) -> Counter:
    counts = Counter()
    for line in lines:
        instruction = line.split("*/", 1)[-1].strip()
        opcode = re.sub(r"^@!?U?P[T0-9]+\s+", "", instruction).split(" ")[0]
        if opcode.startswith("HGMMA."):
            counts[opcode] += 1
            continue
        for prefix in opcodes:
            if opcode == prefix or opcode.startswith(prefix + "."):
                counts[prefix] += 1
    return counts


def names_in_cubin_match(path: str, pattern: str) -> bool:
    with open(path, "rb") as cubin:
        strings = cubin.read().decode("latin-1").split("\0")
    return any(re.search(pattern, string) for string in strings)


def main():
    args = parse_args()
    opcodes = list(dict.fromkeys(list(DEFAULT_OPCODES) + list(args.extra)))
    for path in find_binaries(args.paths):
        if args.kernel and path.endswith(".cubin") and not names_in_cubin_match(path, args.kernel):
            continue
        sass = subprocess.run([args.cuobjdump, "-sass", path], capture_output=True, text=True, check=False).stdout
        functions = split_functions(sass)
        if args.kernel:
            functions = {key: lines for key, lines in functions.items() if re.search(args.kernel, key[1])}
        if not functions:
            continue
        usage = resource_usage(args.cuobjdump, path)
        by_line = lines_by_source(args.cuobjdump, args.nvdisasm, path, args.by_line) if args.by_line else {}
        several_archs = len({arch for arch, _ in functions}) > 1
        for (arch, name), lines in functions.items():
            counts = count_opcodes(lines, opcodes)
            title = f"{name} ({arch})" if several_archs else name
            resources = usage.get((arch, name)) or usage.get(("", name), "resource usage not found")
            print(f"### {title}\n\n`{path}`\n\n{resources}, {len(lines)} instructions\n")
            print("| opcode | count |\n|---|---|")
            for opcode in sorted(k for k in counts if k.startswith("HGMMA")) + opcodes:
                if counts.get(opcode):
                    print(f"| `{opcode}` | {counts[opcode]} |")
            print()
            if args.by_line:
                print(f"| source line | {' / '.join(args.by_line)} |\n|---|---|")
                lines_counter = by_line.get((arch, name)) or by_line.get(("", name), Counter())
                for source, count in lines_counter.most_common():
                    print(f"| `{source}` | {count} |")
                print()


if __name__ == "__main__":
    main()
