"""Smoke del Studio (D-031): la API levanta y lista proyectos sin tocar modelos.

Requiere el extra `studio` (fastapi); si no está, se omite.
"""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pipeline.server.app import create_app  # noqa: E402


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(projects_dir=tmp_path, config_dir=Path("config")))


def test_health(tmp_path):
    assert _client(tmp_path).get("/api/health").json() == {"ok": True}


def test_list_projects(tmp_path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "project.yaml").write_text(
        "project: demo\nstyle: lego\ntitle: Demo\nscenes:\n"
        "  - id: s1\n    prompt: x\n    duration_s: 4\n",
        encoding="utf-8",
    )
    projs = _client(tmp_path).get("/api/projects").json()
    assert any(p["slug"] == "demo" and p["title"] == "Demo" and p["scenes"] == 1 for p in projs)


def test_project_detail_404_when_missing(tmp_path):
    assert _client(tmp_path).get("/api/projects/ghost").status_code == 404


def test_settings_status_shape(tmp_path):
    body = _client(tmp_path).get("/api/settings").json()
    assert set(body) == {"fal_key", "anthropic_api_key", "elevenlabs_api_key"}
    assert all(isinstance(v, bool) for v in body.values())
