#!/usr/bin/env python3
"""Tiny static server for local dashboard preview. Serves this folder on :8765."""
import http.server
import os
import socketserver

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765
with socketserver.TCPServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"serving {os.getcwd()} on http://127.0.0.1:{PORT}", flush=True)
    httpd.serve_forever()
