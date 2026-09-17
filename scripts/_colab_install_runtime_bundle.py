import shutil
import zipfile
from pathlib import Path

archive = Path("/content/voicebox-backend.zip")
repo = Path("/content/voicebox")
drive_mount = Path("/content/drive")
my_drive = drive_mount / "MyDrive"

if not archive.exists():
    raise FileNotFoundError(archive)
if not drive_mount.is_mount():
    raise RuntimeError("/content/drive is not a real mounted filesystem")
if not my_drive.is_dir() or my_drive.is_symlink():
    raise RuntimeError("/content/drive/MyDrive is not a real Drive directory")

if repo.exists():
    shutil.rmtree(repo)
repo.mkdir(parents=True)
with zipfile.ZipFile(archive) as bundle:
    bundle.extractall(repo)
if not (repo / "backend" / "server.py").exists():
    raise RuntimeError("runtime bundle did not contain backend/server.py")

for name in ["voicebox-logs", "voicebox-data", "voicebox-models", "voicebox-hf-home", "voicebox-torch-home"]:
    (my_drive / name).mkdir(parents=True, exist_ok=True)
print("VOICEBOX_RUNTIME_BUNDLE_INSTALLED")
