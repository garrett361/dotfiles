# Viewing a remote trace in a local browser

Status: CORS file-server path verified end to end on 2026-09-24 (Slurm login node, Perfetto UI stable
v58.3-11fbaed83, user on macOS with Vivaldi over Tailscale ssh). A last-step-trimmed trace (2 MB gzipped,
34 MB JSON) loads by URL in about 4 s; the untrimmed 5-step trace (20 MB gzipped, 405 MB JSON) loads too,
but takes tens of seconds (single-threaded in-browser JSON parsing, roughly 8 to 9 MB/s). The optional
native trace processor path was verified on 2026-10-06 (see its section).

## Setting

The agent runs on a remote machine; the user is on a laptop that reaches it with plain `ssh` (over
Tailscale). The user runs one ssh command and opens one URL; no file transfer.

## Constraint that shapes everything: the UI's CSP

`ui.perfetto.dev` sets a Content Security Policy whose `connect-src` allows plain-http loopback only at
`http://127.0.0.1:9001` (plus `http://localhost:8080`). Any other `http://127.0.0.1:<port>` is blocked by
the browser. So the laptop side must be port 9001; the remote side can use any free port, because the ssh
forward maps laptop 9001 to it.

## Recipe (verified): serve a trimmed trace with CORS

0. Trim first. In-browser parsing runs at roughly 8 to 9 MB of JSON per second, so keep only the step being
   analyzed:
   `python3 <skill dir>/scripts/trim_last_step.py trace_0.json.gz trace_0_laststep.json.gz`
   (gzipped output loads fine by URL; no need to decompress).

1. The server is `scripts/serve_cors.py` (stdlib only). Set `INV=~/tmp/profiling/<investigation>` and put
   symlinks to the files to view in `$INV/serve/`. Its core:

   ```python
   import functools, http.server, sys

   class CORSHandler(http.server.SimpleHTTPRequestHandler):
       def end_headers(self):
           self.send_header("Access-Control-Allow-Origin", "https://ui.perfetto.dev")
           super().end_headers()

   port, directory = int(sys.argv[1]), sys.argv[2]
   handler = functools.partial(CORSHandler, directory=directory)
   http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
   ```

2. Pick a remote port (prefer 9001). `serve_cors.py` exits at once with `Address already in use` if the port
   is taken on the shared login node; pick another remote port then.

3. Start it in the background next to the trace directory, recording the PID:

   ```bash
   nohup python3 <skill dir>/scripts/serve_cors.py "$PORT" "$INV/serve" > "$INV/server.log" 2>&1 &
   echo $! > "$INV/server.pid"
   ```

4. Check it: `curl -sS -D - -o /dev/null http://127.0.0.1:$PORT/$FILE` must show `200 OK` and
   `Access-Control-Allow-Origin: https://ui.perfetto.dev`.

5. Print for the user (fill in `<host>` only if known, see Gotchas; the laptop side is always 9001):

   ```
   ssh -N -L 9001:127.0.0.1:<PORT> <host>
   https://ui.perfetto.dev/#!/?url=http://127.0.0.1:9001/<FILE>
   ```

   Ask them to keep the ssh command running while viewing, and to report whether the trace loaded.

6. Stop: `kill "$(cat "$INV/server.pid")"`, then `curl http://127.0.0.1:$PORT/` should be refused.

## Optional: native trace_processor for big traces

The CORS recipe above is the default. Switch to Perfetto's native trace processor only when a trace is too
big for the in-browser parser (e.g. a full multi-step or full-model trace; a 405 MB JSON trace took tens of
seconds in the browser). It parses on the remote machine and the UI queries it over RPC. Verified end to end
on 2026-10-06 (Slurm login node, Vivaldi on macOS over Tailscale ssh).

1. Start it with `scripts/serve_trace_processor.py` (runs in an ephemeral `uv` env; the `perfetto` package
   downloads the matching `trace_processor_shell` binary on first use):

   ```bash
   uv run --script <skill dir>/scripts/serve_trace_processor.py <trace.json.gz> --port 9002 --state-dir "$INV"
   ```

   It prints the ssh forward, a UI URL pinned to the binary's version, and the stop command.
2. The user points the laptop's 9001 at it: `ssh -N -L 9001:127.0.0.1:9002 <host>`. Only one of the CORS
   server and the trace processor can sit behind laptop port 9001 at a time (the UI's CSP allows only
   `127.0.0.1:9001`), so this replaces the CORS tunnel while in use.
3. The user opens the printed `https://ui.perfetto.dev/<version>/` URL with no `?url=` and chooses "YES, use
   loaded trace" in the native-acceleration dialog.

Notes:
- The live UI is often newer than the binary the `perfetto` package fetches; opening plain
  `ui.perfetto.dev` then shows a "Version mismatch" dialog. The version-pinned URL avoids it.
- Chromium browsers need local-network access allowed for `ui.perfetto.dev`, or the UI's `POST /status`
  probe is blocked and no dialog appears.
- A stale `?url=` in the tab (e.g. from history) makes the UI fetch a file instead of probing; the trace
  processor answers 404. Open the pinned URL fresh.
- It loads one trace as is: to compare arms, serve a merged file from `scripts/merge_traces.py`.
- The same engine runs headless from Python (`perfetto.trace_processor.TraceProcessor`) for SQL over the
  standard tables; a possible backend for the analysis scripts.

## Gotchas

- The ssh host: on the verified node `hostname -f` returned only a short name (`prime`) and there is no
  `tailscale` CLI, so the user's Tailscale name or ssh alias is not discoverable from the remote side.
  Print `<host>` as a placeholder and ask for it.
- Bind to `127.0.0.1` only (verified unreachable via the node's LAN IP). On a shared login node, other
  users on that node can still read the served directory, so serve only the trace directory.
- The static server answers the UI's `POST /status` probe with 501, so the UI does not mistake it for a
  trace processor.
- `pkill -f <pattern>` run from an agent shell can match and kill that shell itself, because the pattern
  appears on its own command line. Stop by saved PID.
- Debug from the server log first: it shows whether the browser's requests arrive at all. If `curl` on the
  laptop gets 200 through the tunnel but the log shows no browser GET, the browser is blocking the fetch.
- Chromium browsers (verified: Vivaldi) apply Local Network Access to an https page fetching `127.0.0.1`.
  DevTools reports the UI's `status` probe as blocked; that is harmless for this path, since the trace GETs
  still go through.
- Each load does GET, `POST /status` (501), then GET again; the first GET may end in a `BrokenPipeError`
  traceback in the server log. Harmless: the UI abandons the first download and refetches.
- Perfetto's JSON importer silently drops events with negative timestamps: anything before an anchor
  shifted to t = 0 vanishes (verified: markers starting before the anchor never showed until shifted).
  `scripts/merge_traces.py` shifts all arms so the earliest event is at 0. Check a file with the SQL page:
  `select min(ts), max(ts), count(*) from slice`. Metadata (`ph: "M"`) events need no `ts`; a stale one
  from the run's start can stretch the timeline by minutes.
- Chrome-JSON async events with a plain `id` are global: Perfetto groups them by name under "Global Legacy
  Events" across processes. Put per-process markers on a thread track instead.
- Find markers and annotations programmatically on the "Query (SQL)" page, e.g.
  `select s.ts, s.dur, s.name, p.name from slice s join thread_track tt on s.track_id = tt.id join thread
  t using (utid) join process p using (upid) where s.name like 'FSDP::%' order by s.ts`; the `stats` table
  (`where value > 0`) lists import errors and dropped events. The omnibox searches slice names too.
- Perfetto caches a trace by its URL: after regenerating a file, reloading the same URL shows the old trace
  (the server log shows only `POST /status`, no GET). Write regenerated traces under a new name (e.g. `_v2`).
- A console error about `perfetto-gae-internal.googleplex.com/.../manifest` is the UI failing to fetch a
  Google-internal extension; unrelated to the trace.

## Not yet verified

- Safari and Firefox on the laptop side.
- trace_processor memory use and load time on full-model (43-layer, 8-node) traces.
- The size limit for the in-browser path: 405 MB of JSON loaded in tens of seconds; larger is untested.
