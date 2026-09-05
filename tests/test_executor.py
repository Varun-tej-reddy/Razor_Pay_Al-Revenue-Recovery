from unittest.mock import MagicMock
from agent.executor import execute_action

def test_execute_send_new_payment_link_mock_sdk():
    txn = {
        "transaction_id": "pay_test_9999",
        "amount": 2500.0,
        "currency": "INR",
        "customer_id": "cust_123",
        "customer_contact": {"email": "cust@example.com", "phone": "+919876543210"}
    }
    action = {"action": "send_new_payment_link"}

    # Mock real Razorpay client
    mock_client = MagicMock()
    mock_client.payment_link.create.return_value = {
        "id": "plink_live_mock_123",
        "short_url": "https://rzp.io/i/plink_live_mock_123",
        "status": "created"
    }

    result = execute_action(txn, action, client=mock_client)
    assert result["status"] == "executed"
    assert result["payment_link_id"] == "plink_live_mock_123"
    assert result["payment_link_url"] == "https://rzp.io/i/plink_live_mock_123"
    assert result["error"] is None
    # Verify amount was converted to paise (2500 * 100 = 250000)
    mock_client.payment_link.create.assert_called_once()
    call_args = mock_client.payment_link.create.call_args[1]["data"]
    assert call_args["amount"] == 250000
    assert call_args["currency"] == "INR"

def test_execute_escalate_to_human():
    txn = {
        "transaction_id": "pay_vip_1111",
        "amount": 18000.0,
        "customer_id": "cust_vip",
        "customer_contact": {}
    }
    action = {"action": "escalate_to_human"}
    result = execute_action(txn, action)
    assert result["status"] == "escalated_to_human"
    assert "VIP Concierge" in result["message_payload"]
    assert result["payment_link_id"] is None

def test_execute_no_action():
    txn = {"transaction_id": "pay_noop_2222", "amount": 500.0}
    action = {"action": "no_action"}
    result = execute_action(txn, action)
    assert result["status"] == "skipped"
    assert result["payment_link_id"] is None

def test_execute_razorpay_api_error_handling():
    txn = {
        "transaction_id": "pay_err_3333",
        "amount": 1000.0,
        "currency": "INR"
    }
    action = {"action": "send_new_payment_link"}

    # Mock client throwing an API gateway exception
    mock_client = MagicMock()
    mock_client.payment_link.create.side_effect = Exception("Razorpay API 500 Internal Server Error")

    result = execute_action(txn, action, client=mock_client)
    assert result["status"] == "failed"
    assert "Razorpay API 500" in result["error"]
    assert result["payment_link_id"] is None
