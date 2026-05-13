# ============================================================
# Voicebox Colab Full Restore
# Restores backend + model cache + data dir + Cloudflare tunnel
# ============================================================

import os
import sys
import re
import json
import time
import shutil
import socket
import subprocess
from pathlib import Path

import requests

# ----------------------------
# User-configurable constants
# ----------------------------

REPO_URL = "https://github.com/insane66613/voicebox.git"
BRANCH = "fix-remote-proxy-desktop-mode"

REPO_DIR = Path("/content/voicebox")
PORT = 17493

# Known good profile for smoke test / status reference.
ZAY_PROFILE_ID = "e4ba7e03-0123-48e6-9d2b-104fa8e7cf25"

# Persistent Drive folders.
DATA_FOLDER_NAME = "voicebox-data"
MODELS_FOLDER_NAME = "voicebox-models"
LOG_FOLDER_NAME = "voicebox-logs"
OUTPUTS_FOLDER_NAME = "voicebox-outputs"

# Leave this False for normal restore.
# Set True only if Drive model loading becomes slow/stuck and you want to stage models to /content SSD.
USE_LOCAL_MODEL_CACHE_COPY = False

# Models to copy to local SSD if USE_LOCAL_MODEL_CACHE_COPY=True.
LOCAL_COPY_MODEL_DIRS = [
    "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base",
    "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base",
    "models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice",
]

# ----------------------------
# Helpers
# ----------------------------

def run(cmd, check=False, env=None, cwd=None, tail=8000):
    print(f"\n$ {cmd}")
    p = subprocess.run(
        cmd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    out = p.stdout or ""
    print(out[-tail:])
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed with code {p.returncode}: {cmd}")
    return p

def wait_http_json(url, timeout=10):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

def kill_old_processes():
    print("\n=== Stop old backend / tunnel processes ===")
    run(f"fuser -k {PORT}/tcp || true")
    run("pkill -f 'backend.server' || true")
    run("pkill -f 'backend/server.py' || true")
    run("pkill -f 'voicebox-server-cuda' || true")
    run("pkill -f cloudflared || true")
    time.sleep(3)

def detect_my_drive():
    candidates = [
        Path("/content/gdrive_real_1778701776/MyDrive"),
        Path("/content/drive/MyDrive"),
    ]

    for p in candidates:
        if p.exists():
            return p

    print("\n=== Mount Google Drive ===")
    from google.colab import drive
    drive.mount("/content/drive", force_remount=False)

    if Path("/content/gdrive_real_1778701776/MyDrive").exists():
        return Path("/content/gdrive_real_1778701776/MyDrive")
    if Path("/content/drive/MyDrive").exists():
        return Path("/content/drive/MyDrive")

    raise RuntimeError("Could not find Google Drive MyDrive after mount.")

def ensure_repo():
    print("\n=== Restore Voicebox repo ===")

    if not REPO_DIR.exists():
        run(f'git clone --branch "{BRANCH}" "{REPO_URL}" "{REPO_DIR}"', check=True)
    else:
        run("git status --short || true", cwd=REPO_DIR)
        run("git fetch --all --prune", cwd=REPO_DIR, check=False)
        run(f'git checkout "{BRANCH}"', cwd=REPO_DIR, check=True)
        run(f'git pull --ff-only origin "{BRANCH}"', cwd=REPO_DIR, check=False)

    run("git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD", cwd=REPO_DIR, check=False)

def install_backend_deps():
    print("\n=== Install / repair Python dependencies ===")

    # Avoid --force-reinstall because it previously disturbed Colab requests/fsspec/numpy.
    # huggingface_hub 1.x breaks the current transformers range.
    run(f'{sys.executable} -m pip install -q --no-deps "huggingface-hub>=0.34.0,<1.0"', check=True)

    # Install project requirements if present.
    req_candidates = [
        REPO_DIR / "requirements.txt",
        REPO_DIR / "backend" / "requirements.txt",
    ]

    for req in req_candidates:
        if req.exists():
            print(f"Installing requirements from {req}")
            run(f'{sys.executable} -m pip install -q -r "{req}"', check=False)

    # Editable install if the repo exposes pyproject/setup.py.
    if (REPO_DIR / "pyproject.toml").exists() or (REPO_DIR / "setup.py").exists():
        run(f'{sys.executable} -m pip install -q -e "{REPO_DIR}"', check=False)

    print("\n=== Version sanity ===")
    run(
        f"""{sys.executable} - <<'PY'
import sys
print("python", sys.version)

mods = [
    "torch",
    "transformers",
    "huggingface_hub",
    "fastapi",
    "uvicorn",
]
for m in mods:
    try:
        mod = __import__(m)
        print(m, getattr(mod, "__version__", "unknown"))
    except Exception as e:
        print(m, "IMPORT_FAIL", repr(e))

try:
    import torch
    print("torch.cuda.is_available", torch.cuda.is_available())
    print("torch.cuda.device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("torch.cuda.device_name", torch.cuda.get_device_name(0))
except Exception as e:
    print("torch cuda check failed", repr(e))
PY""",
        check=False,
    )

def prepare_dirs(my_drive):
    print("\n=== Prepare persistent directories ===")

    data_dir = my_drive / DATA_FOLDER_NAME
    drive_models_dir = my_drive / MODELS_FOLDER_NAME
    log_dir = my_drive / LOG_FOLDER_NAME
    outputs_dir = my_drive / OUTPUTS_FOLDER_NAME

    for p in [data_dir, drive_models_dir, log_dir, outputs_dir]:
        p.mkdir(parents=True, exist_ok=True)
        print(p)

    models_dir = drive_models_dir

    if USE_LOCAL_MODEL_CACHE_COPY:
        print("\n=== Stage selected models to local SSD ===")
        local_models = Path("/content/voicebox-models-local")
        local_models.mkdir(parents=True, exist_ok=True)

        for name in LOCAL_COPY_MODEL_DIRS:
            src = drive_models_dir / name
            dst = local_models / name

            if not src.exists():
                print(f"SKIP missing model cache dir: {src}")
                continue

            print(f"\nCopying {name}")
            if dst.exists():
                shutil.rmtree(dst)

            shutil.copytree(src, dst, symlinks=False)
            run(f'du -sh "{dst}" || true')

        models_dir = local_models

    return data_dir, models_dir, log_dir, outputs_dir

def validate_cache(models_dir):
    print("\n=== Validate model cache ===")
    print("MODELS_DIR:", models_dir)

    qwen_17 = models_dir / "models--Qwen--Qwen3-TTS-12Hz-1.7B-Base"
    checks = [
        qwen_17,
        qwen_17 / "snapshots",
        qwen_17 / "blobs",
    ]

    for p in checks:
        print(f"{p}: exists={p.exists()}")

    # Detect the repaired flattened/snapshot files.
    if qwen_17.exists():
        found_safetensors = list(qwen_17.rglob("model.safetensors"))
        print(f"Qwen 1.7B model.safetensors files found: {len(found_safetensors)}")
        for f in found_safetensors[:10]:
            try:
                print(
                    " -",
                    f,
                    "is_file=",
                    f.is_file(),
                    "is_symlink=",
                    f.is_symlink(),
                    "size=",
                    f.stat().st_size if f.exists() else None,
                )
            except Exception as e:
                print(" -", f, "stat failed", repr(e))

def start_backend(data_dir, models_dir, log_dir, my_drive):
    print("\n=== Start PyTorch CUDA-capable backend ===")

    server_log = log_dir / "voicebox-server.log"
    server_log.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_DIR)
    env["VOICEBOX_MODELS_DIR"] = str(models_dir)
    env["HF_HUB_CACHE"] = str(models_dir)
    env["HUGGINGFACE_HUB_CACHE"] = str(models_dir)
    env["HF_HOME"] = str(my_drive / "voicebox-hf-home")
    env["TORCH_HOME"] = str(my_drive / "voicebox-torch-home")

    # Important: do not force the Windows CUDA sidecar variant in Colab.
    env.pop("TRANSFORMERS_CACHE", None)
    env.pop("VOICEBOX_BACKEND_VARIANT", None)

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "backend.server",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--data-dir",
        str(data_dir),
    ]

    print("CMD:", " ".join(cmd))
    print("DATA_DIR:", data_dir)
    print("MODELS_DIR:", models_dir)
    print("SERVER_LOG:", server_log)

    log_fh = open(server_log, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_DIR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    base = f"http://127.0.0.1:{PORT}"

    for i in range(120):
        try:
            r = requests.get(f"{base}/health", timeout=10)
            print(f"backend attempt {i+1}: {r.status_code} {r.text[:500]}")
            if r.status_code == 200:
                break
        except Exception as e:
            print(f"backend attempt {i+1}: {repr(e)}")
        time.sleep(2)
    else:
        print("\n=== Backend log tail ===")
        print(server_log.read_text(errors="ignore")[-16000:])
        raise RuntimeError("Backend did not become healthy.")

    return base, server_log

def backend_smoke_checks(base):
    print("\n=== Backend smoke checks ===")

    try:
        print("\n--- clear tasks ---")
        print(requests.post(f"{base}/tasks/clear", timeout=30).text[:1000])
    except Exception as e:
        print("clear tasks failed:", repr(e))

    for endpoint in ["/health", "/models/cache-dir", "/models/status", "/profiles", "/tasks/active"]:
        print(f"\n--- {endpoint} ---")
        try:
            r = requests.get(f"{base}{endpoint}", timeout=30)
            print("HTTP", r.status_code)
            txt = r.text
            if endpoint == "/models/status":
                data = r.json()
                for m in data.get("models", []):
                    if "qwen" in m.get("model_name", "").lower():
                        print(
                            m.get("model_name"),
                            "downloaded=",
                            m.get("downloaded"),
                            "loaded=",
                            m.get("loaded"),
                            "size_mb=",
                            m.get("size_mb"),
                        )
            else:
                print(txt[:3000])
        except Exception as e:
            print(endpoint, "failed:", repr(e))

    print("\n--- nvidia-smi ---")
    run("nvidia-smi || true", check=False, tail=12000)

def ensure_cloudflared():
    print("\n=== Ensure cloudflared binary ===")

    cf = Path("/content/cloudflared")

    if not cf.exists():
        run(
            "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /content/cloudflared",
            check=True,
        )
        run("chmod +x /content/cloudflared", check=True)

    run("/content/cloudflared --version || true", check=False)
    return cf

def start_cloudflare_tunnel(log_dir):
    print("\n=== Start Cloudflare tunnel ===")

    tunnel_log = log_dir / "cloudflared.log"
    tunnel_log.write_text("", encoding="utf-8")

    run("pkill -f cloudflared || true")
    time.sleep(2)

    run(f'nohup /content/cloudflared tunnel --url http://127.0.0.1:{PORT} > "{tunnel_log}" 2>&1 &')

    url = None

    print("\n=== Waiting for trycloudflare URL ===")
    for i in range(90):
        time.sleep(2)
        text = tunnel_log.read_text(errors="ignore")
        matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", text)
        if matches:
            url = matches[-1]
            print("Found URL:", url)
            break
        print(f"wait-url {i+1}/90")

    if not url:
        print("\n=== cloudflared log tail ===")
        print(tunnel_log.read_text(errors="ignore")[-8000:])
        raise RuntimeError("No trycloudflare URL found.")

    print("\n=== Wait for tunnel DNS/reachability ===")
    for i in range(60):
        try:
            host = url.replace("https://", "").strip("/")
            socket.getaddrinfo(host, 443)
            r = requests.get(f"{url}/health", timeout=20)
            print(f"tunnel attempt {i+1}: HTTP {r.status_code} {r.text[:500]}")
            if r.status_code == 200:
                p = requests.get(f"{url}/profiles", timeout=20)
                print("profiles:", p.status_code, p.text[:1000])
                return url, tunnel_log
        except Exception as e:
            print(f"tunnel attempt {i+1}: not ready: {repr(e)}")

        time.sleep(5)

    print("\n=== cloudflared log tail ===")
    print(tunnel_log.read_text(errors="ignore")[-8000:])
    raise RuntimeError(f"Tunnel URL was printed but never became reachable: {url}")

def print_windows_proxy_block(tunnel_url):
    print("\n" + "=" * 88)
    print("RESTORE COMPLETE")
    print("=" * 88)

    print("\nBACKEND:")
    print(f"http://127.0.0.1:{PORT}")

    print("\nCLOUDFLARE:")
    print(tunnel_url)

    print("\nDESKTOP SETTINGS:")
    print("Server Mode:        Remote / proxy server")
    print("Local helper proxy: Enabled")
    print(f"Proxy upstream URL: {tunnel_url}")
    print("Server URL:         http://127.0.0.1:17493")

    print("\nWINDOWS POWERSHELL BLOCK:")
    print(rf'''
$Upstream = "{tunnel_url}"

Write-Host "`n=== Update local Voicebox helper proxy upstream ==="
Invoke-RestMethod `
  -Method Put `
  -Uri "http://127.0.0.1:17493/_proxy/upstream" `
  -ContentType "application/json" `
  -Body (@{{ upstream_url = $Upstream }} | ConvertTo-Json)

Write-Host "`n=== Proxy status ==="
Invoke-RestMethod "http://127.0.0.1:17493/_proxy/status" |
  ConvertTo-Json -Depth 8

Write-Host "`n=== Health through local proxy ==="
Invoke-RestMethod "http://127.0.0.1:17493/health" |
  ConvertTo-Json -Depth 8

Write-Host "`n=== Profiles through local proxy ==="
Invoke-RestMethod "http://127.0.0.1:17493/profiles" |
  ConvertTo-Json -Depth 8

Pause
''')

def optional_direct_generation_test(base):
    print("\n=== Optional direct generation test ===")
    print("Skipping automatic generation by default.")
    print("Run this manually if you want to warm-load Qwen 1.7B immediately:")
    print(f'''
import requests, json, time

BASE = "{base}"

payload = {{
    "profile_id": "{ZAY_PROFILE_ID}",
    "text": "Hello. This is a short Voicebox restore test.",
    "language": "en",
    "engine": "qwen",
    "model_size": "1.7B",
    "effects_chain": None,
    "personality": False,
    "max_chunk_chars": 180,
    "crossfade_ms": 0,
    "normalize": True,
}}

r = requests.post(f"{{BASE}}/generate", json=payload, timeout=120)
print(r.status_code)
print(r.text[:2000])
''')

# ----------------------------
# Main restore flow
# ----------------------------

print("=" * 88)
print("VOICEBOX COLAB FULL RESTORE")
print("=" * 88)

MY_DRIVE = detect_my_drive()
print("\nMY_DRIVE:", MY_DRIVE)

kill_old_processes()
ensure_repo()
install_backend_deps()

DATA_DIR, MODELS_DIR, LOG_DIR, OUTPUTS_DIR = prepare_dirs(MY_DRIVE)
validate_cache(MODELS_DIR)

BASE, SERVER_LOG = start_backend(DATA_DIR, MODELS_DIR, LOG_DIR, MY_DRIVE)
backend_smoke_checks(BASE)

ensure_cloudflared()
TUNNEL_URL, TUNNEL_LOG = start_cloudflare_tunnel(LOG_DIR)

print_windows_proxy_block(TUNNEL_URL)
optional_direct_generation_test(BASE)
