from fastapi import FastAPI
from app.database import Base, engine
from app.routes import webhook
from app.routes import dashboard
from app.config import settings
# Import all models to ensure they're registered with SQLAlchemy
from app.models.trade import Trade
from app.models.settings import TradeSettings
from app.models.open_order import OpenOrder

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

app.include_router(webhook.router)
app.include_router(dashboard.router)

@app.get("/")
def root():
    return {"message": "IBKR Paper Trading Bot API is running"}

@app.get("/auth")
def auth_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard/auth")

@app.get("/signup")
def signup_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/dashboard/signup")