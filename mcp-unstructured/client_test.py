import requests

def test(path):
    r = requests.post("http://localhost:8000", json={
        "tool":"parse_file",
        "path": path
    })
    print(r.status_code)
    print(r.text[:1000])

def health():
    print(requests.post("http://localhost:8000", json={"tool":"health"}).json())
