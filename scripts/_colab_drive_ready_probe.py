from pathlib import Path

mydrive = Path("/content/drive/MyDrive")
models = mydrive / "voicebox-models"
data = mydrive / "voicebox-data"
db = data / "voicebox.db"

real_mount = mydrive.exists() and not mydrive.is_symlink()
models_ready = models.is_dir()
data_ready = db.is_file() and db.stat().st_size > 0
write_ready = False
probe = data / ".voicebox-persistence-probe"
try:
    if data.is_dir():
        probe.write_text("persistent", encoding="utf-8")
        write_ready = probe.read_text(encoding="utf-8") == "persistent"
finally:
    probe.unlink(missing_ok=True)

print("GOOGLE_DRIVE_REAL", real_mount)
print("REMOTE_MODELS_READY", models_ready)
print("REMOTE_DATA_READY", data_ready)
print("REMOTE_WRITE_READY", write_ready)
if not (real_mount and models_ready and data_ready and write_ready):
    raise SystemExit(2)
print("REMOTE_DRIVE_READY")
