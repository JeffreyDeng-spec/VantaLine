"""Actual production route/auth handlers with isolated runtime and no model calls."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD


def main():
    with tempfile.TemporaryDirectory(prefix="vantaline_navigation_dist_") as directory:
        dist = Path(directory)
        (dist / "index.html").write_text("<!doctype html><title>navigation fixture</title>", encoding="utf-8")
        server.REACT_PRODUCTION_DIST_DIR = dist
        client = TestClient(server.app, base_url="https://testserver")
        pages = ["/", "/docs", "/workspace", "/workspace/about", "/workspace/text-compare-beta", "/workspace/tasks/pipeline:fixture/inspect", "/login", "/text-compare-beta", "/tasks/pipeline:fixture/inspect"]
        for page in pages:
            result = client.get(page)
            assert result.status_code == 200, (page, result.status_code)
            assert "text/html" in result.headers["content-type"]
            assert "no-store" in result.headers["cache-control"]
        # Unknown/protected URLs must not be disguised as the SPA document.
        for page in ["/api/does-not-exist", "/outputs/missing.png", "/static/missing.js", "/unrecognized-page"]:
            result = client.get(page)
            assert result.status_code in {401, 403, 404, 503}, (page, result.status_code)
            assert "navigation fixture" not in result.text
        for old, new in [("/react-preview", "/workspace"), ("/react-preview/tasks/pipeline:fixture/inspect?view=1", "/workspace/tasks/pipeline:fixture/inspect?view=1"), ("/react-preview/docs", "/docs")]:
            result = client.get(old, follow_redirects=False)
            assert result.status_code == 307 and result.headers["location"] == new, (old, result.headers)
        assert client.get("/react-preview/api/status").status_code == 404
        result = client.post("/api/auth/bootstrap", json={"username": "navigation-admin", "password": PASSWORD})
        assert result.status_code == 200, result.text
        for page in pages:
            assert client.get(page).status_code == 200
        assert client.get("/api/docs").status_code == 200
        anonymous = TestClient(server.app, base_url="https://testserver")
        assert anonymous.get("/api/docs").status_code == 401
        assert anonymous.get("/openapi.json").status_code == 404
        # Public SPA shell does not grant API authority to an ordinary account.
        result = client.post("/api/auth/users", json={"username": "navigation-user", "password": PASSWORD, "role": "user", "permissions": ["inspection"]})
        assert result.status_code == 200, result.text
        other = TestClient(server.app, base_url="https://testserver")
        assert other.post("/api/auth/login", json={"username": "navigation-user", "password": PASSWORD}).status_code == 200
        assert other.get("/workspace/about").status_code == 200
        assert other.get("/api/auth/users").status_code == 403
        assert other.get("/api/docs").status_code == 403
        assert other.get("/openapi.json").status_code == 404
        assert other.get("/api/text-inspection/standards/missing-owned-record").status_code == 404
        assert other.post("/api/auth/logout").status_code == 200
        assert other.get("/api/auth/status").json()["authenticated"] is False
    print("navigation endpoint/auth smoke: passed")


if __name__ == "__main__":
    main()
