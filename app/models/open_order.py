from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class OpenOrder(Base):
    """Track open/pending orders to avoid duplicates."""
    __tablename__ = "open_orders"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    side = Column(String)  # BUY or SELL
    qty = Column(Integer)
    price = Column(Float)
    order_id = Column(String, nullable=True, doc="IBKR order ID if available")
    created_at = Column(DateTime, server_default=func.now(), index=True)
    filled_at = Column(DateTime, nullable=True, doc="When order was filled or cancelled")
