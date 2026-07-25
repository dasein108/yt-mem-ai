import time
import lancedb
from fastapi.testclient import TestClient
from tests.support import fake_embedder
from yt_summary.config import Config
from yt_summary.store import db as store
from yt_summary.api.app import create_app


def _cfg(tmp_path):
    return Config(downloads_dir=tmp_path / "dl", proxy_username=None, proxy_password=None,
                  cookies_browser=None, whisper_model="small", whisper_device="cpu",
                  whisper_compute_type="int8", openrouter_api_key=None,
                  store_path=tmp_path / "lance", embedding_backend="local", embedding_model=None,
                  chunk_target_s=45.0, openai_api_key=None, openrouter_model="test/model")


def _setup(tmp_path):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    app = create_app(_cfg(tmp_path), store_opener=lambda: conn, start_worker=False)
    return TestClient(app), app, conn


def test_fetch_job_enqueues_and_runs(tmp_path, monkeypatch):
    client, app, conn = _setup(tmp_path)
    # patch run_fetch used by the job closure
    monkeypatch.setattr("yt_summary.api.app_jobs.run_fetch",
                        lambda url, cfg, force=False, db=None, video_id=None: "vid123")
    with client:
        r = client.post("/jobs/fetch", json={"url": "https://y/abc"})
        assert r.status_code == 200
        jid = r.json()["id"]
        assert r.json()["status"] == "queued"
        # drain inline (worker not started)
        assert app.state.worker.run_one(block=False) is True
        got = client.get(f"/jobs/{jid}").json()
        assert got["status"] == "done"
        assert got["result"] == {"video_id": "vid123"}


def test_jobs_list_and_404(tmp_path):
    client, app, conn = _setup(tmp_path)
    with client:
        client.post("/jobs/discover", json={})
        assert len(client.get("/jobs").json()) == 1
        assert client.get("/jobs/nope").status_code == 404


def test_recovery_requeues_and_resets_running(tmp_path, monkeypatch):
    from yt_summary.config import load_config

    cfg = load_config(tmp_path / "none.env")
    object.__setattr__(cfg, "discover_interval_s", 0.0)  # disable auto-sync in this test
    conn = lancedb.connect(str(tmp_path / "l"))
    store.init_db(conn, fake_embedder())
    # a leftover 'running' (interrupted) + a 'queued' job persisted before restart
    store.insert_job(conn, {"id": "r1", "kind": "discover", "video_id": None,
                            "status": "running", "progress": None, "error": None,
                            "created_at": "t", "updated_at": "t"})
    store.insert_job(conn, {"id": "q1", "kind": "summarize", "video_id": "abc",
                            "status": "queued", "progress": None, "error": None,
                            "created_at": "t", "updated_at": "t"})
    monkeypatch.setattr("yt_summary.api.app_jobs.run_discover",
                        lambda *a, **k: ([], 0))
    monkeypatch.setattr("yt_summary.api.app_jobs.summarize_video",
                        lambda *a, **k: {"video_id": "abc"})
    app = create_app(cfg, store_opener=lambda: conn, start_worker=False)
    with TestClient(app):  # triggers lifespan
        # recovery drained into the worker; run them synchronously
        while app.state.worker.run_one(block=False):
            pass
    assert store.get_job(conn, "r1")["status"] == "done"   # requeued + ran
    assert store.get_job(conn, "q1")["status"] == "done"


def test_fetch_job_runs_on_real_worker_thread(tmp_path, monkeypatch):
    conn = lancedb.connect(str(tmp_path / "lance"))
    store.init_db(conn, fake_embedder())
    monkeypatch.setattr("yt_summary.api.app_jobs.run_fetch",
                        lambda url, cfg, force=False, db=None, video_id=None: "vid123")
    app = create_app(_cfg(tmp_path), store_opener=lambda: conn, start_worker=True)
    client = TestClient(app)
    with client:
        r = client.post("/jobs/fetch", json={"url": "https://y/abc"})
        assert r.status_code == 200
        jid = r.json()["id"]

        deadline = time.monotonic() + 2.0
        got = client.get(f"/jobs/{jid}").json()
        while got["status"] not in ("done", "error") and time.monotonic() < deadline:
            time.sleep(0.02)
            got = client.get(f"/jobs/{jid}").json()

        assert got["status"] == "done"
        assert got["result"] == {"video_id": "vid123"}
