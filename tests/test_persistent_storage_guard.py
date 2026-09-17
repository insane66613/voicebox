from pathlib import Path

import pytest

from backend import config


def _configure(monkeypatch, root: Path, mount: Path, models: Path):
    monkeypatch.setenv("VOICEBOX_REQUIRE_PERSISTENT_ROOT", str(root))
    monkeypatch.setenv("VOICEBOX_REQUIRE_MOUNTPOINT", str(mount))
    monkeypatch.setenv("VOICEBOX_MODELS_DIR", str(models))


def test_guard_rejects_ephemeral_data_dir(monkeypatch, tmp_path):
    mount = tmp_path / "drive"
    root = mount / "MyDrive"
    models = root / "voicebox-models"
    _configure(monkeypatch, root, mount, models)
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    with pytest.raises(RuntimeError, match="persistent root"):
        config.validate_persistent_storage(tmp_path / "ephemeral-data")


def test_guard_rejects_non_mount_drive(monkeypatch, tmp_path):
    mount = tmp_path / "drive"
    root = mount / "MyDrive"
    _configure(monkeypatch, root, mount, root / "voicebox-models")
    monkeypatch.setattr(Path, "is_mount", lambda self: False)

    with pytest.raises(RuntimeError, match="not mounted"):
        config.validate_persistent_storage(root / "voicebox-data")


def test_guard_accepts_drive_backed_data_and_models(monkeypatch, tmp_path):
    mount = tmp_path / "drive"
    root = mount / "MyDrive"
    _configure(monkeypatch, root, mount, root / "voicebox-models")
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    config.validate_persistent_storage(root / "voicebox-data")


def test_colab_runtime_enables_backend_persistence_guard():
    text = Path("scripts/colab_live_repair.py").read_text(encoding="utf-8")
    assert "VOICEBOX_REQUIRE_PERSISTENT_ROOT" in text
    assert "VOICEBOX_REQUIRE_MOUNTPOINT" in text


def test_drive_readiness_probe_verifies_write_access():
    text = Path("scripts/_colab_drive_ready_probe.py").read_text(encoding="utf-8")
    assert ".voicebox-persistence-probe" in text
    assert "write_text" in text
    assert "unlink" in text
