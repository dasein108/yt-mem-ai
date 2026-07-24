import threading

from yt_summary.api import jobs
from yt_summary.api.jobs import JobRegistry, Worker


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


def test_worker_persists_each_transition():
    reg = JobRegistry()
    seen = []
    w = Worker(reg, persist=lambda job: seen.append((job.id, job.status)))
    job = w.submit("summarize", lambda j: {"ok": True}, video_id="abc")
    assert job.video_id == "abc"
    w.run_one(block=False)
    statuses = [s for (_id, s) in seen if _id == job.id]
    assert statuses[0] == "queued"
    assert statuses[-1] == "done"


def test_worker_runs_bounded_parallel():
    reg = JobRegistry()
    w = Worker(reg, concurrency=3)
    barrier = threading.Barrier(3, timeout=5)
    def fn(job):
        barrier.wait()  # only completes if 3 run concurrently
        return {}
    for _ in range(3):
        w.submit("x", fn)
    w.start()
    # if concurrency<3 this would deadlock the barrier and raise BrokenBarrierError
    for _ in range(50):
        if all(j.status == "done" for j in reg.list()):
            break
        threading.Event().wait(0.05)
    w.stop()
    assert all(j.status == "done" for j in reg.list())
