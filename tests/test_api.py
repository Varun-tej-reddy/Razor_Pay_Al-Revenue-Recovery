from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "AI Revenue Recovery Agent" in data["service"]

def test_api_run_batch_default_sample():
    res = client.post("/run-batch", json={})
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert data["summary"]["total_processed"] == 60
    assert data["summary"]["flagged_at_risk_count"] == 45
    assert data["summary"]["recovered_transactions_count"] > 0
    batch_id = data["batch_id"]

    # Test audit trail endpoint
    trail_res = client.get(f"/audit-trail/{batch_id}")
    assert trail_res.status_code == 200
    trail_data = trail_res.json()
    assert trail_data["count"] == 60
    assert len(trail_data["records"]) == 60

    # Test report endpoint
    report_res = client.get(f"/report/{batch_id}")
    assert report_res.status_code == 200
    rep = report_res.json()
    assert rep["summary"]["total_processed"] == 60

def test_api_invalid_auth_token():
    res = client.post("/run-batch", json={}, headers={"X-API-Key": "wrong_key_123"})
    assert res.status_code == 401
    assert "Invalid or missing API key" in res.json()["detail"]

def test_payment_link_dual_portals():
    # 1. Test Red Action-Required View for unrecovered checkout
    res_red = client.get("/pay/test_link_01?txn=txn_unit_01&amount=1999.00&recovered=0&failed_inst=Visa+Card&fail_reason=Declined")
    assert res_red.status_code == 200
    assert "ACTION REQUIRED" in res_red.text
    assert "Failed Customer Attempt" in res_red.text
    assert "Pay ₹1,999.00" in res_red.text

    # 2. Test Green Settled-Receipt View for recovered checkout
    res_green = client.get("/pay/test_link_02?txn=txn_unit_02&amount=2999.00&recovered=1&paying_inst=Kotak+Bank+UPI")
    assert res_green.status_code == 200
    assert "PAID & SETTLED" in res_green.text
    assert "Payment Captured & Settled!" in res_green.text
    assert "Settled Payment Telemetry" in res_green.text
    assert 'id="payButton"' not in res_green.text

    # 3. Test capture-payment endpoint
    res_cap = client.post("/api/capture-payment?txn=txn_unit_01&amount=1999.00")
    assert res_cap.status_code == 200
    assert res_cap.json()["status"] == "success"

    # 4. Verify DB auto-detect transitions to Green Settled View
    res_auto = client.get("/pay/test_link_01?txn=txn_unit_01")
    assert res_auto.status_code == 200
    assert "PAID & SETTLED" in res_auto.text
    assert 'id="payButton"' not in res_auto.text

