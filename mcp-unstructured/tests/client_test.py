import requests

SERVER_URL = "http://localhost:8000"


def test_parse_file(path: str, vlm_mode: bool = False, vlm_model_provider: str | None = None, vlm_model: str | None = None):
    payload = {"tool": "parse_file", "path": path, "vlm_mode": vlm_mode}
    if vlm_model_provider:
        payload["vlm_model_provider"] = vlm_model_provider
    if vlm_model:
        payload["vlm_model"] = vlm_model

    r = requests.post(
        SERVER_URL,
        json=payload,
        timeout=180 if not vlm_mode else 600,
    )
    print(r.status_code)
    print(r.text[:1000])


def test_health():
    r = requests.post(SERVER_URL, json={"tool": "health"}, timeout=30)
    print(r.status_code)
    print(r.text)


def test_tools():
    r = requests.post(SERVER_URL, json={"tool": "tools"}, timeout=30)
    print(r.status_code)
    print(r.text)
