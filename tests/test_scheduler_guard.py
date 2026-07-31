from __future__ import annotations

from services import scheduler_guard


def test_record_and_list_status(monkeypatch):
    bucket = {}
    monkeypatch.setattr(scheduler_guard.store, "get_kv", lambda key, default=None: bucket.get(key, default))
    monkeypatch.setattr(scheduler_guard.store, "set_kv", lambda key, value: bucket.setdefault(key, value) if key not in bucket else bucket.update({key: value}) or value)

    scheduler_guard.record_status("hotspot-refresh", status="completed", elapsedSeconds=1.23)
    status = scheduler_guard.list_status(("hotspot-refresh",))

    assert status["hotspot-refresh"]["status"] == "completed"
    assert status["hotspot-refresh"]["elapsedSeconds"] == 1.23
