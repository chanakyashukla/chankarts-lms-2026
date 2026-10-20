#!/usr/bin/env python3
"""
ChankArts Music Academy - Frontend Development Server
Run this to preview the frontend locally.
"""
import http.server
import socketserver
import os
from pathlib import Path

PORT = 3000
FRONTEND_DIR = Path(__file__).parent / "frontend"

os.chdir(FRONTEND_DIR)

class AcademyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Serve index.html for SPA routes
        if not Path(self.path).suffix and self.path != '/':
            self.path = '/index.html'
        return super().do_GET()
    
    def end_headers(self):
        # Add CORS headers for development
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), AcademyHandler) as httpd:
        print(f"ChankArts Academy Frontend")
        print(f"Running at: http://localhost:{PORT}/academy/")
        print(f"Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
