from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_windows_build_recipe_builds_mcp_shim():
    source = _source("justfile")
    assert "backend/build_binary.py --shim" in source
    assert "voicebox-mcp-$triple.exe" in source


def test_absolute_date_uses_server_utc_normalization():
    source = _source("app/src/lib/utils/format.ts")
    assert "function parseServerDate" in source
    assert "const dateObj = parseServerDate(date);" in source


def test_avatar_upload_accepts_missing_filename():
    source = _source("backend/routes/profiles.py")
    expected = 'NamedTemporaryFile(delete=False, suffix=Path(file.filename or "").suffix)'
    assert expected in source


def test_export_filenames_include_generation_id():
    backend = _source("backend/routes/history.py")
    frontend = _source("app/src/lib/hooks/useHistory.ts")
    assert "{generation_id[:8]}" in backend
    assert "generationId.substring(0, 8)" in frontend


def test_story_list_batches_item_counts():
    source = _source("backend/services/stories.py")
    assert ".group_by(DBStoryItem.story_id)" in source
    assert "item_counts.get(story.id, 0)" in source


def test_tauri_runtime_is_at_least_2_11_1():
    import re

    lock = _source("tauri/src-tauri/Cargo.lock")
    match = re.search(r'name = "tauri"\nversion = "(\d+)\.(\d+)\.(\d+)"', lock)
    assert match is not None
    version = tuple(int(part) for part in match.groups())
    assert version >= (2, 11, 1)
