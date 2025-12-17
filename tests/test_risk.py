from app.services.risk import RiskManager
from app.models.trade import Trade
from app.database import Base, engine, SessionLocal
from sqlalchemy.orm import Session


def create_session():
    # Use the existing engine (sqlite file) but create test table state
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_validate_basic_limits():
    db = create_session()
    rm = RiskManager()

    # qty bigger than MAX_ORDER_QTY should be rejected
    ok, reason = rm.validate_order('AAPL', 'BUY', rm.settings.MAX_ORDER_QTY + 1, 10.0, db)
    assert not ok
    assert 'qty_exceeds_max' in reason

    # notional larger than MAX_ORDER_NOTIONAL
    large_qty = int(rm.settings.MAX_ORDER_NOTIONAL // 1_000) + 1
    ok, reason = rm.validate_order('AAPL', 'BUY', large_qty, 1000.0, db)
    assert not ok
    assert 'notional_exceeds_max' in reason

    db.close()


def test_position_limit_enforced():
    db = create_session()
    rm = RiskManager()

    # Create existing filled position near the limit
    t = Trade(symbol='AAPL', side='BUY', qty=rm.settings.MAX_POSITION_PER_SYMBOL - 1, price=100.0, status='Filled')
    db.add(t)
    db.commit()

    # Trying to buy 5 more should exceed position limit
    ok, reason = rm.validate_order('AAPL', 'BUY', 5, 100.0, db)
    assert not ok
    assert 'position_limit_exceeded' in reason

    db.close()