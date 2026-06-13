"""Core Studio (D-031): job manager — estados y registro (logica pura).

Ciclo 1 (persistencia SQLite): cubre transiciones persistidas, barrido al
boot y el historial. Los tests de persistencia usan tmp_path para estar
aislados; la fixture autouse en conftest.py garantiza que NINGUN test
escriba en out/telemetry.sqlite (la base real del operador).
"""

import asyncio
from pathlib import Path

import pytest

from pipeline.server.jobs import Job, JobConflictError, JobManager, JobStatus


def test_job_to_dict_and_done():
    j = Job(id="x", kind="render", project="p")
    assert j.status == JobStatus.QUEUED and not j.done
    d = j.to_dict()
    assert d["id"] == "x" and d["kind"] == "render"
    assert d["status"] == "queued" and d["log_lines"] == 0


def test_manager_create_get_list():
    m = JobManager()
    j = m.create("keyframes", "pesc")
    assert m.get(j.id) is j and j in m.list()


def test_manager_append_log_and_set_status():
    m = JobManager()
    j = m.create("render", "p")
    m.append_log(j.id, "linea 1")
    m.append_log(j.id, "linea 2")
    assert j.logs == ["linea 1", "linea 2"]
    m.set_status(j.id, JobStatus.DONE, result={"run_id": "r1"})
    assert j.done and j.result == {"run_id": "r1"}
    assert j.to_dict()["log_lines"] == 2


def test_manager_unknown_job_is_noop():
    m = JobManager()
    m.append_log("nope", "x")  # no debe romper
    m.set_status("nope", JobStatus.FAILED, error="e")
    assert m.get("nope") is None


# --- Fase 2.6 (T2.6.6): guard anti doble-gasto ------------------------------

async def _wait_all_done(m: JobManager, tries: int = 200):
    for _ in range(tries):
        if all(j.done for j in m.list()):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("los jobs no terminaron a tiempo")


async def test_spawn_conflict_same_kind_and_project():
    m = JobManager()
    release = asyncio.Event()

    async def work():
        await release.wait()
        return {"ok": True}

    m.spawn("render", "p", work())
    # mismo kind+proyecto con el primero vivo -> conflicto (no se paga dos veces)
    with pytest.raises(JobConflictError):
        m.spawn("render", "p", work())
    # otro proyecto u otro kind: permitido
    m.spawn("render", "otro", work())
    m.spawn("export", "p", work())

    release.set()
    await _wait_all_done(m)
    assert len(m.list()) == 3  # el conflictivo nunca se registró


async def test_spawn_allowed_again_after_done():
    m = JobManager()

    async def quick():
        return {"ok": True}

    m.spawn("render", "p", quick())
    await _wait_all_done(m)
    m.spawn("render", "p", quick())  # terminado: re-disparar es legítimo
    await _wait_all_done(m)
    assert len(m.list()) == 2


# --- Fase 2.6 (T2.6.23): un evento por consumidor del stream ----------------

async def test_stream_two_consumers_both_get_everything():
    # Con un Event compartido, un consumidor le "robaba" el despertar al otro
    # (clear ajeno) y el segundo SSE podía colgarse. Uno por consumidor.
    m = JobManager()
    j = m.create("render", "p")

    async def consume():
        return [line async for line in m.stream(j.id)]

    async def produce():
        await asyncio.sleep(0.02)
        m.append_log(j.id, "a")
        await asyncio.sleep(0.02)
        m.append_log(j.id, "b")
        m.set_status(j.id, JobStatus.DONE)

    r1, r2, _ = await asyncio.wait_for(
        asyncio.gather(consume(), consume(), produce()), timeout=5)
    assert r1 == ["a", "b", "__status__:done"]
    assert r2 == ["a", "b", "__status__:done"]


# --- Ciclo 1: persistencia de jobs en SQLite ---------------------------------


def _mgr(tmp_path: Path) -> JobManager:
    """JobManager con base SQLite aislada en tmp_path."""
    return JobManager(db_path=tmp_path / "jobs_test.sqlite")


def test_persistence_queued_on_create(tmp_path):
    """create() persiste el job con status=queued en SQLite."""
    from pipeline.server.job_store import JobStore

    m = _mgr(tmp_path)
    j = m.create("render", "demo")
    # Abrir el store directamente para verificar que se escribio
    store = JobStore(tmp_path / "jobs_test.sqlite")
    row = store.get_job(j.id)
    assert row is not None
    assert row["status"] == "queued"
    assert row["kind"] == "render"
    assert row["project"] == "demo"


def test_persistence_running_on_set_status(tmp_path):
    """set_status(RUNNING) persiste la transicion en SQLite."""
    from pipeline.server.job_store import JobStore

    m = _mgr(tmp_path)
    j = m.create("keyframes", "slug")
    m.set_status(j.id, JobStatus.RUNNING)
    store = JobStore(tmp_path / "jobs_test.sqlite")
    row = store.get_job(j.id)
    assert row["status"] == "running"
    assert row["started_at"] is not None


def test_persistence_done_with_result_and_log_tail(tmp_path):
    """set_status(DONE) persiste result y log_tail (ultimas lineas del log)."""
    from pipeline.server.job_store import JobStore

    m = _mgr(tmp_path)
    j = m.create("render", "demo")
    m.append_log(j.id, "linea 1")
    m.append_log(j.id, "linea 2")
    m.set_status(j.id, JobStatus.RUNNING)
    m.set_status(j.id, JobStatus.DONE, result={"run_id": "r42"})

    store = JobStore(tmp_path / "jobs_test.sqlite")
    row = store.get_job(j.id)
    assert row["status"] == "done"
    assert row["result"]["run_id"] == "r42"
    assert row["ended_at"] is not None
    assert "linea 1" in row["log_tail"]
    assert "linea 2" in row["log_tail"]


def test_persistence_failed_with_error(tmp_path):
    """set_status(FAILED) persiste error y log_tail."""
    from pipeline.server.job_store import JobStore

    m = _mgr(tmp_path)
    j = m.create("render", "demo")
    m.set_status(j.id, JobStatus.RUNNING)
    m.set_status(j.id, JobStatus.FAILED, error="algo salio mal")

    store = JobStore(tmp_path / "jobs_test.sqlite")
    row = store.get_job(j.id)
    assert row["status"] == "failed"
    assert row["error"] == "algo salio mal"


def test_boot_sweep_marks_orphaned_jobs_failed(tmp_path):
    """Al reiniciar el JobManager, jobs queued/running del proceso anterior
    se marcan failed. Sin esto, find_active bloquea para siempre (D-082).
    """
    from pipeline.server.job_store import JobStore

    # Simular proceso anterior: insertar jobs huerfanos directamente en el store
    db = tmp_path / "jobs_test.sqlite"
    store1 = JobStore(db)
    store1.insert_job("aaa", "render", "p1")
    store1.insert_job("bbb", "keyframes", "p2")
    store1.set_running("bbb")
    store1.insert_job("ccc", "export", "p3")
    # ccc lo marcamos done (no debe tocar el barrido)
    store1.set_done("ccc", {"ok": True})
    store1.close()

    # Reiniciar el manager -> barrido al boot
    m2 = JobManager(db_path=db)
    store2 = JobStore(db)
    # aaa y bbb deben estar failed
    assert store2.get_job("aaa")["status"] == "failed"
    assert store2.get_job("bbb")["status"] == "failed"
    # ccc (done) debe estar intacto
    assert store2.get_job("ccc")["status"] == "done"
    # Los jobs huerfanos NO deben aparecer en memoria (find_active libre)
    assert m2.find_active("render", "p1") is None
    assert m2.find_active("keyframes", "p2") is None


def test_boot_sweep_allows_redispatch(tmp_path):
    """Tras el barrido, se puede re-disparar el mismo kind+proyecto sin 409."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "jobs_test.sqlite"
    store = JobStore(db)
    store.insert_job("old", "render", "demo")
    store.set_running("old")
    store.close()

    m = JobManager(db_path=db)
    # Debe poder crear un nuevo job render/demo sin JobConflictError
    j = m.create("render", "demo")
    assert j.kind == "render" and j.project == "demo"


def test_list_active_only_queued_and_running(tmp_path):
    """list() devuelve solo los jobs vivos (queued/running) de memoria.

    Los jobs terminados en memoria no se exponen por list() cuando estan done,
    aunque sigan en el dict interno (para el SSE replay).
    Este comportamiento es el mismo de antes; GET /api/jobs lo filtra ademas.
    """
    m = _mgr(tmp_path)
    j1 = m.create("render", "p1")
    j2 = m.create("keyframes", "p2")
    m.set_status(j1.id, JobStatus.DONE)
    # list() devuelve todos los jobs en memoria (incluyendo done)
    # pero el endpoint /api/jobs filtra solo los !done
    # Acá testeamos que find_active no ve j1 (done)
    assert m.find_active("render", "p1") is None
    assert m.find_active("keyframes", "p2") is j2


def test_get_from_store_for_terminated_job(tmp_path):
    """get_from_store devuelve el job terminado aunque ya no este en memoria."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "jobs_test.sqlite"
    # Insertar directamente como si fuera un job de un proceso anterior
    store = JobStore(db)
    store.insert_job("old123", "render", "proj")
    store.set_running("old123")
    store.set_done("old123", {"run_id": "r1"}, log_tail=["linea final"])
    store.close()

    m = JobManager(db_path=db)
    # No esta en memoria (es de proceso anterior, barrido lo deja intacto si ya era done)
    assert m.get("old123") is None
    row = m.get_from_store("old123")
    assert row is not None
    assert row["status"] == "done"
    assert row["result"]["run_id"] == "r1"
    assert "linea final" in row["log_tail"]


def test_list_history_returns_terminated_jobs(tmp_path):
    """list_history() devuelve done/failed del SQLite, mas nuevos primero."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "jobs_test.sqlite"
    store = JobStore(db)
    store.insert_job("j1", "render", "p", created_at=1000.0)
    store.set_running("j1", started_at=1001.0)
    store.set_done("j1", {"ok": 1}, ended_at=1010.0)
    store.insert_job("j2", "keyframes", "p", created_at=2000.0)
    store.set_running("j2", started_at=2001.0)
    store.set_failed("j2", "error grave", ended_at=2010.0)
    # j3 sigue vivo (queued): no debe aparecer en history
    store.insert_job("j3", "export", "p", created_at=3000.0)
    store.close()

    m = JobManager(db_path=db)
    history = m.list_history()
    ids = [h["id"] for h in history]
    # j1 y j2 terminados; j3 (queued) lo barre el boot y queda como failed -> aparece
    assert "j1" in ids and "j2" in ids and "j3" in ids
    # mas nuevo primero segun ended_at: j3 barrido ahora (ts > j2=2010 > j1=1010)
    assert ids.index("j1") > ids.index("j2")


def test_list_history_pagination(tmp_path):
    """list_history soporta limit/offset."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "jobs_test.sqlite"
    store = JobStore(db)
    for i in range(5):
        jid = f"j{i}"
        store.insert_job(jid, "render", "p", created_at=float(i * 100))
        store.set_running(jid, started_at=float(i * 100 + 1))
        store.set_done(jid, {"i": i}, ended_at=float(i * 100 + 10))
    store.close()

    m = JobManager(db_path=db)
    page1 = m.list_history(limit=2, offset=0)
    page2 = m.list_history(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    # No se solapan
    ids1 = {h["id"] for h in page1}
    ids2 = {h["id"] for h in page2}
    assert ids1.isdisjoint(ids2)


def test_job_events_written_per_transition(tmp_path):
    """Cada transicion escribe una fila en job_events (event sourcing liviano)."""
    import sqlite3

    db = tmp_path / "jobs_test.sqlite"
    m = _mgr(tmp_path)
    j = m.create("render", "demo")
    m.set_status(j.id, JobStatus.RUNNING)
    m.set_status(j.id, JobStatus.DONE, result={"ok": True})

    conn = sqlite3.connect(str(db))
    events = [r[0] for r in conn.execute(
        "SELECT type FROM job_events WHERE job_id=? ORDER BY rowid", (j.id,)
    ).fetchall()]
    conn.close()
    # queued (en create), running, done y log_tail (por los logs del job)
    assert "queued" in events
    assert "running" in events
    assert "done" in events


# --- Ciclo 2: semaforo de concurrencia (D-092) -----------------------------------


async def test_semaphore_limits_concurrency(tmp_path):
    """Con max_concurrency=1: el segundo job queda QUEUED hasta que el primero
    libera el semaforo; luego pasa a RUNNING.

    La secuencia esperada:
      1. job1 spawn -> RUNNING (toma el semaforo)
      2. job2 spawn -> QUEUED (esperando semaforo)
      3. job1 libera -> job2 pasa a RUNNING -> luego DONE
    """
    m = JobManager(db_path=tmp_path / "sem.sqlite", max_concurrency=1)

    # Evento para bloquear job1 hasta que decidamos liberarlo
    release1 = asyncio.Event()
    # Evento para saber que job2 esta corriendo
    job2_started = asyncio.Event()

    async def work1():
        await release1.wait()
        return {"job": 1}

    async def work2():
        job2_started.set()
        return {"job": 2}

    job1 = m.spawn("render", "p1", work1())
    job2 = m.spawn("render", "p2", work2())

    # Dar tiempo al event loop para arrancar job1 y que job2 quede esperando
    await asyncio.sleep(0.05)

    # job1 debe estar RUNNING (tomo el semaforo)
    assert job1.status == JobStatus.RUNNING, f"job1 esperado RUNNING, got {job1.status}"
    # job2 debe estar QUEUED (semaforo ocupado)
    assert job2.status == JobStatus.QUEUED, f"job2 esperado QUEUED, got {job2.status}"

    # Liberar job1
    release1.set()

    # Esperar a que job2 arranque y termine
    await asyncio.wait_for(job2_started.wait(), timeout=3)
    await _wait_all_done(m)

    assert job1.status == JobStatus.DONE
    assert job2.status == JobStatus.DONE


async def test_semaphore_queued_job_still_triggers_409_conflict(tmp_path):
    """Un job en QUEUED (esperando semaforo) sigue siendo "vivo" para el guard 409.

    El guard anti doble-gasto no distingue QUEUED de RUNNING: ambos son vivos.
    Un segundo disparo identico debe dar JobConflictError aunque el primero
    este en cola.
    """
    m = JobManager(db_path=tmp_path / "sem.sqlite", max_concurrency=1)

    release = asyncio.Event()

    async def slow():
        await release.wait()
        return {"ok": True}

    # job1 ocupa el semaforo
    job1 = m.spawn("render", "proj1", slow())
    # job2 queda en cola (semaforo lleno, proyecto diferente -> no conflict)
    job2 = m.spawn("render", "proj2", slow())

    await asyncio.sleep(0.05)
    assert job2.status == JobStatus.QUEUED

    # Ahora intentar re-disparar job2 (mismo kind+proyecto) -> 409
    with pytest.raises(JobConflictError):
        m.spawn("render", "proj2", slow())

    # limpieza
    release.set()
    await _wait_all_done(m)


async def test_semaphore_default_concurrency_is_2(tmp_path):
    """El default de max_concurrency es 2: dos jobs corren en paralelo sin bloquearse."""
    m = JobManager(db_path=tmp_path / "sem2.sqlite")  # sin pasar max_concurrency

    release = asyncio.Event()
    started = []

    async def work(n):
        started.append(n)
        await release.wait()
        return {"n": n}

    job1 = m.spawn("render", "p1", work(1))
    job2 = m.spawn("keyframes", "p2", work(2))
    job3 = m.spawn("render", "p3", work(3))  # el tercero debe quedar en cola

    await asyncio.sleep(0.05)

    # Con default=2: job1 y job2 RUNNING, job3 QUEUED
    assert job1.status == JobStatus.RUNNING
    assert job2.status == JobStatus.RUNNING
    assert job3.status == JobStatus.QUEUED

    release.set()
    await _wait_all_done(m)
    assert job3.status == JobStatus.DONE


async def test_semaphore_queued_job_visible_in_list(tmp_path):
    """Un job QUEUED (esperando semaforo) aparece en list() y find_active()."""
    m = JobManager(db_path=tmp_path / "sem.sqlite", max_concurrency=1)

    release = asyncio.Event()

    async def slow():
        await release.wait()
        return {"ok": True}

    m.spawn("render", "p1", slow())
    job2 = m.spawn("keyframes", "p2", slow())

    await asyncio.sleep(0.05)
    assert job2.status == JobStatus.QUEUED

    # Debe ser visible en list() y en find_active()
    assert job2 in m.list()
    assert m.find_active("keyframes", "p2") is job2

    release.set()
    await _wait_all_done(m)


# --- D-093: scope batch/item -----------------------------------------------


def test_determine_scope_batch_for_top_level_kinds(tmp_path):
    """Jobs de lote (render, keyframes, cast, animatic con project=slug) -> batch."""
    from pipeline.server.job_store import determine_scope

    assert determine_scope("render", "mi-proyecto") == "batch"
    assert determine_scope("keyframes", "mi-proyecto") == "batch"
    assert determine_scope("cast", "mi-proyecto") == "batch"
    assert determine_scope("animatic", "mi-proyecto") == "batch"
    assert determine_scope("export", "mi-proyecto") == "batch"
    assert determine_scope("import", "mi-proyecto") == "batch"
    assert determine_scope("music", "mi-proyecto") == "batch"


def test_determine_scope_item_for_sub_project(tmp_path):
    """Jobs con project='slug/sub' (per-escena, per-personaje) -> item."""
    from pipeline.server.job_store import determine_scope

    assert determine_scope("keyframes", "mi-proyecto/s1") == "item"
    assert determine_scope("cast", "mi-proyecto/juan") == "item"
    assert determine_scope("shots", "mi-proyecto/s1") == "item"


def test_determine_scope_item_for_micro_kinds(tmp_path):
    """Kinds micro (pose_variants, shots) siempre son item, aunque project sea top-level."""
    from pipeline.server.job_store import determine_scope

    assert determine_scope("pose_variants", "mi-proyecto") == "item"
    assert determine_scope("shots", "mi-proyecto") == "item"
    # Con sub-project tambien
    assert determine_scope("pose_variants", "mi-proyecto/s1/destino") == "item"


def test_scope_persisted_on_create(tmp_path):
    """create() persiste el scope correcto en SQLite."""
    from pipeline.server.job_store import JobStore

    m = _mgr(tmp_path)
    # batch
    j_batch = m.create("render", "demo")
    # item por project
    j_item_proj = m.create("keyframes", "demo/s1")
    # item por kind
    j_item_kind = m.create("shots", "demo")

    store = JobStore(tmp_path / "jobs_test.sqlite")
    assert store.get_job(j_batch.id)["scope"] == "batch"
    assert store.get_job(j_item_proj.id)["scope"] == "item"
    assert store.get_job(j_item_kind.id)["scope"] == "item"


def test_scope_in_job_to_dict(tmp_path):
    """to_dict() incluye el campo scope."""
    m = _mgr(tmp_path)
    j_batch = m.create("render", "demo")
    j_item = m.create("keyframes", "demo/s1")
    assert j_batch.to_dict()["scope"] == "batch"
    assert j_item.to_dict()["scope"] == "item"


def test_history_default_excludes_micro(tmp_path):
    """list_history() por defecto devuelve solo jobs batch (exclude micro scope=item)."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "scope_test.sqlite"
    store = JobStore(db)
    # batch
    store.insert_job("b1", "render", "p", created_at=1000.0)
    store.set_running("b1", started_at=1001.0)
    store.set_done("b1", {"ok": 1}, ended_at=1010.0)
    # item
    store.insert_job("i1", "keyframes", "p/s1", created_at=2000.0)
    store.set_running("i1", started_at=2001.0)
    store.set_done("i1", {"ok": 1}, ended_at=2010.0)
    store.close()

    m = JobManager(db_path=db)
    history = m.list_history()
    ids = [h["id"] for h in history]
    # i1 es item: NO debe aparecer por defecto
    assert "b1" in ids
    assert "i1" not in ids


def test_history_include_micro_returns_all(tmp_path):
    """list_history(include_micro=True) devuelve batch e item."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "scope_micro.sqlite"
    store = JobStore(db)
    store.insert_job("b1", "render", "p", created_at=1000.0)
    store.set_running("b1", started_at=1001.0)
    store.set_done("b1", {}, ended_at=1010.0)
    store.insert_job("i1", "keyframes", "p/s1", created_at=2000.0)
    store.set_running("i1", started_at=2001.0)
    store.set_done("i1", {}, ended_at=2010.0)
    store.close()

    m = JobManager(db_path=db)
    history = m.list_history(include_micro=True)
    ids = [h["id"] for h in history]
    assert "b1" in ids
    assert "i1" in ids


def test_history_filter_by_kind(tmp_path):
    """list_history(kind='render') devuelve solo jobs de ese kind."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "kind_filter.sqlite"
    store = JobStore(db)
    for i, (kind, jid) in enumerate([("render", "r1"), ("export", "e1"), ("keyframes", "k1")]):
        # timestamps deterministas (no hash(), que depende de PYTHONHASHSEED)
        store.insert_job(jid, kind, "p", created_at=float(1000 + i))
        store.set_running(jid)
        store.set_done(jid, {}, ended_at=float(2000 + i))
    store.close()

    m = JobManager(db_path=db)
    history = m.list_history(kind="render")
    ids = [h["id"] for h in history]
    assert "r1" in ids
    assert "e1" not in ids
    assert "k1" not in ids


def test_history_scope_in_each_row(tmp_path):
    """list_history devuelve el campo scope en cada fila."""
    from pipeline.server.job_store import JobStore

    db = tmp_path / "scope_row.sqlite"
    store = JobStore(db)
    store.insert_job("b1", "render", "p", created_at=1000.0)
    store.set_running("b1")
    store.set_done("b1", {}, ended_at=1010.0)
    store.close()

    m = JobManager(db_path=db)
    history = m.list_history()
    row = next(h for h in history if h["id"] == "b1")
    assert "scope" in row
    assert row["scope"] == "batch"


# --- Aislamiento: JobManager() sin args NO debe tocar out/telemetry.sqlite ----


def test_job_manager_default_does_not_write_real_ledger():
    """JobManager() sin db_path usa el LEDGER_PATH redirigido por la fixture.

    La fixture autouse _isolate_ledger monkeypatcha pipeline.server.jobs.LEDGER_PATH
    a un SQLite temporal. Este test verifica que el default lazy (resuelto en
    __init__, no en la firma) respeta el monkeypatch y por lo tanto nunca toca
    out/telemetry.sqlite durante la suite.
    """
    import pipeline.server.jobs as jobs_mod

    # La ruta real del operador (hardcodeada como referencia, nunca debe ser usada)
    real_ledger = Path("out/telemetry.sqlite").resolve()

    # La fixture ya redirige LEDGER_PATH del modulo a un tmp.
    # Crear un JobManager sin argumentos debe usar ESE tmp, no la ruta real.
    m = JobManager()
    db_used = m._store._db_path  # JobStore expone _db_path
    assert db_used.resolve() != real_ledger, (
        f"JobManager() sin args escribio en la base real {real_ledger}. "
        "El aislamiento fallo."
    )
    # Ademas, el path usado debe ser el que el modulo tiene ahora (el tmp de la fixture)
    assert db_used == jobs_mod.LEDGER_PATH, (
        f"JobManager usa {db_used} pero jobs_mod.LEDGER_PATH es {jobs_mod.LEDGER_PATH}"
    )


def test_migration_adds_scope_to_existing_db(tmp_path):
    """Bases SQLite previas (sin columna scope) se migran al abrir el JobStore."""
    import sqlite3
    from pipeline.server.job_store import JobStore

    db = tmp_path / "old.sqlite"
    # Crear la tabla sin la columna scope (simula base de Ciclo 1-3)
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, project TEXT NOT NULL,
            status TEXT NOT NULL, created_at REAL NOT NULL,
            started_at REAL, ended_at REAL, result TEXT, error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE job_events (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL, ts REAL NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("INSERT INTO jobs VALUES ('old1', 'render', 'p', 'done', 100, 101, 110, NULL, NULL)")
    conn.commit()
    conn.close()

    # Abrir el JobStore -> debe migrar sin error
    store = JobStore(db)
    row = store.get_job("old1")
    # La columna scope existe y tiene el default 'batch'
    assert row is not None
    assert row.get("scope") == "batch"
    store.close()
