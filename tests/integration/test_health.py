from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_is_available_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    client = TestClient(create_app(frontend_dir=tmp_path))
    assert client.get("/health/live").json() == {"status": "ok", "service": "aira"}
    assert client.get("/health/live").status_code == 200


def test_unimplemented_assessments_never_report_ready(tmp_path):
    client = TestClient(create_app(frontend_dir=tmp_path))
    for _ in range(3):
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "reasons": ["Assessment processing is not available in this build."],
            "provider_verification": "unverified",
        }
    assert client.post("/api/assessments", json={}).status_code == 404


def test_built_ui_and_health_share_one_origin(tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>Aira test build</h1>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("export const app = 'aira';")
    client = TestClient(create_app(frontend_dir=tmp_path))
    assert "Aira test build" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/../pyproject.toml").status_code == 404
