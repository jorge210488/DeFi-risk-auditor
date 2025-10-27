def test_ai_predict_ok(client):
    rv = client.post("/api/ai/predict", json={"feature1": 0.3, "feature2": -0.4})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert "risk_score" in data
