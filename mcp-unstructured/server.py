import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from parser import parse_file, health

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))

            tool = data.get("tool")
            if tool == "parse_file":
                result = parse_file(data["path"], data.get("route","auto"))
            elif tool == "health":
                result = health()
            else:
                raise ValueError("Unknown tool")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"result": result}).encode())

        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

def run_http(port=8000):
    print(f"Server running {port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

if __name__ == "__main__":
    run_http()
