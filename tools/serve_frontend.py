#!/usr/bin/env python3
"""serve_frontend.py - Serve frontend_dist_files on port 8081"""
import os
import sys
import http.server
import socketserver

PORT = 8081
DIR = sys.argv[1] if len(sys.argv) > 1 else "frontend_dist_files"
os.chdir(DIR)
print(f"[serve_frontend] cwd={os.getcwd()}, port={PORT}", flush=True)

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # CORS
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def log_message(self, format, *args):
        print(f"[serve_frontend] {self.address_string()} - {format%args}", flush=True)

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"[serve_frontend] serving on 0.0.0.0:{PORT}", flush=True)
    httpd.serve_forever()
