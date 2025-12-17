from fastapi.testclient import TestClient
from app.main import app
from app.routes import webhook


class DummyDB:
    def __init__(self, fail_commit=False):
        self.added = None
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit

    def add(self, obj):
        self.added = obj

    def commit(self):
        if self.fail_commit:
            raise Exception("db commit failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


client = TestClient(app)


def test_tradingview_webhook_success(monkeypatch):
    dummy_db = DummyDB()

    def override_get_db():
        try:
            yield dummy_db
        finally:
            pass

    app.dependency_overrides[webhook.get_db] = override_get_db
    monkeypatch.setattr(webhook, "place_order_sync", lambda symbol, side, qty: "Filled")

    resp = client.post("/webhook/tradingview", json={"symbol": "AAPL", "side": "BUY", "qty": 1, "price": 150.0})

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["order_status"] == "Filled"

    assert dummy_db.added is not None
    assert dummy_db.added.symbol == "AAPL"
    assert dummy_db.committed is True

    app.dependency_overrides.clear()


def test_tradingview_webhook_risk_reject(monkeypatch):
    # Force a low max qty so the order is rejected by risk manager
    from app.config import settings
    old_max = settings.MAX_ORDER_QTY
    settings.MAX_ORDER_QTY = 1

    dummy_db = DummyDB()

    def override_get_db():
        try:
            yield dummy_db
        finally:
            pass

    app.dependency_overrides[webhook.get_db] = override_get_db
    monkeypatch.setattr(webhook, "place_order_sync", lambda symbol, side, qty: "Filled")

    resp = client.post("/webhook/tradingview", json={"symbol": "AAPL", "side": "BUY", "qty": 5, "price": 150.0})

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert "qty_exceeds_max" in resp.json()["reason"]

    # The trade should be saved with risk_rejected status
    assert dummy_db.added is not None
    assert dummy_db.added.status.startswith("risk_rejected")

    app.dependency_overrides.clear()
    settings.MAX_ORDER_QTY = old_max


def test_tradingview_webhook_order_error(monkeypatch):
    dummy_db = DummyDB()

    def override_get_db():
        try:
            yield dummy_db
        finally:
            pass

    app.dependency_overrides[webhook.get_db] = override_get_db

    def raise_exc(symbol, side, qty):
        raise Exception("IB down")

    monkeypatch.setattr(webhook, "place_order_sync", raise_exc)

    resp = client.post("/webhook/tradingview", json={"symbol": "AAPL", "side": "BUY", "qty": 1, "price": 150.0})

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["order_status"].startswith("error:")
    assert dummy_db.added.status.startswith("error:")
    assert dummy_db.committed is True

    app.dependency_overrides.clear()


def test_tradingview_webhook_db_commit_failure(monkeypatch):
    dummy_db = DummyDB(fail_commit=True)

    def override_get_db():
        try:
            yield dummy_db
        finally:
            pass

    app.dependency_overrides[webhook.get_db] = override_get_db
    monkeypatch.setattr(webhook, "place_order_sync", lambda symbol, side, qty: "Filled")

    resp = client.post("/webhook/tradingview", json={"symbol": "AAPL", "side": "BUY", "qty": 1, "price": 150.0})

    assert resp.status_code == 200
    assert resp.json()["status"] == "db_error"
    assert "db commit failed" in resp.json()["reason"]
    assert dummy_db.rolled_back is True

    app.dependency_overrides.clear()