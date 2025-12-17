# app/routes/webhook.py
from fastapi import APIRouter, Depends
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from app.schemas.webhook import TradingViewAlert
from app.services.strategy import validate_signal
from app.services.broker import place_order_sync
from app.services.risk import RiskManager
from app.services.signal_validation import validate_signal as validate_signal_with_market_data
from app.database import SessionLocal
from app.models.trade import Trade
import asyncio
import logging
import json

router = APIRouter(prefix="/webhook", tags=["Webhook"])

executor = ThreadPoolExecutor(max_workers=2)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/tradingview")
async def tradingview_webhook(alert: TradingViewAlert, db: Session = Depends(get_db)):
    """
    Receives TradingView webhook JSON and validates signal using independent market data.
    
    Validation layers:
    1. Schema validation (qty, side)
    2. Server-side signal confirmation (market data from Yahoo Finance)
    3. Risk management checks
    4. Order placement to IBKR
    """
    # Layer 1: Schema validation
    if not validate_signal(alert):
        return {"status": "rejected", "reason": "invalid qty or side"}

    # Check user settings
    risk = RiskManager()
    user_settings = risk.get_user_settings(db)
    enable_validation = getattr(user_settings, 'enable_signal_validation', True)

    # Layer 2: Server-side signal confirmation using independent market data (if enabled)
    market_validation = None
    if enable_validation:
        logging.info(f"Validating signal: {alert.symbol} {alert.side}")
        market_validation = validate_signal_with_market_data(alert.symbol.upper(), alert.side.upper())
        
        if not market_validation['valid']:
            # Signal not confirmed by market data
            status = f"signal_rejected: {market_validation['metadata'].get('reason', 'validation failed')}"
            trade = Trade(
                symbol=alert.symbol.upper(),
                side=alert.side.upper(),
                qty=alert.qty,
                price=alert.price,
                status=status,
                validation_data=json.dumps(market_validation)  # Store validation details
            )
            db.add(trade)
            db.commit()
            logging.warning(
                f"Signal validation failed for {alert.symbol}: {market_validation['metadata'].get('reason')}"
            )
            return {
                "status": "rejected",
                "reason": "signal_not_confirmed",
                "validation": market_validation['metadata']
            }
        
        logging.info(
            f"Signal validated: {market_validation['metadata']['checks_passed']}/5 checks passed"
        )
    else:
        logging.info("Signal validation disabled - skipping market data confirmation")
        # Create empty validation data for consistency
        market_validation = {
            'valid': True,
            'metadata': {'decision': 'SKIPPED', 'reason': 'Signal validation disabled'}
        }

    # Layer 3: Subscription gate
    if not getattr(user_settings, 'subscribe_to_strategy', True):
        status = "risk_rejected: subscription_disabled"
        trade = Trade(
            symbol=alert.symbol.upper(),
            side=alert.side.upper(),
            qty=alert.qty,
            price=alert.price,
            status=status,
            validation_data=json.dumps(market_validation)
        )
        db.add(trade)
        db.commit()
        return {"status": "rejected", "reason": "subscription_disabled"}

    # Layer 4: Risk management checks
    ok, reason = risk.validate_order(alert.symbol.upper(), alert.side.upper(), alert.qty, alert.price, db)
    if not ok:
        status = f"risk_rejected: {reason}"
        # Save rejected trade and return
        trade = Trade(
            symbol=alert.symbol.upper(),
            side=alert.side.upper(),
            qty=alert.qty,
            price=alert.price,
            status=status,
            validation_data=json.dumps(market_validation)
        )
        db.add(trade)
        try:
            db.commit()
            logging.info("Trade saved (id=%s) with status: %s", getattr(trade, 'id', None), status)
        except Exception as e:
            db.rollback()
            logging.exception("DB commit failed for risk_rejected")
            return {"status": "db_error", "reason": str(e)}
        return {"status": "rejected", "reason": reason}

    # Run synchronous IBKR function in thread and handle errors
    loop = asyncio.get_running_loop()
    try:
        status = await loop.run_in_executor(executor, place_order_sync, alert.symbol, alert.side, alert.qty)
        logging.info("Order placed, worker returned status: %s", status)
    except Exception as e:
        logging.exception("Error placing order")
        status = f"error: {e}"

    # Parse execution price from status (e.g., "Filled | reason: Fill 10.0@273.89")
    executed_price = None
    if "Fill" in status and "@" in status:
        try:
            # Extract price from "Fill X.X@PRICE" pattern
            import re
            match = re.search(r'Fill\s+[\d.]+@([\d.]+)', status)
            if match:
                executed_price = float(match.group(1))
                logging.info("Parsed execution price: %s", executed_price)
        except Exception as e:
            logging.warning("Failed to parse execution price from status: %s", e)

    # Save trade in DB (all layers passed)
    trade = Trade(
        symbol=alert.symbol.upper(),
        side=alert.side.upper(),
        qty=alert.qty,
        price=alert.price,
        executed_price=executed_price,
        status=status,
        validation_data=json.dumps(market_validation)
    )
    db.add(trade)
    try:
        db.commit()
        logging.info("Trade saved (id=%s) with status: %s", getattr(trade, 'id', None), status)        # Broadcast new trade and updated PnL
        try:
            from app.services.broadcaster import broadcaster
            from app.services.pnl import compute_pnl_by_ticker, compute_daily_realized_pnl
            # prepare payloads
            from app.services.pnl import compute_trade_pnls
            tpnl = compute_trade_pnls(db)
            pnl_val = tpnl.get(trade.id, {}).get('net') if tpnl else None
            tpayload = {
                'type': 'new_trade',
                'trade': {
                    'id': trade.id,
                    'timestamp': str(trade.timestamp),
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'qty': trade.qty,
                    'price': trade.price,
                    'pnl': pnl_val,
                    'status': trade.status,
                }
            }
            await broadcaster.broadcast(tpayload)

            pnl = compute_pnl_by_ticker(db)
            dpayload = {
                'type': 'pnl_update',
                'tickers': list(pnl.values()),
                'daily_realized': compute_daily_realized_pnl(db)
            }
            await broadcaster.broadcast(dpayload)
        except Exception:
            logging.exception("Broadcast failed")
    except Exception as e:
        db.rollback()
        logging.exception("DB commit failed")
        return {"status": "db_error", "reason": str(e)}

    return {"status": "success", "order_status": status}