# /// script
# requires-python = ">=3.10"
# dependencies = ["perfetto"]
# ///
"""Serve a trace with Perfetto's native trace_processor for the Perfetto UI, as an alternative to serve_cors.py.

Use for traces too large for the in-browser parser (full multi-step or full-model traces). The perfetto
package fetches the matching trace_processor_shell binary on first use into ~/.local/share/perfetto. The
server runs in the background, bound to localhost, with its PID written next to the log. It prints the ssh
forward (the UI only talks to laptop port 9001) and a UI URL pinned to the binary's version, which avoids
the UI's version-mismatch dialog. Stop it with `kill "$(cat <pid file>)"`.

Usage:
  uv run --script serve_trace_processor.py <trace.json.gz> --port 9002 --state-dir ~/tmp/profiling/<investigation>
"""

import argparse
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from perfetto.trace_processor.platform import PlatformDelegate


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trace")
    parser.add_argument("--port", type=int, default=9002, help="remote port to serve on (laptop side is always 9001)")
    parser.add_argument("--state-dir", required=True, help="where to write trace_processor.log and .pid")
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds to wait for the trace to load")
    return parser.parse_args()


def main():
    args = parse_args()
    trace = Path(args.trace).expanduser().resolve()
    state = Path(args.state_dir).expanduser()
    state.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    binary = PlatformDelegate().get_shell_path(bin_path=None)
    version = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout
    version_code = re.search(r"v\d+\.\d+-[0-9a-f]+", version).group(0)
    log, pid_file = state / "trace_processor.log", state / "trace_processor.pid"
    with open(log, "w") as out:
        proc = subprocess.Popen(
            [binary, "--httpd", "--http-port", str(args.port), str(trace)], stdout=out, stderr=subprocess.STDOUT
        )
    pid_file.write_text(str(proc.pid))
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"trace_processor exited with {proc.returncode}; see {log}")
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{args.port}/status", method="POST")
            if urllib.request.urlopen(request, timeout=2).status == 200:
                break
        except OSError:
            time.sleep(2)
    else:
        raise SystemExit(f"trace_processor did not answer within {args.timeout:.0f} s; see {log}")
    print(f"serving {trace} with trace_processor {version_code} on 127.0.0.1:{args.port} (pid {proc.pid}, {pid_file})")
    print(f"laptop: ssh -N -L 9001:127.0.0.1:{args.port} <host>")
    print(f"then open https://ui.perfetto.dev/{version_code}/ and choose 'YES, use loaded trace'")
    print(f'stop: kill "$(cat {pid_file})"')


if __name__ == "__main__":
    main()
