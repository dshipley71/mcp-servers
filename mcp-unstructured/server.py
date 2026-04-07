import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from parser import parse_file, partition_file


def handle_request(data):
    tool = data.get("tool")

    if tool == "parse_file":
        return parse_file(
            path=data["path"],
            route=data.get("route", "auto"),
            max_characters=data.get("max_characters", 1000),
            new_after_n_chars=data.get("new_after_n_chars", 1000),
            overlap=data.get("overlap", 0),
            ocr_languages=data.get("ocr_languages"),
            hi_res_model_name=data.get("hi_res_model_name"),
            ocr_agent=data.get("ocr_agent"),
            include_coordinates=data.get("include_coordinates", False),
            return_elements=data.get("return_elements", False),
            cleaning_config=data.get("cleaning_config"),
            chunking_strategy=data.get("chunking_strategy", "basic"),
            combine_text_under_n_chars=data.get("combine_text_under_n_chars", 0),
            multipage_sections=data.get("multipage_sections", True),
        )

    if tool == "partition":
        result = partition_file(
            path=data["path"],
            route=data.get("route", "auto"),
            ocr_languages=data.get("ocr_languages"),
            hi_res_model_name=data.get("hi_res_model_name"),
            ocr_agent=data.get("ocr_agent"),
            include_coordinates=data.get("include_coordinates", False),
        )
        result.pop("_raw_elements", None)
        return result

    raise ValueError("Unknown tool")


def run_stdio():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = handle_request(request)
            print(json.dumps({"result": result}), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


class MCPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        try:
            length = int(self.headers["Content-Length"])
            body = self.rfile.read(length)
            request = json.loads(body)

            result = handle_request(request)

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
    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    print(f"HTTP MCP server running on port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if mode == "http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        run_http(port=port)
    else:
        run_stdio()
