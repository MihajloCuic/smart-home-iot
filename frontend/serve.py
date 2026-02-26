#!/usr/bin/env python3
"""Simple HTTP server to serve the Smart Home IoT frontend."""
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8080

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"[FRONTEND] Serving on http://0.0.0.0:{PORT}")
HTTPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler).serve_forever()
