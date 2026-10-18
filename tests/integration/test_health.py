from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


@contextmanager
def _shell(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AIRA_MODEL", raising=False)
    monkeypatch.delenv("AIRA_DATA_DIR", raising=False)
    with TestClient(
        create_app(
            frontend_dir=tmp_path,
            data_dir=tmp_path / "data",
            env_file=tmp_path / "missing.env",
        )
    ) as client:
        yield client


def test_liveness_is_available_without_credentials(monkeypatch, tmp_path):
    with _shell(tmp_path, monkeypatch) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_unconfigured_application_never_reports_ready(monkeypatch, tmp_path):
    with _shell(tmp_path, monkeypatch) as client:
        for _ in range(3):
            response = client.get("/health/ready")
            assert response.status_code == 503
            body = response.json()
            assert body["ready"] is False
            assert body["provider"]["status"] == "unverified"
            assert any("OPENAI_API_KEY" in item for item in body["missing_prerequisites"])
        assert client.post("/api/assessments", json={}).status_code == 422


def test_built_ui_and_health_share_one_origin(monkeypatch, tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>Aira test build</h1>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("export const app = 'aira';")
    with _shell(tmp_path, monkeypatch) as client:
        assert "Aira test build" in client.get("/").text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        missing_route = client.get("/api/unknown")
        assert missing_route.status_code == 404
        assert missing_route.headers["X-Request-ID"].startswith("req-")
        assert client.get("/../pyproject.toml").status_code == 404
