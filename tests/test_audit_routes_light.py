def test_audit_start_bad_body(client):
    rv = client.post("/api/audit/start", json={})
    assert rv.status_code == 400

def test_audit_start_ok(client, monkeypatch):
    # Evitar que llame a run_audit.delay real
    from app.routes import audit_routes

    class DummyAsync:
        id = "fake-task-id"

    def fake_delay(job_id, address, network):
        return DummyAsync()

    monkeypatch.setattr("app.tasks.audit_tasks.run_audit.delay", fake_delay)

    rv = client.post("/api/audit/start", json={"address": "0x0000000000000000000000000000000000000000"})
    assert rv.status_code == 202
    js = rv.get_json()
    assert js["ok"] is True
    assert js["status"] == "queued"
    assert "job_id" in js
