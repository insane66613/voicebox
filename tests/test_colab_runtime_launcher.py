from pathlib import Path
import re


def test_runtime_launcher_contract():
    launcher = Path("scripts/start_voicebox_colab_runtime.ps1")
    assert launcher.exists(), "runtime launcher must exist"
    text = launcher.read_text(encoding="utf-8")
    assert "tauri" in text and "VITE_VOICEBOX_REMOTE_UPSTREAM_URL" in text
    assert "voicebox.ptelectronics.net" not in text
    assert "_colab_poll_probe.py" in text
    assert "voicebox_remote_proxy.py" in text
    assert "anonymous Colab assignment" in text


def test_remote_bundle_installer_contract():
    installer = Path("scripts/_colab_install_runtime_bundle.py")
    assert installer.exists(), "remote bundle installer must exist"
    text = installer.read_text(encoding="utf-8")
    assert "/content/voicebox-backend.zip" in text
    assert "/content/voicebox" in text
    assert "/content/drive/MyDrive" in text
    assert "is_mount()" in text
    assert 'os.symlink("/content"' not in text
    assert 'Path("/content", name)' not in text


def test_runtime_bundle_excludes_local_artifacts():
    text = Path("scripts/start_voicebox_colab_runtime.ps1").read_text(encoding="utf-8")
    assert "robocopy" in text.lower()
    for excluded in ["venv", "build", "dist", "__pycache__", ".pytest_cache", "tests"]:
        assert excluded in text


def test_new_colab_runtime_requires_remote_google_drive_state():
    text = Path("scripts/start_voicebox_colab_runtime.ps1").read_text(encoding="utf-8")
    assert r"X:\Drive\voicebox-data" not in text
    assert "voicebox-persistent-data.zip" not in text
    assert "_colab_restore_persistent_data.py" not in text
    assert "_colab_drive_ready_probe.py" in text
    assert "Google Drive" in text


def test_drive_probe_rejects_ephemeral_my_drive():
    text = Path("scripts/_colab_drive_ready_probe.py").read_text(encoding="utf-8")
    assert "is_symlink" in text
    assert "voicebox-models" in text
    assert "voicebox-data" in text


def test_drive_runtime_logs_are_not_truncated_on_restart():
    live = Path("scripts/colab_live_repair.py").read_text(encoding="utf-8")
    assert 'open(server_log, "a")' in live
    assert 'open(cf_log, "a")' in live
    assert "cf_log_start" in live
    assert "seek(cf_log_start)" in live

    restore = Path("backend/colab_restore.py").read_text(encoding="utf-8")
    assert 'server_log.write_text(""' not in restore
    assert 'tunnel_log.write_text(""' not in restore
    assert re.search(r'(?<!>)> "\{tunnel_log\}"', restore) is None
    assert 'VOICEBOX_REQUIRE_PERSISTENT_ROOT' in restore
    assert 'VOICEBOX_REQUIRE_MOUNTPOINT' in restore
    assert "tunnel_log_start" in restore
    assert "seek(tunnel_log_start)" in restore


def test_runtime_launcher_retries_transient_colab_transport_failures():
    text = Path("scripts/start_voicebox_colab_runtime.ps1").read_text(encoding="utf-8")
    assert "Invoke-ColabWithRetry" in text
    assert "503" in text
    assert "upload" in text
    assert "MaxAttempts" in text


def test_new_session_allocation_does_not_wait_forever_for_colab_new():
    text = Path("scripts/start_voicebox_colab_runtime.ps1").read_text(encoding="utf-8")
    block = text.split("function Ensure-ColabSession", 1)[1].split("function Get-LiveTunnel", 1)[0]
    assert "Start-Process" in block
    assert "Invoke-Colab @('sessions')" in block
    assert "Stop-Process" in block


def test_colab_invocations_have_local_wall_clock_timeout():
    text = Path("scripts/start_voicebox_colab_runtime.ps1").read_text(encoding="utf-8")
    block = text.split("function Invoke-Colab", 1)[1].split("function Invoke-ColabWithRetry", 1)[0]
    assert "LocalTimeoutSeconds" in block
    assert "WaitForExit" in block
    assert ".Kill($true)" in block
    assert "local timeout" in block.lower()


def test_live_tunnel_probe_reads_persistent_drive_log():
    text = Path("scripts/_colab_poll_probe.py").read_text(encoding="utf-8")
    assert "/content/drive/MyDrive/voicebox-logs/cloudflared.log" in text
    assert "/content/voicebox-logs/cloudflared.log" not in text
