import json
import subprocess
from pathlib import Path

import requests


def test_stdio(project_dir: str, file_path: str):
    proc = subprocess.Popen(
        ["python", "server.py"],
        cwd=project_dir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    request = {
        "tool": "parse_file",
        "path": file_path,
        "route": "auto",
        "chunking_strategy": "by_title",
        "return_elements": True,
        "cleaning_config": {
            "use_clean": True,
            "extra_whitespace": True,
            "group_broken_paragraphs": True,
            "replace_unicode_quotes": True,
        },
    }

    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()

    response = proc.stdout.readline().strip()
    proc.terminate()
    return json.loads(response)


def test_http(file_path: str, port: int = 8000):
    payload = {
        "tool": "partition",
        "path": file_path,
        "route": "auto",
        "include_coordinates": False,
    }
    response = requests.post(f"http://localhost:{port}", json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    sample = str(here / "sample.pdf")
    print("STDIO:", test_stdio(str(here), sample))
