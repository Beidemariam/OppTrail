from fastapi.testclient import TestClient

import app.main

SECRET = "TOP SECRET - outside the static build"
INDEX = "<html>opptrail</html>"


def build_static_dir(tmp_path):
    """Mirror the container layout: static build beside the database file."""
    static_dir = tmp_path / "app" / "frontend-out"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(INDEX)
    (static_dir / "favicon.ico").write_text("icon")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "app.db").write_text(SECRET)
    (tmp_path / "secret.txt").write_text(SECRET)
    return static_dir


def test_static_route_serves_files_inside_the_build(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    static_dir = build_static_dir(tmp_path)
    monkeypatch.setattr(app.main, "frontend_dir", static_dir)

    assert client.get("/index.html").text == INDEX
    assert client.get("/favicon.ico").text == "icon"
    # Unknown client-side routes fall back to the SPA entry point.
    assert client.get("/dashboard").text == INDEX


def test_static_route_refuses_to_escape_the_build_directory(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    static_dir = build_static_dir(tmp_path)
    monkeypatch.setattr(app.main, "frontend_dir", static_dir)

    traversals = [
        "/%2e%2e/secret.txt",
        "/../secret.txt",
        "/%2e%2e/%2e%2e/data/app.db",
        "/%2e%2e%2f%2e%2e%2fdata/app.db",
        "/static/%2e%2e/%2e%2e/%2e%2e/data/app.db",
        "/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
    ]
    for path in traversals:
        response = client.get(path)
        assert SECRET not in response.text, f"{path} escaped the static directory"
        assert "root:" not in response.text, f"{path} escaped the static directory"
