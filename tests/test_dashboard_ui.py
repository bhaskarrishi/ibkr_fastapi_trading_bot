from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_dashboard_contains_brand_and_filter_button():
    resp = client.get('/dashboard/')
    assert resp.status_code == 200
    text = resp.text
    assert 'ALGO TRADER - By RB' in text
    assert 'id="filterRejected"' in text
    # P/L column header present
    assert '<th>P/L</th>' in text
    # Filter and Refresh button present
    assert 'id="filterRejected"' in text
    assert 'id="refreshBtn"' in text
    # Refresh status indicator present
    assert 'id="refreshStatus"' in text