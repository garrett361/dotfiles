# /// script
# requires-python = ">=3.10"
# ///
"""Diff the kernel artifacts two arms compiled: are the SASS / PTX / TTIR identical, and if not, how do they differ?

Takes two directories, each a `CUTE_DSL_DUMP_DIR` written with `CUTE_DSL_KEEP=sass` (or `ptx`), a Triton cache
(`$TRITON_CACHE_DIR`), or a mix, and compares every `.sass`, `.ptx` and `.ttir` file under them, matched by file
name. Prints one markdown row per artifact name: identical, differing (with the count of changed lines), or
present in one arm only, then a table of the changed instructions with register numbers normalized, so a diff
that only swaps a constant operand (`FADD R1, R2, 1` vs `FADD R1, RZ, R2`) reads as one row per opcode pattern;
patterns that only renumber registers cancel out.

Artifacts are normalized before comparison, so two worktrees of the same code compare equal:
- SASS: the `/*0a10*/` address and encoding comments and `.reuse` flags are dropped.
- PTX: `.loc` and `.file` directives, `//` comments, and everything from the first `.section .debug` on (the
  DWARF bytes embed source paths) are dropped.
- TTIR: `loc(...)` attributes and `#loc` lines are dropped.

Triton caches hold one file per specialization under the same name (e.g. four `_triton_swiglu_fwd.ptx`), so the
files sharing a name are compared as a multiset of normalized contents, not pairwise in directory order. CuTe DSL
4.8 names dumps after the host function and its argument types, truncated to 180 characters with object
addresses removed, so two specializations of one kernel class can share a name and the later compile overwrites
the earlier dump: a `CUTE_DSL_DUMP_DIR` holds one variant per name. Dump each configuration of interest into its
own directory if every variant matters.

Usage:
  uv run --script artifact_diff.py A_DIR B_DIR [--ext .sass .ptx .ttir] [--kernel REGEX] [--show N]

--kernel keeps artifact names matching REGEX; --show prints up to N changed-instruction patterns (default 20).
Exits 1 when any artifact differs or is present in one arm only.
"""

import argparse
import collections
import hashlib
import os
import re
import sys

SASS_ADDR = re.compile(r"/\*[0-9a-f]{4,}\*/")
PTX_DROP = re.compile(r"^\s*\.(loc|file)\b.*$|//.*$", re.MULTILINE)
TTIR_DROP = re.compile(r"\s*loc\((?:[^()]|\([^()]*\))*\)|^#loc.*$", re.MULTILINE)
REGISTER = re.compile(r"\b(R|UR|P|UP)\d+\b|(%[a-z]+)\d+")


def normalize(path):
    with open(path, errors="replace") as f:
        text = f.read()
    if path.endswith(".sass"):
        text = SASS_ADDR.sub("", text).replace(".reuse", "")
    elif path.endswith(".ptx"):
        text = PTX_DROP.sub("", text.split("\t.section\t.debug")[0])
    elif path.endswith(".ttir"):
        text = TTIR_DROP.sub("", text)
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def collect(root, exts, kernel):
    found = collections.defaultdict(list)
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.endswith(tuple(exts)) and (kernel is None or kernel.search(name)):
                found[name].append(os.path.join(dirpath, name))
    return found


def digest(lines):
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def changed_lines(a_lines, b_lines):
    a_count = collections.Counter(a_lines)
    b_count = collections.Counter(b_lines)
    removed = a_count - b_count
    added = b_count - a_count
    return removed, added


def pattern(line):
    line = re.sub(r"\s+", " ", line.strip().rstrip(";").strip())
    return REGISTER.sub(lambda m: m.group(1) or m.group(2), line)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("a_dir")
    parser.add_argument("b_dir")
    parser.add_argument("--ext", nargs="+", default=[".sass", ".ptx", ".ttir"])
    parser.add_argument("--kernel", type=re.compile, default=None)
    parser.add_argument("--show", type=int, default=20)
    args = parser.parse_args()

    a = collect(args.a_dir, args.ext, args.kernel)
    b = collect(args.b_dir, args.ext, args.kernel)
    a_patterns = collections.Counter()
    b_patterns = collections.Counter()
    rows = []
    for name in sorted(set(a) | set(b)):
        if name not in a or name not in b:
            rows.append((name, "only in " + ("A" if name in a else "B"), ""))
            continue
        a_norm = [normalize(p) for p in a[name]]
        b_norm = [normalize(p) for p in b[name]]
        if sorted(map(digest, a_norm)) == sorted(map(digest, b_norm)):
            rows.append((name, "identical", f"{len(a_norm)}"))
            continue
        a_all = [line for lines in a_norm for line in lines]
        b_all = [line for lines in b_norm for line in lines]
        removed, added = changed_lines(a_all, b_all)
        for line, count in removed.items():
            a_patterns[pattern(line)] += count
        for line, count in added.items():
            b_patterns[pattern(line)] += count
        result = (
            f"differs: -{sum(removed.values())} +{sum(added.values())} lines,"
            f" {len(a_all)} vs {len(b_all)} total"
        )
        rows.append((name, result, f"{len(a_norm)}/{len(b_norm)}"))
    patterns = collections.Counter(
        {f"A: {k}": v for k, v in (a_patterns - b_patterns).items()}
        | {f"B: {k}": v for k, v in (b_patterns - a_patterns).items()}
    )

    print(f"A: {args.a_dir}\nB: {args.b_dir}\n")
    print("| artifact | result | files A/B |")
    print("|---|---|---|")
    for name, result, files in rows:
        short = name if len(name) <= 100 else name[:97] + "..."
        print(f"| `{short}` | {result} | {files} |")
    summary = collections.Counter(r[1].split(":")[0] for r in rows)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(summary.items())))
    if patterns:
        print("\n| changed instruction (registers normalized) | count |")
        print("|---|---|")
        for line, count in patterns.most_common(args.show):
            print(f"| `{line}` | {count} |")
    sys.exit(0 if all(r[1] == "identical" for r in rows) else 1)


if __name__ == "__main__":
    main()
