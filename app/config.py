import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME = "IBKR Paper Trading Bot"
    ENV = os.getenv("ENV", "development")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trades.db")

    # Risk management defaults
    MAX_ORDER_QTY = int(os.getenv("MAX_ORDER_QTY", "100"))
    MAX_ORDER_NOTIONAL = float(os.getenv("MAX_ORDER_NOTIONAL", "50000"))
    MAX_POSITION_PER_SYMBOL = int(os.getenv("MAX_POSITION_PER_SYMBOL", "1000"))
    MAX_TOTAL_EXPOSURE = float(os.getenv("MAX_TOTAL_EXPOSURE", "250000"))
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "2000"))

settings = Settings()