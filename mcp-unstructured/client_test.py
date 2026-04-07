import requests


def test_parse_file(path: str):
    r = requests.post("http://localhost:8000", json={
        "tool": "parse_file",
        "path": path
    }, timeout=180)
    print(r.status_code)
    print(r.text[:1000])


def test_health():
    r = requests.post("http://localhost:8000", json={"tool": "health"}, timeout=30)
    print(r.status_code)
    print(r.text)
