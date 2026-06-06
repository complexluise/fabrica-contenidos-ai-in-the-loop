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


# --- Fase 2: importar (T2.3) + storyboard editable (T2.4) ------------------

def _make_project(tmp_path, slug="demo"):
    d = tmp_path / slug
    d.mkdir()
    (d / "project.yaml").write_text(
        "project: " + slug + "\nstyle: lego\ntitle: Demo\nscenes:\n"
        "  - id: s1\n    prompt: ciudad\n    duration_s: 4\n    seed: 7\n"
        "  - id: s2\n    prompt: plaza\n    duration_s: 4\n",
        encoding="utf-8",
    )
    return d


def test_import_requires_text(tmp_path):
    r = _client(tmp_path).post("/api/projects/import", json={"text": "  "})
    assert r.status_code == 422


def test_import_creates_project(tmp_path, monkeypatch):
    from pipeline import author

    draft = author.ProjectDraft(
        title="Ciudad que despierta",
        brief="Prueba",
        scenes=[author.Scene(id="s1", prompt="ciudad LEGO", duration_s=5)],
    )
    monkeypatch.setattr(author, "draft_project", lambda text: draft)

    client = _client(tmp_path)
    job = client.post("/api/projects/import", json={"text": "una ciudad despierta"}).json()
    # Consumir el SSE fuerza a que la tarea del job corra hasta el final.
    body = client.get(f"/api/jobs/{job['id']}/stream").text
    assert "__status__:done" in body

    detail = client.get(f"/api/jobs/{job['id']}").json()
    slug = detail["result"]["slug"]
    assert (tmp_path / slug / "project.yaml").exists()
    assert detail["result"]["scenes"] == 1


def test_update_project_edits_title_and_scenes(tmp_path):
    _make_project(tmp_path)
    client = _client(tmp_path)
    r = client.put("/api/projects/demo", json={
        "title": "Nuevo título",
        "brief": "nueva sinopsis",
        "scenes": [
            {"id": "s1", "prompt": "ciudad EDITADA", "duration_s": 4},
            {"id": "s2", "prompt": "plaza", "duration_s": 4},
        ],
    })
    assert r.status_code == 200
    detail = client.get("/api/projects/demo").json()
    assert detail["title"] == "Nuevo título"
    assert detail["scenes"][0]["prompt"] == "ciudad EDITADA"


def test_update_project_preserves_non_editable_scene_fields(tmp_path):
    # seed=7 en s1 no viene del UI; debe conservarse tras editar el prompt.
    _make_project(tmp_path)
    from pipeline.project import Project, load_project_spec

    client = _client(tmp_path)
    client.put("/api/projects/demo", json={
        "scenes": [{"id": "s1", "prompt": "x", "duration_s": 4}],
    })
    spec = load_project_spec(Project("demo", root=tmp_path).spec_path)
    assert spec.scenes[0].seed == 7


def test_update_project_422_on_invalid_scene(tmp_path):
    _make_project(tmp_path)
    r = _client(tmp_path).put("/api/projects/demo", json={
        "scenes": [{"id": "s1", "prompt": "x", "duration_s": -1}],
    })
    assert r.status_code == 422


def test_update_project_404_when_missing(tmp_path):
    r = _client(tmp_path).put("/api/projects/ghost", json={"scenes": [{"id": "s1", "prompt": "x", "duration_s": 4}]})
    assert r.status_code == 404


def test_update_project_prunes_orphan_selections(tmp_path):
    # AC5: eliminar s2 debe limpiar su selección persistida (D-022).
    d = _make_project(tmp_path)
    (d / "selections.yaml").write_text("s1: a.png\ns2: b.png\n", encoding="utf-8")
    client = _client(tmp_path)
    r = client.put("/api/projects/demo", json={"scenes": [{"id": "s1", "prompt": "x", "duration_s": 4}]})
    assert r.json()["dropped_selections"] == ["s2"]
    import yaml
    sel = yaml.safe_load((d / "selections.yaml").read_text(encoding="utf-8"))
    assert sel == {"s1": "a.png"}
