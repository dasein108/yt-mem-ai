from yt_summary.api import jobs


def test_worker_runs_job_to_done():
    w = jobs.Worker(jobs.JobRegistry())
    job = w.submit("test", lambda j: {"ok": True})
    assert job.status == "queued"
    assert w.run_one(block=False) is True
    assert job.status == "done"
    assert job.result == {"ok": True}


def test_worker_records_error_and_survives():
    reg = jobs.JobRegistry()
    w = jobs.Worker(reg)
    bad = w.submit("test", lambda j: (_ for _ in ()).throw(RuntimeError("boom")))
    good = w.submit("test", lambda j: {"ok": 1})
    assert w.run_one(block=False) is True   # bad
    assert bad.status == "error" and "boom" in bad.error
    assert w.run_one(block=False) is True   # worker survived → good runs
    assert good.status == "done"


def test_run_one_empty_returns_false():
    w = jobs.Worker(jobs.JobRegistry())
    assert w.run_one(block=False) is False


def test_registry_get_and_list():
    reg = jobs.JobRegistry()
    w = jobs.Worker(reg)
    job = w.submit("k", lambda j: {})
    assert reg.get(job.id) is job
    assert job in reg.list()
    assert reg.get("nope") is None
