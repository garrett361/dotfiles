"""Put Python sites from a hooked run onto costs from an unhooked trace, joining `find_syncs.py --dump` rows by position.

The sync sequence of a steady-state step repeats run to run, so the k-th sync point on the main thread (and on the
other threads) of one dump is the k-th of the other. The join refuses to run if the per-thread counts differ and
reports how many rows disagree on the op chain, which should be zero. Sites print sorted by unhooked exposed GPU idle.

Usage: python3 join_sync_dumps.py <unhooked_dump.json> <hooked_dump.json>
"""

import argparse
import json
import re
from collections import defaultdict

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("unhooked", help="`find_syncs.py --dump` rows from the unhooked trace (costs)")
parser.add_argument("hooked", help="`find_syncs.py --dump --stacks` rows from the hooked run (Python sites)")
args = parser.parse_args()
costs, labels = json.load(open(args.unhooked)), json.load(open(args.hooked))


def op_chain(ops):
    return re.sub(r"^\[[^\]]*\] ", "", ops)


def by_thread(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["main_thread"]].append(r)
    return out


c, h = by_thread(costs), by_thread(labels)
if {t: len(v) for t, v in c.items()} != {t: len(v) for t, v in h.items()}:
    raise SystemExit(f"per-thread sync counts differ: {[(t, len(v)) for t, v in c.items()]} vs "
                     f"{[(t, len(v)) for t, v in h.items()]}")
mismatches = 0
sites = defaultdict(lambda: {"n": 0, "host": 0.0, "idle": 0.0, "exposed": 0.0, "hooked_exposed": 0.0, "max_host": 0.0,
                             "ops": None})
for thread in c:
    for a, b in zip(c[thread], h[thread]):
        mismatches += op_chain(a["ops"]) != op_chain(b["ops"])
        s = sites[(thread, b["label"])]
        s["n"] += 1
        s["host"] += a["host_us"]
        s["idle"] += a["idle_us"]
        s["exposed"] += a["exposed_us"]
        s["hooked_exposed"] += b["exposed_us"]
        s["max_host"] = max(s["max_host"], a["host_us"])
        s["ops"] = op_chain(a["ops"])
print(f"op chain mismatches: {mismatches} of {len(costs)}; exposed GPU idle: unhooked "
      f"{sum(r['exposed_us'] for r in costs) / 1e3:.2f} ms, hooked {sum(r['exposed_us'] for r in labels) / 1e3:.2f} ms")
print(f"{'n':>4} {'exposed':>8} {'idle@ret':>8} {'host ms':>8} {'max host':>9} {'hooked exp':>10}  thread  site")
for (thread, label), s in sorted(sites.items(), key=lambda kv: (-kv[1]["exposed"], -kv[1]["host"])):
    print(f"{s['n']:4d} {s['exposed'] / 1e3:8.2f} {s['idle'] / 1e3:8.2f} {s['host'] / 1e3:8.2f} {s['max_host'] / 1e3:9.2f} "
          f"{s['hooked_exposed'] / 1e3:10.2f}  {'main' if thread else 'other'}    {label}")
    print(f"{'':59}ops: {s['ops']}")
