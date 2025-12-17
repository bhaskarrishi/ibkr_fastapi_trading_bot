from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from app.database import Base

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    side = Column(String)
    qty = Column(Integer)
    price = Column(Float)  # Webhook/alert price
    executed_price = Column(Float, nullable=True)  # Actual market execution price
    status = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    validation_data = Column(Text, nullable=True)  # Stores validation results as JSON