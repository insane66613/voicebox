import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

RESTORE = Path(__file__).resolve().parents[1] / "backend" / "colab_restore.py"

def load_functions():
    tree = ast.parse(RESTORE.read_text(encoding="utf-8"))
    body = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(RESTORE), "exec"), ns)
    return ns

def response(status, data):
    return SimpleNamespace(status_code=status, text=json.dumps(data), json=lambda: data)

@pytest.mark.parametrize("health,profiles", [
    (response(403, {}), response(200, [])),
    (response(200, {"status": "healthy"}), response(500, {})),
    (response(200, {"status": "healthy"}), response(200, {})),
])
def test_tunnel_rejects_unusable_backend(tmp_path, health, profiles):
    ns = load_functions()
    ns.update(CF_TUNNEL_TOKEN="test", CF_TUNNEL_NAME="", CF_DOMAIN="example.test",
              CF_SAVE_CERT_TO_DRIVE=False, run=lambda *a, **k: None)
    ns["time"] = SimpleNamespace(sleep=lambda _: None)
    ns["socket"] = SimpleNamespace(getaddrinfo=lambda *a: [])
    ns["requests"] = SimpleNamespace(get=lambda url, **k: health if url.endswith("/health") else profiles)
    with pytest.raises(RuntimeError):
        ns["start_cloudflare_tunnel"](tmp_path)

def test_tunnel_accepts_healthy_backend_with_profile_list(tmp_path):
    ns = load_functions()
    ns.update(CF_TUNNEL_TOKEN="test", CF_TUNNEL_NAME="", CF_DOMAIN="example.test",
              CF_SAVE_CERT_TO_DRIVE=False, run=lambda *a, **k: None)
    ns["time"] = SimpleNamespace(sleep=lambda _: None)
    ns["socket"] = SimpleNamespace(getaddrinfo=lambda *a: [])
    ns["requests"] = SimpleNamespace(get=lambda url, **k:
        response(200, {"status": "healthy"}) if url.endswith("/health") else response(200, []))
    assert ns["start_cloudflare_tunnel"](tmp_path)[0] == "https://example.test"

def test_backend_exit_stops_readiness_polling(tmp_path):
    ns = load_functions()
    ns.update(REPO_DIR=tmp_path, PORT=17493)
    ns["subprocess"] = SimpleNamespace(Popen=lambda *a, **k: SimpleNamespace(poll=lambda: 1), STDOUT=-2)
    ns["time"] = SimpleNamespace(sleep=lambda _: None)
    get = Mock(side_effect=ConnectionError("not listening"))
    ns["requests"] = SimpleNamespace(get=get)
    with pytest.raises(RuntimeError):
        ns["start_backend"](tmp_path, tmp_path, tmp_path, tmp_path)
    assert get.call_count == 0, "Exited child must fail before any readiness requests"
