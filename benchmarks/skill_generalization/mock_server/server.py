"""
Simple HTTP Server for Evil Benchmark Pages
=============================================

Serves the compiled HTML pages and provides a JSON API for ground truth.

Usage:
    python server.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PAGES_DIR = Path(__file__).resolve().parent / "pages"


def serve(environ, start_response):
    """WSGI application for serving benchmark pages."""
    path = environ.get("PATH_INFO", "/")
    query_string = environ.get("QUERY_STRING", "")
    params = parse_qs(query_string)
    
    # Health check
    if path == "/" or path == "/health":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"status": "ok", "pages": len(list(PAGES_DIR.glob("*.html")))}).encode()]
    
    # Ground truth API
    if path == "/api/truth":
        template = params.get("template", [""])[0]
        variant = params.get("variant", [""])[0]
        
        if not template or not variant:
            start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [json.dumps({"error": "template and variant required"}).encode()]
        
        truth_path = PAGES_DIR / "ground_truth.json"
        if truth_path.exists():
            ground_truth = json.loads(truth_path.read_text())
            key = f"{template}:{variant}"
            data = ground_truth.get(key)
            if data:
                start_response("200 OK", [("Content-Type", "application/json")])
                return [json.dumps({"template": template, "variant": variant, "ground_truth": data}).encode()]
        
        start_response("404 Not Found", [("Content-Type", "application/json")])
        return [json.dumps({"error": "not found"}).encode()]
    
    # List pages
    if path == "/api/pages":
        pages = []
        for f in sorted(PAGES_DIR.glob("*.html")):
            if f.name != "ground_truth.json":
                parts = f.stem.rsplit("_", 1)
                if len(parts) == 2:
                    pages.append({"template": parts[0], "variant": parts[1], "file": f.name})
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"pages": pages}).encode()]
    
    # Serve HTML page
    if path.endswith(".html"):
        filename = path.lstrip("/")
        filepath = PAGES_DIR / filename
        if filepath.exists():
            content = filepath.read_bytes()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [content]
    
    # Try to serve a specific page by template + variant
    template = params.get("template", [""])[0]
    variant = params.get("variant", [""])[0]
    if template and variant:
        safe_variant = variant.replace("/", "_SLASH_")
        filename = f"{template}_{safe_variant}.html"
        filepath = PAGES_DIR / filename
        if filepath.exists():
            content = filepath.read_bytes()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [content]
    
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Page not found"]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    
    host = os.environ.get("BENCHMARK_HOST", "0.0.0.0")
    port = int(os.environ.get("BENCHMARK_PORT", "9999"))
    
    httpd = make_server(host, port, serve)
    print(f"Evil Benchmark Server running on http://{host}:{port}")
    print(f"Serving {len(list(PAGES_DIR.glob('*.html')))} pages from {PAGES_DIR}")
    print(f"API endpoints:")
    print(f"  GET /health")
    print(f"  GET /api/pages")
    print(f"  GET /api/truth?template=<name>&variant=<name>")
    print(f"  GET /<page>.html")
    print(f"\nPress Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
