from app.main import app
from fastapi.testclient import TestClient
from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models.trade import Trade

client = TestClient(app)


def test_rejected_trade_visible_in_api():
    db = SessionLocal()
    Base.metadata.create_all(bind=engine)
    # Insert a rejected trade
    db.add(Trade(symbol='ZZZ', side='BUY', qty=1, price=1.0, status='risk_rejected: test'))
    db.commit()

    resp = client.get('/dashboard/api/pnl')
    assert resp.status_code == 200
    data = resp.json()
    assert 'trades' in data
    found = any(t['symbol'] == 'ZZZ' and t['status'].startswith('risk_rejected') for t in data['trades'])
    assert found
    # PnL key should be present (None for non-filled/rejected trade)
    zzz = next(t for t in data['trades'] if t['symbol'] == 'ZZZ')
    assert 'pnl' in zzz and zzz['pnl'] is None

    db.close()