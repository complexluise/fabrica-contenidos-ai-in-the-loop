"""Core Studio (D-031): job manager — estados y registro (lógica pura)."""

from pipeline.server.jobs import Job, JobManager, JobStatus


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
