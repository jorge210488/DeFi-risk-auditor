def test_healthz(client):
    rv = client.get("/healthz")
    assert rv.status_code == 200
    assert rv.json["ok"] is True
