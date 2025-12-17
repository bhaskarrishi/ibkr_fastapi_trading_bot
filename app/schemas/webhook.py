from pydantic import BaseModel

class TradingViewAlert(BaseModel):
    symbol: str
    side: str
    qty: int
    price: float