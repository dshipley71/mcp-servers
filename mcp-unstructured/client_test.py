import subprocess
import json
import requests


def test_stdio():
    proc = subprocess.Popen(
        ["python", "server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    request = {
        "tool": "parse_file",
        "path": "sample.pdf"
    }

    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()

    response = proc.stdout.readline()
    print("STDIO:", response)


def test_http():
    response = requests.post(
        "http://localhost:8000",
        json={
            "tool": "parse_file",
            "path": "sample.pdf"
        }
    )
    print("HTTP:", response.json())


if __name__ == "__main__":
    test_stdio()
