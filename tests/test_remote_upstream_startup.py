from pathlib import Path


def test_remote_startup_does_not_silently_fallback_to_stable_hostname():
    source = (Path(__file__).parents[1] / "app" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "VITE_VOICEBOX_REMOTE_UPSTREAM_URL" in source
    assert "|| 'https://voicebox.ptelectronics.net'" not in source


def test_launcher_upstream_wins_and_is_synced_into_ui_store():
    source = (Path(__file__).parents[1] / "app" / "src" / "App.tsx").read_text(encoding="utf-8")
    env_pos = source.index("import.meta.env.VITE_VOICEBOX_REMOTE_UPSTREAM_URL")
    store_pos = source.index("serverStore.proxyUpstreamUrl?.trim()", env_pos)
    assert env_pos < store_pos
    assert "serverStore.setProxyUpstreamUrl(upstream)" in source


def test_remote_proxy_connection_is_labeled_explicitly():
    source = (Path(__file__).parents[1] / "app" / "src" / "components" / "ServerTab" / "GeneralPage.tsx").read_text(encoding="utf-8")
    assert "REMOTE VIA PROXY" in source
