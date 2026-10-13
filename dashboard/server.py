"""Lightweight observatory server for the Argus Free Model Benchmark Dashboard.

Serves static UI assets and exposes live telemetry JSON endpoints.
Runs with zero external dependencies (Python standard library only).
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import subprocess
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_JSON = os.path.join(BASE_DIR, "data", "free_model_benchmarks.json")
LOG_FILE = os.path.join(BASE_DIR, "data", "benchmark_runner.log")
PID_FILE = os.path.join(BASE_DIR, "data", "benchmark_runner.pid")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/telemetry":
            self.handle_telemetry()
        elif self.path == "/api/logs":
            self.handle_logs()
        elif self.path == "/api/runner-status":
            self.handle_runner_status()
        else:
            # Fall back to static files in STATIC_DIR
            if self.path == "/" or not os.path.exists(os.path.join(STATIC_DIR, self.path.lstrip("/"))):
                self.path = "/index.html"
            super().do_GET()

    def handle_telemetry(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

        if os.path.isfile(DATA_JSON):
            try:
                with open(DATA_JSON, "r", encoding="utf-8") as f:
                    content = f.read()
                self.wfile.write(content.encode("utf-8"))
                return
            except Exception as e:
                err = json.dumps({"error": f"Failed to read telemetry: {e}"})
                self.wfile.write(err.encode("utf-8"))
                return

        # If file not ready yet, return placeholder state
        resp = {
            "status": "initializing",
            "message": "Benchmark runner is currently executing round 1. Data will appear once the round completes.",
            "rounds": [],
            "total_rounds_configured": 5,
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_logs(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

        lines = []
        if os.path.isfile(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                    lines = [ln.strip() for ln in all_lines[-60:]]
            except Exception as e:
                lines = [f"Error reading log file: {e}"]

        resp = {"logs": lines}
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_runner_status(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        is_running = False
        pid = None
        if os.path.isfile(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid_str = f.read().strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    # Check if process is alive
                    res = subprocess.run(["kill", "-0", str(pid)], capture_output=True)
                    is_running = (res.returncode == 0)
            except Exception:
                pass

        resp = {
            "is_running": is_running,
            "pid": pid,
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def log_message(self, format, *args):
        # Silence verbose GET log spam in terminal
        pass


def run_server(port=8085):
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"Argus Observatory Dashboard active at http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8085
    run_server(port)
