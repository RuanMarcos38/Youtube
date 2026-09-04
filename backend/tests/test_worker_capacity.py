from app import worker


def test_pipeline_concurrency_uses_five_slots(monkeypatch):
    monkeypatch.setattr(worker.settings, "worker_concurrency", 5)
    assert worker._pipeline_concurrency() == 5


def test_pipeline_concurrency_never_claims_six(monkeypatch):
    monkeypatch.setattr(worker.settings, "worker_concurrency", 9)
    assert worker._pipeline_concurrency() == 5


def test_pipeline_concurrency_honors_lower_runtime_guard(monkeypatch):
    monkeypatch.setattr(worker.settings, "worker_concurrency", 3)
    assert worker._pipeline_concurrency() == 3
