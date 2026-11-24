# /// script
# requires-python = ">=3.10"
# ///
"""Sample one node's NFS client throughput for a mount from /proc/self/mountstats, while a phase reads or writes.

Answers "how much is this node actually reading from the file server, with how many requests in flight, and how
long does each take", next to per-rank phase times: a per-rank read rate far below the node's NFS rate means time
goes outside I/O (decode, copies, waits), and a node rate flat while RPC latency climbs means the server or network
is the limit. Counters are the client's (all processes on the node), so run one sampler per node, e.g. with
`srun --overlap --ntasks-per-node=1` beside the job.

Every --interval seconds it prints a CSV row: unix time, READ and WRITE MB/s (wire bytes of those RPCs), READ and
WRITE RPCs per second, mean READ RPC round trip and execute ms (execute includes client queueing), and the mean READ
RPCs in flight over the interval (Little's law: READ execute seconds per second). Stops after --seconds (0: never).

Usage: uv run --script nfs_sampler.py [--mount /home] [--interval 1] [--seconds 0] > node.csv
"""

import argparse
import time


def read_counters(mount):
    counters = {}
    inside = False
    with open("/proc/self/mountstats") as f:
        for line in f:
            if line.startswith("device "):
                inside = f" mounted on {mount} " in line
                continue
            if not inside:
                continue
            fields = line.split()
            if fields and fields[0] in ("READ:", "WRITE:") and len(fields) >= 9:
                ops, _, _, sent, received, _, rtt, execute = (int(v) for v in fields[1:9])
                counters[fields[0][:-1]] = (ops, sent, received, rtt, execute)
    if not counters:
        raise SystemExit(f"no NFS per-op statistics for {mount} in /proc/self/mountstats")
    return counters


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mount", default="/home")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=0.0)
    args = parser.parse_args()

    print("time,read_mb_s,write_mb_s,read_ops_s,write_ops_s,read_rtt_ms,read_exe_ms,read_in_flight", flush=True)
    start = time.time()
    previous, previous_t = read_counters(args.mount), time.time()
    while not args.seconds or time.time() - start < args.seconds:
        time.sleep(args.interval)
        current, now = read_counters(args.mount), time.time()
        dt = now - previous_t
        r0, r1 = previous["READ"], current["READ"]
        w0, w1 = previous["WRITE"], current["WRITE"]
        read_ops, write_ops = r1[0] - r0[0], w1[0] - w0[0]
        read_mb = (r1[2] - r0[2]) / 1e6
        write_mb = (w1[1] - w0[1]) / 1e6
        rtt = (r1[3] - r0[3]) / read_ops if read_ops else 0.0
        execute = (r1[4] - r0[4]) / read_ops if read_ops else 0.0
        in_flight = (r1[4] - r0[4]) / 1e3 / dt
        print(
            f"{now:.1f},{read_mb / dt:.1f},{write_mb / dt:.1f},{read_ops / dt:.1f},{write_ops / dt:.1f},"
            f"{rtt:.2f},{execute:.2f},{in_flight:.1f}",
            flush=True,
        )
        previous, previous_t = current, now


if __name__ == "__main__":
    main()
