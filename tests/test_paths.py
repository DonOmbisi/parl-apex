from core.paths import resolve_data_path, resolve_sqlite_url


def test_resolve_data_path_uses_configured_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    assert resolve_data_path("data/graphs/acme.db") == str(tmp_path / "graphs" / "acme.db")
    assert resolve_data_path("graphs/acme.db") == str(tmp_path / "graphs" / "acme.db")


def test_resolve_sqlite_url_creates_parent_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    url = resolve_sqlite_url("sqlite+aiosqlite:///./data/app.db")

    assert url == f"sqlite+aiosqlite:///{(tmp_path / 'app.db').as_posix()}"
    assert tmp_path.exists()
