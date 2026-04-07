import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from parser import parse_file


def handle_request(data):
    if data.get("tool") == "parse_file":
        return parse_file(data["path"])
    else:
        raise ValueError("Unknown tool")


def run_stdio():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = handle_request(request)
            print(json.dumps({"result": result}))
        except Exception as e:
            print(json.dumps({"error": str(e)}))


class MCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers["Content-Length"])
            body = self.rfile.read(length)
            request = json.loads(body)

            result = handle_request(request)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"result": result}).encode())

        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())


def run_http(port=8000):
    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    print(f"HTTP MCP server running on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if mode == "http":
        run_http()
    else:
        run_stdio()
