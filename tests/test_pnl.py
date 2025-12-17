from app.services.pnl import compute_pnl_by_ticker, compute_daily_realized_pnl
from app.database import Base, engine, SessionLocal
from app.models.trade import Trade
from datetime import datetime, timezone, date


def create_session():
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_pnl_fifo_and_daily():
    db = create_session()
    # Clear any existing rows
    db.query(Trade).delete()
    db.commit()

    # BUY 10 @ 10
    t1 = Trade(symbol='FOO', side='BUY', qty=10, price=10.0, status='Filled', timestamp=datetime(2025,12,16,0,1, tzinfo=timezone.utc))
    # BUY 5 @ 12
    t2 = Trade(symbol='FOO', side='BUY', qty=5, price=12.0, status='Filled', timestamp=datetime(2025,12,16,0,2, tzinfo=timezone.utc))
    # SELL 8 @ 15 (realizes 8*(avg matched) => 8*((10@10 -> take 8) => (15-10)*8 = 40) realized)
    t3 = Trade(symbol='FOO', side='SELL', qty=8, price=15.0, status='Filled', timestamp=datetime(2025,12,16,0,3, tzinfo=timezone.utc))

    db.add_all([t1, t2, t3])
    db.commit()

    tickers = compute_pnl_by_ticker(db)
    foo = tickers['FOO']
    assert foo['realized'] == 40.0
    # remaining position is (10+5 -8) =7; remaining lots: 2@10 left? Actually 10 had 8 consumed -> 2@10 left and 5@12 -> net 7 units in book
    assert foo['position'] == 7

    daily = compute_daily_realized_pnl(db, date(2025,12,16))
    assert daily == 40.0

    db.close()


def test_compute_trade_pnls_per_trade():
    db = create_session()
    db.query(Trade).delete()
    db.commit()

    # BUY 10 @ 10 (t1)
    t1 = Trade(symbol='FOO', side='BUY', qty=10, price=10.0, status='Filled', timestamp=datetime(2025,12,16,0,1, tzinfo=timezone.utc))
    # BUY 5 @ 12 (t2)
    t2 = Trade(symbol='FOO', side='BUY', qty=5, price=12.0, status='Filled', timestamp=datetime(2025,12,16,0,2, tzinfo=timezone.utc))
    # SELL 8 @ 15 (t3) -> realizes 40
    t3 = Trade(symbol='FOO', side='SELL', qty=8, price=15.0, status='Filled', timestamp=datetime(2025,12,16,0,3, tzinfo=timezone.utc))

    db.add_all([t1, t2, t3])
    db.commit()

    from app.services.pnl import compute_trade_pnls
    pnls = compute_trade_pnls(db)

    # find db ids
    t1_id = db.query(Trade).filter(Trade.timestamp == t1.timestamp).one().id
    t2_id = db.query(Trade).filter(Trade.timestamp == t2.timestamp).one().id
    t3_id = db.query(Trade).filter(Trade.timestamp == t3.timestamp).one().id

    # t3 should have realized 40.0
    assert pnls[t3_id]['realized'] == 40.0
    assert pnls[t3_id]['net'] == 40.0

    # t1: remaining 2 units @10 unrealized at last price 15 => (15-10)*2 = 10
    assert pnls[t1_id]['unrealized'] == 10.0
    # t2: remaining 5 units @12 unrealized => (15-12)*5 = 15
    assert pnls[t2_id]['unrealized'] == 15.0

    db.close()