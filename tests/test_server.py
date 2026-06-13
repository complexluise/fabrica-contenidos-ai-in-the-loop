"""Smoke del Studio (D-031): la API levanta y lista proyectos sin tocar modelos.

Requiere el extra `studio` (fastapi); si no está, se omite.
"""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pipeline.server.app import create_app  # noqa: E402


def _client(tmp_path) -> TestClient:
    # db_path apunta a un SQLite temporal para que los tests no toquen
    # out/telemetry.sqlite (el libro mayor global de produccion).
    return TestClient(create_app(projects_dir=tmp_path, config_dir=Path("config"),
                                 db_path=tmp_path / "test_jobs.sqlite"))


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
    # D-051: google_api_key se expone para gatear el toggle de keyframe Google.
    assert set(body) == {"fal_key", "anthropic_api_key", "elevenlabs_api_key", "google_api_key"}
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


def test_create_project_blank(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/projects", json={"title": "Mi Proyecto", "style": "lego"})
    assert r.status_code == 200
    slug = r.json()["slug"]
    assert (tmp_path / slug / "project.yaml").exists()
    # aparece en el listado y abre sin escenas
    assert any(p["slug"] == slug for p in c.get("/api/projects").json())
    assert c.get(f"/api/projects/{slug}").json()["scenes"] == []


def test_create_project_unique_slug(tmp_path):
    c = _client(tmp_path)
    a = c.post("/api/projects", json={"title": "Repetido"}).json()["slug"]
    b = c.post("/api/projects", json={"title": "Repetido"}).json()["slug"]
    assert a != b  # no se pisan


def test_create_project_rejects_unknown_style(tmp_path):
    r = _client(tmp_path).post("/api/projects", json={"title": "X", "style": "nope"})
    assert r.status_code == 422


def test_delete_project(tmp_path):
    c = _client(tmp_path)
    slug = c.post("/api/projects", json={"title": "Borrame"}).json()["slug"]
    assert c.delete(f"/api/projects/{slug}").json()["deleted"] == slug
    assert not (tmp_path / slug).exists()
    assert c.get(f"/api/projects/{slug}").status_code == 404


def test_delete_project_404_when_missing(tmp_path):
    assert _client(tmp_path).delete("/api/projects/ghost").status_code == 404


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


def test_update_project_sign_toggles_storyboard_signed(tmp_path):
    # #5: firmar marca el storyboard como firmado; un cambio NARRATIVO sin
    # firmar lo limpia (D-082: el prompt ya no cuenta como narrativo).
    _make_project(tmp_path)
    c = _client(tmp_path)
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is False

    r = c.put("/api/projects/demo", json={"sign": True,
              "scenes": [{"id": "s1", "prompt": "x", "duration_s": 4}]})
    assert r.json()["signed"] is True
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is True

    c.put("/api/projects/demo", json={"scenes": [
        {"id": "s1", "prompt": "x", "duration_s": 4, "dialogue": "Juan: hola."}]})
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is False


def test_update_project_422_on_invalid_scene(tmp_path):
    _make_project(tmp_path)
    r = _client(tmp_path).put("/api/projects/demo", json={
        "scenes": [{"id": "s1", "prompt": "x", "duration_s": -1}],
    })
    assert r.status_code == 422


def test_update_project_404_when_missing(tmp_path):
    r = _client(tmp_path).put("/api/projects/ghost", json={"scenes": [{"id": "s1", "prompt": "x", "duration_s": 4}]})
    assert r.status_code == 404


def test_list_styles(tmp_path):
    styles = _client(tmp_path).get("/api/styles").json()
    assert "lego" in styles and "crochet" in styles


def test_import_with_style_override(tmp_path, monkeypatch):
    from pipeline import author

    draft = author.ProjectDraft(title="X", scenes=[author.Scene(id="s1", prompt="a", duration_s=4)])
    monkeypatch.setattr(author, "draft_project", lambda text: draft)
    c = _client(tmp_path)
    job = c.post("/api/projects/import", json={"text": "hola", "style": "crochet"}).json()
    assert "__status__:done" in c.get(f"/api/jobs/{job['id']}/stream").text
    slug = c.get(f"/api/jobs/{job['id']}").json()["result"]["slug"]
    assert c.get(f"/api/projects/{slug}").json()["style"] == "crochet"


def test_import_rejects_unknown_style(tmp_path):
    r = _client(tmp_path).post("/api/projects/import", json={"text": "hola", "style": "nope"})
    assert r.status_code == 422


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


# --- D-078: guardar claves desde la UI no destruye el .env ---------------------

def test_merge_env_lines_preserves_comments_and_foreign_keys():
    from pipeline.server.app import merge_env_lines

    lines = ["# mis claves (no borrar)", "FAL_KEY=vieja", "", "OTRA_VAR=x"]
    out = merge_env_lines(lines, {"FAL_KEY": "nueva", "GOOGLE_API_KEY": "g"})
    assert out[0] == "# mis claves (no borrar)"   # el comentario sobrevive
    assert "FAL_KEY=nueva" in out
    assert "OTRA_VAR=x" in out                     # las claves ajenas sobreviven
    assert "GOOGLE_API_KEY=g" in out               # la nueva se agrega al final
    assert "FAL_KEY=vieja" not in out


# --- D-079: el libro mayor visible desde la UI ---------------------------------

def test_costs_endpoint_returns_summary(tmp_path):
    r = _client(tmp_path).get("/api/costs")
    assert r.status_code == 200
    body = r.json()
    assert "total_usd" in body and "by_project" in body and "by_provider" in body


# --- Fase 2.6 (hardening post-auditoría) ---------------------------------------

def _make_engine_project(tmp_path, slug="motor"):
    """Proyecto con los campos del motor (D-070..D-074) poblados en un plano."""
    d = tmp_path / slug
    d.mkdir()
    (d / "project.yaml").write_text(
        "project: " + slug + "\nstyle: lego\ntitle: Motor\nscenes:\n"
        "  - id: s1\n    prompt: ciudad\n    duration_s: 4\n"
        "    shots:\n"
        "      - framing: wide\n"
        "        duration_s: 4\n"
        "        motion: the camera orbits him quickly, then settles\n"
        "        lands: true\n"
        "        media: video\n"
        "        takes: 3\n"
        "        speed: 1.2\n",
        encoding="utf-8",
    )
    return d


def test_project_detail_exposes_engine_fields(tmp_path):
    # T2.6.1: el GET serializa motion/lands/media/takes/speed. Su ausencia era
    # la causa del wipe: la UI leía undefined y guardaba defaults encima.
    _make_engine_project(tmp_path)
    sh = _client(tmp_path).get("/api/projects/motor").json()["scenes"][0]["shots"][0]
    assert sh["motion"] == "the camera orbits him quickly, then settles"
    assert sh["lands"] is True and sh["media"] == "video"
    assert sh["takes"] == 3 and sh["speed"] == 1.2


def test_storyboard_roundtrip_preserves_engine_fields(tmp_path):
    # T2.6.2: PUT(GET(x)) no pierde nada — el guard permanente del contrato
    # UI<->server. Este test habría atrapado el bug de la auditoría 2026-06-12.
    _make_engine_project(tmp_path)
    c = _client(tmp_path)
    detail = c.get("/api/projects/motor").json()
    body = {"title": detail["title"], "brief": detail["brief"] or "",
            "scenes": detail["scenes"]}
    assert c.put("/api/projects/motor", json=body).status_code == 200

    from pipeline.project import Project, load_project_spec
    sh = load_project_spec(Project("motor", root=tmp_path).spec_path).scenes[0].shots[0]
    assert sh.motion == "the camera orbits him quickly, then settles"
    assert sh.lands is True and sh.media == "video"
    assert sh.takes == 3 and sh.speed == 1.2


# --- D-082: la firma atestigua el plan NARRATIVO --------------------------------

def _signed_demo(tmp_path):
    _make_project(tmp_path)
    c = _client(tmp_path)
    c.put("/api/projects/demo", json={"sign": True, "scenes": [
        {"id": "s1", "prompt": "ciudad", "duration_s": 4},
        {"id": "s2", "prompt": "plaza", "duration_s": 4},
    ]})
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is True
    return c


def test_prompt_only_edit_preserves_signature(tmp_path):
    # Encuadres edita el prompt visual post-firma; eso NO des-firma (D-082).
    c = _signed_demo(tmp_path)
    r = c.put("/api/projects/demo", json={"scenes": [
        {"id": "s1", "prompt": "ciudad neon de noche", "duration_s": 4},
        {"id": "s2", "prompt": "plaza", "duration_s": 4},
    ]})
    assert r.json()["signed"] is True
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is True


def test_backend_switch_preserves_signature(tmp_path):
    # Cambiar el motor de imagen es una preferencia, no un cambio del plan.
    c = _signed_demo(tmp_path)
    r = c.put("/api/projects/demo", json={"storyboard_backend": "google", "scenes": [
        {"id": "s1", "prompt": "ciudad", "duration_s": 4},
        {"id": "s2", "prompt": "plaza", "duration_s": 4},
    ]})
    assert r.json()["signed"] is True


def test_narrative_edit_clears_signature(tmp_path):
    # Tocar un plano (duración) SI es el plan: la firma se limpia.
    c = _signed_demo(tmp_path)
    r = c.put("/api/projects/demo", json={"scenes": [
        {"id": "s1", "prompt": "ciudad", "duration_s": 6},
        {"id": "s2", "prompt": "plaza", "duration_s": 4},
    ]})
    assert r.json()["signed"] is False
    assert c.get("/api/projects/demo/status").json()["storyboard"]["signed"] is False


# --- Fase 2.6: perfiles sin drift (D-076) ---------------------------------------

def test_profiles_expose_default_and_scene_cost(tmp_path):
    # T2.6.14: el default viene del server (la UI no hardcodea fal-ultra-cheap)
    # y est_cost_per_scene_usd viaja (el estimado del Animatic era NaN sin él).
    from pipeline.config import DEFAULT_PROFILE

    profs = _client(tmp_path).get("/api/profiles").json()
    assert sum(1 for p in profs if p.get("default")) == 1
    assert any(p["key"] == DEFAULT_PROFILE and p["default"] for p in profs)
    assert all(isinstance(p["est_cost_per_scene_usd"], (int, float)) for p in profs)


# --- Fase 2.6: anti doble-gasto (T2.6.6) -----------------------------------------

def test_concurrent_same_job_is_409(tmp_path, monkeypatch):
    # T2.6.6: un segundo import del mismo proyecto mientras el primero está vivo
    # se rechaza con 409 (no se paga dos veces). Acá probamos el MAPEO HTTP; que
    # re-disparar tras 'done' vuelva a estar permitido se cubre, sin la fragilidad
    # de TestClient+to_thread, en test_jobs.py::test_spawn_allowed_again_after_done.
    import threading

    from pipeline import author

    gate = threading.Event()
    draft = author.ProjectDraft(
        title="X", scenes=[author.Scene(id="s1", prompt="a", duration_s=4)])

    def slow_draft(text):
        gate.wait(timeout=5)  # el job queda vivo hasta que el test lo libere
        return draft

    monkeypatch.setattr(author, "draft_project", slow_draft)
    c = _client(tmp_path)
    try:
        c.post("/api/projects/import", json={"text": "hola", "slug": "uno"})
        # mismo kind+proyecto con el primero vivo -> 409 con mensaje legible
        r = c.post("/api/projects/import", json={"text": "hola", "slug": "uno"})
        assert r.status_code == 409
        assert "trabajo" in r.json()["detail"].lower()
    finally:
        gate.set()  # liberar el worker bloqueado (teardown limpio)


# --- D-084: casting con el patrón fluido de los keyframes ------------------------

def test_candidates_exposes_cast_sources(tmp_path):
    # La mesa de luz del casting necesita cast_sources para el badge "tu foto".
    _make_project(tmp_path)
    body = _client(tmp_path).get("/api/projects/demo/candidates").json()
    assert "cast_sources" in body and isinstance(body["cast_sources"], dict)


def test_cast_character_404_for_unknown(tmp_path):
    _make_project(tmp_path)
    r = _client(tmp_path).post("/api/projects/demo/cast/fantasma", json={})
    assert r.status_code == 404


def test_cast_upload_404_for_unknown_character(tmp_path):
    _make_project(tmp_path)
    r = _client(tmp_path).post("/api/projects/demo/cast-candidates/fantasma/upload",
                               json={"data": "Zm9v", "filename": "x.png"})
    assert r.status_code == 404


def test_discard_cast_candidate_422_when_no_candidates(tmp_path):
    _make_project(tmp_path)
    r = _client(tmp_path).delete("/api/projects/demo/cast-candidates/juan/0")
    assert r.status_code == 422


# --- D-085: el prompt del personaje, visible y editable (patrón completo) --------

def _make_cast_project(tmp_path, slug="cast"):
    d = tmp_path / slug
    d.mkdir()
    (d / "project.yaml").write_text(
        "project: " + slug + "\nstyle: lego\ntitle: Cast\n"
        "characters:\n"
        "  juan:\n"
        "    design:\n"
        "      prompt: hombre mayor\n"
        "      physical: barba canosa\n"
        "      palette: [azul, ocre]\n"
        "scenes:\n"
        "  - id: s1\n    prompt: x\n    duration_s: 4\n    characters: [juan]\n",
        encoding="utf-8",
    )
    return d


def test_project_detail_exposes_design_fields(tmp_path):
    _make_cast_project(tmp_path)
    chars = _client(tmp_path).get("/api/projects/cast").json()["characters"]
    juan = next(c for c in chars if c["name"] == "juan")
    assert juan["design_fields"]["prompt"] == "hombre mayor"
    assert juan["design_fields"]["physical"] == "barba canosa"
    assert juan["design_fields"]["palette"] == ["azul", "ocre"]
    # `design` es el compuesto (preview de lo que se envía a la IA)
    assert "hombre mayor" in juan["design"] and "barba canosa" in juan["design"]


def test_update_character_persists_design(tmp_path):
    _make_cast_project(tmp_path)
    c = _client(tmp_path)
    r = c.put("/api/projects/cast/characters/juan", json={
        "prompt": "hombre joven", "physical": "pelo corto",
        "wardrobe": "saco azul", "palette": ["rojo"], "expression": "serio"})
    assert r.status_code == 200
    assert "hombre joven" in r.json()["design"]
    # persistió: el siguiente GET lo refleja
    juan = next(ch for ch in c.get("/api/projects/cast").json()["characters"]
                if ch["name"] == "juan")
    assert juan["design_fields"]["prompt"] == "hombre joven"
    assert juan["design_fields"]["wardrobe"] == "saco azul"
    assert juan["design_fields"]["expression"] == "serio"


def test_update_character_404_for_unknown(tmp_path):
    _make_cast_project(tmp_path)
    r = _client(tmp_path).put("/api/projects/cast/characters/fantasma",
                              json={"prompt": "x"})
    assert r.status_code == 404


def test_update_character_422_without_prompt(tmp_path):
    _make_cast_project(tmp_path)
    r = _client(tmp_path).put("/api/projects/cast/characters/juan", json={"prompt": "  "})
    assert r.status_code == 422


# --- Ciclo 1: persistencia de jobs — endpoints (GET /api/jobs, /history, /{id}) ---

def test_list_jobs_returns_only_active(tmp_path, monkeypatch):
    """GET /api/jobs devuelve SOLO los jobs activos (no los terminados).

    El dock del sidebar pollea cada 3s; devolver el historico lo arruinaria.
    """
    import threading

    from pipeline import author

    gate = threading.Event()
    draft = author.ProjectDraft(
        title="X", scenes=[author.Scene(id="s1", prompt="a", duration_s=4)])

    def slow_draft(text):
        gate.wait(timeout=5)
        return draft

    monkeypatch.setattr(author, "draft_project", slow_draft)
    c = _client(tmp_path)
    try:
        job = c.post("/api/projects/import", json={"text": "hola"}).json()
        # Job activo: debe aparecer en /api/jobs
        active = c.get("/api/jobs").json()
        assert any(j["id"] == job["id"] for j in active)
        # Solo activos: ninguno de los que estan en lista esta done/failed
        assert all(j["status"] in ("queued", "running") for j in active)
    finally:
        gate.set()


def test_jobs_history_endpoint(tmp_path, monkeypatch):
    """GET /api/jobs/history devuelve jobs terminados del SQLite."""
    from pipeline import author

    draft = author.ProjectDraft(
        title="X", scenes=[author.Scene(id="s1", prompt="a", duration_s=4)])
    monkeypatch.setattr(author, "draft_project", lambda text: draft)
    c = _client(tmp_path)

    # Crear y completar un job via el endpoint de import
    job = c.post("/api/projects/import", json={"text": "hola"}).json()
    # Consumir el stream para que el job termine
    c.get(f"/api/jobs/{job['id']}/stream").text

    # Debe aparecer en history
    history = c.get("/api/jobs/history").json()
    assert isinstance(history, list)
    ids = [h["id"] for h in history]
    assert job["id"] in ids
    # El job terminado tiene status done o failed
    entry = next(h for h in history if h["id"] == job["id"])
    assert entry["status"] in ("done", "failed")


def test_jobs_history_pagination(tmp_path):
    """GET /api/jobs/history?limit=&offset= pagina correctamente."""
    c = _client(tmp_path)
    r = c.get("/api/jobs/history?limit=10&offset=0")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_job_detail_fallback_to_sqlite(tmp_path, monkeypatch):
    """GET /api/jobs/{id} cae a SQLite para jobs terminados que ya no estan en memoria.

    Simula el caso post-reinicio: el job esta en SQLite (done) pero no en memoria.
    """
    from pipeline.server.job_store import JobStore

    db = tmp_path / "test_jobs.sqlite"
    # Pre-insertar un job terminado directamente en el store (simula proceso anterior)
    store = JobStore(db)
    store.insert_job("histjob1", "render", "demo")
    store.set_running("histjob1")
    store.set_done("histjob1", {"run_id": "r99"}, log_tail=["ultima linea"])
    store.close()

    # El JobManager hace el barrido al boot pero ese job ya era done -> intacto
    c = _client(tmp_path)
    r = c.get("/api/jobs/histjob1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "histjob1"
    assert body["status"] == "done"
    assert body["result"]["run_id"] == "r99"
    assert "ultima linea" in body["logs"]


def test_job_detail_unknown_returns_404(tmp_path):
    """GET /api/jobs/{id} devuelve 404 si el job no existe ni en memoria ni en SQLite."""
    r = _client(tmp_path).get("/api/jobs/nonexistent123")
    assert r.status_code == 404
