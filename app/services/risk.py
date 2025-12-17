from typing import Tuple, Optional
from app.config import settings
from app.models.trade import Trade
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, time
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, settings_obj=None):
        self.settings = settings_obj or settings

    def get_user_settings(self, db: Session):
        """Fetch user-configured trade settings from DB, or create defaults."""
        from app.models.settings import TradeSettings
        setting = db.query(TradeSettings).first()
        if not setting:
            setting = TradeSettings()
            db.add(setting)
            db.commit()
        return setting

    def is_market_open_rth(self) -> bool:
        """Check if current time is within RTH (9:30 AM - 4:00 PM ET).
        Simplified check; does not account for holidays.
        """
        import pytz
        et = pytz.timezone('America/New_York')
        now = datetime.now(et)
        # RTH: 9:30 - 16:00 (4 PM)
        rth_start = time(9, 30)
        rth_end = time(16, 0)
        # Only check on weekdays
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return rth_start <= now.time() <= rth_end

    def check_daily_loss_limit(self, db: Session, user_settings) -> Tuple[bool, Optional[str]]:
        """Check if daily loss exceeds threshold."""
        from app.services.pnl import compute_daily_realized_pnl
        daily_pnl = compute_daily_realized_pnl(db)
        if daily_pnl < user_settings.max_daily_loss * -1:
            return False, f"daily_loss_limit_exceeded (loss: {daily_pnl}, limit: -{user_settings.max_daily_loss})"
        return True, None

    def check_daily_trade_count(self, db: Session, user_settings) -> Tuple[bool, Optional[str]]:
        """Check if daily trade count exceeds threshold."""
        from datetime import date, timedelta
        today = date.today()
        trade_count = db.query(Trade).filter(
            func.date(Trade.timestamp) == today,
            Trade.status.like('Filled%')
        ).count()
        if trade_count >= user_settings.max_trades_per_day:
            return False, f"max_trades_per_day_exceeded ({trade_count} >= {user_settings.max_trades_per_day})"
        return True, None

    def check_open_order_duplicate(self, symbol: str, side: str, db: Session) -> Tuple[bool, Optional[str]]:
        """Check if there's already a pending order for this symbol/side."""
        from app.models.open_order import OpenOrder
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(minutes=1)  # Check last 1 minute for pending orders
        existing = db.query(OpenOrder).filter(
            OpenOrder.symbol == symbol,
            OpenOrder.side == side,
            OpenOrder.filled_at.is_(None),
            OpenOrder.created_at > cutoff
        ).first()
        if existing:
            return False, f"pending_{side.lower()}_order_exists_for_{symbol}"
        return True, None

    def check_position_for_sell(self, symbol: str, qty: int, db: Session) -> Tuple[bool, Optional[str]]:
        """Check if we hold sufficient quantity to sell."""
        try:
            buys = db.query(func.coalesce(func.sum(Trade.qty), 0)).filter(
                Trade.symbol == symbol, 
                Trade.status.like('Filled%'), 
                Trade.side == 'BUY'
            ).scalar() or 0
            sells = db.query(func.coalesce(func.sum(Trade.qty), 0)).filter(
                Trade.symbol == symbol, 
                Trade.status.like('Filled%'), 
                Trade.side == 'SELL'
            ).scalar() or 0
            position = (buys or 0) - (sells or 0)
        except Exception as e:
            logger.exception("Error checking position for sell")
            position = 0

        if position < qty:
            return False, f"insufficient_position_to_sell (have: {position}, want: {qty})"
        return True, None

    def validate_order(self, symbol: str, side: str, qty: int, price: float, db: Session) -> Tuple[bool, Optional[str]]:
        """Validate an outgoing order against all configured risk rules.
        Returns (ok, reason) where reason is provided if not ok.
        """
        user_settings = self.get_user_settings(db)

        # 1. Basic checks
        if qty <= 0:
            return False, "qty_must_be_positive"

        if qty > user_settings.max_qty_per_order:
            return False, f"qty_exceeds_max ({qty} > {user_settings.max_qty_per_order})"

        notional = qty * price
        if notional > user_settings.max_notional_per_order:
            return False, f"notional_exceeds_max ({notional} > {user_settings.max_notional_per_order})"

        # 2. RTH check (if enabled)
        if user_settings.only_trade_during_rth:
            if not self.is_market_open_rth():
                return False, "market_not_open_rth_only_trading_enabled"

        # 3. Daily loss limit check
        ok, reason = self.check_daily_loss_limit(db, user_settings)
        if not ok:
            return False, reason

        # 4. Daily trade count check
        ok, reason = self.check_daily_trade_count(db, user_settings)
        if not ok:
            return False, reason

        # 5. Open order duplicate check
        ok, reason = self.check_open_order_duplicate(symbol, side, db)
        if not ok:
            return False, reason

        # 6. For SELL orders, check position
        if side.upper() == 'SELL':
            ok, reason = self.check_position_for_sell(symbol, qty, db)
            if not ok:
                return False, reason

        # 7. Position per symbol check
        try:
            buys = db.query(func.coalesce(func.sum(Trade.qty), 0)).filter(
                Trade.symbol == symbol, 
                Trade.status.like('Filled%'), 
                Trade.side == 'BUY'
            ).scalar() or 0
            sells = db.query(func.coalesce(func.sum(Trade.qty), 0)).filter(
                Trade.symbol == symbol, 
                Trade.status.like('Filled%'), 
                Trade.side == 'SELL'
            ).scalar() or 0
            pos_q = (buys or 0) - (sells or 0)
        except Exception:
            pos_q = 0

        # New position after this order
        if side.upper() == 'BUY':
            new_pos = (pos_q or 0) + qty
        else:
            new_pos = (pos_q or 0) - qty

        if abs(new_pos) > user_settings.max_position_per_symbol:
            return False, f"position_limit_exceeded (would be {new_pos}, max {user_settings.max_position_per_symbol})"

        # 8. Total exposure check
        try:
            total_exposure = db.query(func.coalesce(func.sum(func.abs(Trade.qty * Trade.price)), 0)).filter(
                Trade.status.like('Filled%')
            ).scalar() or 0
        except Exception:
            total_exposure = 0

        if (total_exposure + abs(notional)) > user_settings.max_total_position_notional:
            return False, f"total_exposure_exceeded (would be {total_exposure + abs(notional)} > {user_settings.max_total_position_notional})"

        # Passed all checks
        return True, None
