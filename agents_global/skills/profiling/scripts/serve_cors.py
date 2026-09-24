"""Serve a directory on 127.0.0.1 with a CORS header for https://ui.perfetto.dev. Usage: python3 serve_cors.py <port> <dir>"""

import functools, http.server, sys

class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "https://ui.perfetto.dev")
        super().end_headers()

port, directory = int(sys.argv[1]), sys.argv[2]
handler = functools.partial(CORSHandler, directory=directory)
http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
