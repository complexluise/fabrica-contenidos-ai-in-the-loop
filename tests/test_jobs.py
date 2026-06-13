"""Core Studio (D-031): job manager — estados y registro (lógica pura)."""

import asyncio

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
