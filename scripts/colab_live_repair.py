import os, re, subprocess, sys, time
from pathlib import Path
import requests

print("LIVE_REPAIR_20260915_START", sys.version)
pkgs = [
    "qwen-tts==0.1.1", "transformers==4.57.3", "huggingface-hub==0.36.2",
    "fastmcp>=3.0,<4.0", "sse-starlette>=2.0", "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0", "pydantic>=2.5.0", "sqlalchemy>=2.0.0",
    "alembic>=1.13.0", "python-multipart>=0.0.6", "httpx>=0.27.0", "pedalboard==0.9.24", "Pillow>=10.0.0",
]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", *pkgs], check=True)
subprocess.run([
    sys.executable, "-c",
    "import fastmcp, transformers, huggingface_hub; "
    "from qwen_tts import Qwen3TTSModel; "
    "from backend.app import app; "
    "print('CORE_IMPORTS_OK', transformers.__version__, huggingface_hub.__version__)",
], cwd="/content/voicebox", env={**os.environ, "PYTHONPATH":"/content/voicebox"}, check=True)

md = Path("/content/drive/MyDrive")
for dirname in ("voicebox-data", "voicebox-models", "voicebox-hf-home", "voicebox-torch-home", "voicebox-logs"):
    (md / dirname).mkdir(parents=True, exist_ok=True)
subprocess.run("pkill -f 'backend.server' || true", shell=True)
env = os.environ.copy()
env.update({"PYTHONPATH":"/content/voicebox", "VOICEBOX_MODELS_DIR":str(md/"voicebox-models"),
            "HF_HUB_CACHE":str(md/"voicebox-models"), "HUGGINGFACE_HUB_CACHE":str(md/"voicebox-models"),
            "HF_HOME":str(md/"voicebox-hf-home"), "TORCH_HOME":str(md/"voicebox-torch-home"),
            "VOICEBOX_REQUIRE_PERSISTENT_ROOT":str(md), "VOICEBOX_REQUIRE_MOUNTPOINT":"/content/drive"})
env.pop("TRANSFORMERS_CACHE", None); env.pop("VOICEBOX_BACKEND_VARIANT", None)
server_log = md / "voicebox-logs" / "voicebox-server.log"
log = open(server_log, "a")
subprocess.Popen([sys.executable,"-u","-m","backend.server","--host","0.0.0.0","--port","17493",
                  "--data-dir",str(md/"voicebox-data")], cwd="/content/voicebox", env=env,
                 stdout=log, stderr=subprocess.STDOUT)
for _ in range(90):
    try:
        h = requests.get("http://127.0.0.1:17493/health", timeout=3)
        if h.status_code == 200:
            print("LOCAL_HEALTH_OK", h.text); break
    except Exception: pass
    time.sleep(2)
else:
    raise RuntimeError(server_log.read_text(errors="ignore")[-12000:])

cf = Path("/content/cloudflared")
if not cf.exists():
    subprocess.run("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /content/cloudflared && chmod +x /content/cloudflared", shell=True, check=True)
subprocess.run("pkill -f cloudflared || true", shell=True); time.sleep(2)
cf_log = md / "voicebox-logs" / "cloudflared.log"
cf_log_start = cf_log.stat().st_size if cf_log.exists() else 0
cfh = open(cf_log, "a")
subprocess.Popen([str(cf),"tunnel","--url","http://127.0.0.1:17493"], stdout=cfh, stderr=subprocess.STDOUT)
url = None
for _ in range(60):
    time.sleep(2)
    with cf_log.open("r", errors="ignore") as reader:
        reader.seek(cf_log_start)
        current_run_log = reader.read()
    matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", current_run_log)
    if matches:
        url = matches[-1]; break
if not url:
    raise RuntimeError(cf_log.read_text(errors="ignore")[-8000:])
print("TUNNEL_URL", url)
for _ in range(60):
    try:
        h = requests.get(url + "/health", timeout=10)
        if h.status_code == 200:
            p = requests.get(url + "/profiles", timeout=10)
            print("REMOTE_HEALTH_OK", h.text)
            print("REMOTE_PROFILES_STATUS", p.status_code)
            break
    except Exception: pass
    time.sleep(3)
else:
    raise RuntimeError("quick tunnel never became reachable")
print("LIVE_REPAIR_20260915_DONE")
