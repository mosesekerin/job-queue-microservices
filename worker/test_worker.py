import fakeredis
import worker


def test_process_job_marks_completed(monkeypatch):
    worker.r = fakeredis.FakeRedis()
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)  # skip the fake 2s work
    worker.process_job("abc-123")
    assert worker.r.hget("job:abc-123", "status") == b"completed"
