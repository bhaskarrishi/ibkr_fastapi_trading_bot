from sqlalchemy import Column, Integer, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class TradeSettings(Base):
    """User-configurable trading risk management parameters."""
    __tablename__ = "trade_settings"

    id = Column(Integer, primary_key=True, index=True)
    
    # Order size limits
    max_qty_per_order = Column(Integer, default=100, doc="Max quantity per single order")
    max_notional_per_order = Column(Float, default=50000.0, doc="Max notional value per order")
    max_orders_per_minute = Column(Integer, default=5, doc="Max orders allowed per minute")
    
    # Daily risk controls
    max_daily_loss = Column(Float, default=2000.0, doc="Max loss allowed per day before stopping trades")
    max_trades_per_day = Column(Integer, default=50, doc="Max number of trades per day")
    max_total_position_notional = Column(Float, default=250000.0, doc="Max total notional exposure across all positions")
    
    # Position limits
    max_position_per_symbol = Column(Integer, default=1000, doc="Max quantity for single symbol")
    
    # Market/RTH controls
    only_trade_during_rth = Column(Boolean, default=False, doc="If true, only allow trades during RTH (9:30-16:00 ET)")
    subscribe_to_strategy = Column(Boolean, default=True, doc="If false, reject incoming webhook orders")
    enable_signal_validation = Column(Boolean, default=True, doc="If true, validate signals with market data before placing orders")
    
    # Account checks
    min_buying_power_required = Column(Float, default=1000.0, doc="Minimum buying power required to place BUY order")
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
