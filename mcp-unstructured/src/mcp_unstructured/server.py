import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from mcp_unstructured.parser import parse_file, health


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        try:
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))

            tool = data.get("tool")
            if tool == "parse_file":
                path = data.get("path")
                if not path:
                    raise ValueError("Missing required field: path")
                result = parse_file(
                    path=path,
                    route=data.get("route", "auto"),
                    chunking_strategy=data.get("chunking_strategy", "basic"),
                    vlm_mode=data.get("vlm_mode", False),
                    vlm_model_provider=data.get("vlm_model_provider"),
                    vlm_model=data.get("vlm_model"),
                )
            elif tool == "health":
                result = health()
            elif tool == "tools":
                result = {
                    "tools": [
                        {
                            "name": "parse_file",
                            "description": "Parse a local document with Unstructured. "
                                           "Set vlm_mode=true to use the hosted Unstructured VLM API.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "route": {"type": "string", "default": "auto"},
                                    "chunking_strategy": {"type": "string", "default": "basic"},
                                    "vlm_mode": {"type": "boolean", "default": False},
                                    "vlm_model_provider": {"type": "string"},
                                    "vlm_model": {"type": "string"},
                                },
                                "required": ["path"],
                            },
                        },
                        {
                            "name": "health",
                            "description": "Return server health and capability flags.",
                            "input_schema": {"type": "object", "properties": {}},
                        },
                    ]
                }
            else:
                raise ValueError("Unknown tool")

            payload = json.dumps({"result": result}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        except Exception as e:
            payload = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


def run_http(port=8000):
    print(f"Server running on port {port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    run_http()
