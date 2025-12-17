from collections import deque, defaultdict
from typing import Dict, Any
from app.models.trade import Trade
from sqlalchemy.orm import Session
from datetime import datetime, timezone, date


def compute_pnl_by_ticker(db: Session) -> Dict[str, Dict[str, Any]]:
    """Compute realized, unrealized and cumulative PnL per ticker using FIFO matching.
    Assumes `Trade` rows with status starting with 'Filled' represent executed trades.
    Returns dict keyed by symbol with fields: position, realized, unrealized, cumulative, last_price
    """
    # Query filled trades ordered by timestamp (status starts with 'Filled')
    trades = db.query(Trade).filter(Trade.status.like('Filled%')).order_by(Trade.timestamp).all()

    results = {}
    # For each symbol, maintain a deque of (qty, price) for buys; positive qty for long buys
    books = defaultdict(deque)
    # track last price for unrealized value reference
    last_price = {}
    realized = defaultdict(float)

    for t in trades:
        sym = t.symbol
        side = t.side.upper()
        qty = int(t.qty)
        price = float(t.price)
        last_price[sym] = price

        if side == 'BUY':
            # add to book
            books[sym].append({'qty': qty, 'price': price})
        elif side == 'SELL':
            # match against buys (FIFO). If no buys, treat as short sell (negative book)
            remaining = qty
            while remaining > 0 and books[sym]:
                lot = books[sym][0]
                take = min(lot['qty'], remaining)
                realized[sym] += (price - lot['price']) * take
                lot['qty'] -= take
                remaining -= take
                if lot['qty'] == 0:
                    books[sym].popleft()
            # if still remaining (shorting), represent as negative position via a negative lot
            if remaining > 0:
                # push negative lot (short)
                books[sym].appendleft({'qty': -remaining, 'price': price})

    # compute positions and unrealized P/L
    # Note: last_price and lot prices are all IBKR execution prices (executed_price field)
    for sym, book in books.items():
        pos = sum(l['qty'] for l in book)
        lp = last_price.get(sym, None)  # Last execution price from IBKR
        unreal = 0.0
        if lp is not None:
            for l in book:
                # Unrealized P/L = (Last exec price - Entry exec price) × Qty
                unreal += (lp - l['price']) * l['qty']
        results[sym] = {
            'symbol': sym,
            'position': pos,
            'realized': round(realized.get(sym, 0.0), 6),
            'unrealized': round(unreal, 6),
            'cumulative': round(realized.get(sym, 0.0) + unreal, 6),
            'last_price': lp,  # IBKR execution price
        }
    return results


def compute_daily_realized_pnl(db: Session, day: date = None) -> float:
    """Compute the net realized PnL for trades realized on a given day (UTC dates).
    Implementation: go through filled trades up to the day and compute realized PnL for fills that happened on that day.
    """
    if day is None:
        day = datetime.now(timezone.utc).date()

    # We'll compute realized PnL by simulating FIFO up to each trade and summing PnL for sell trades whose timestamp date equals the day
    trades = db.query(Trade).filter(Trade.status.like('Filled%')).order_by(Trade.timestamp).all()

    books = defaultdict(deque)
    daily_realized = 0.0

    for t in trades:
        sym = t.symbol
        side = t.side.upper()
        qty = int(t.qty)
        # Use executed_price if available, otherwise fall back to webhook price
        price = float(t.executed_price) if t.executed_price is not None else float(t.price)
        ts_date = t.timestamp.date()

        if side == 'BUY':
            books[sym].append({'qty': qty, 'price': price})
        else:  # SELL
            remaining = qty
            while remaining > 0 and books[sym]:
                lot = books[sym][0]
                take = min(lot['qty'], remaining)
                pnl = (price - lot['price']) * take
                # If this sell happened on the day, count its pnl towards daily realized
                if ts_date == day:
                    daily_realized += pnl
                lot['qty'] -= take
                remaining -= take
                if lot['qty'] == 0:
                    books[sym].popleft()
            # remaining negative means we went short; for simplicity, consider remaining realized when later buys match

    return round(daily_realized, 6)


def compute_trade_pnls(db: Session):
    """Compute per-trade realized and unrealized PnL (net) for trades with status starting with 'Filled'.
    Returns a dict mapping trade_id -> {'realized': float, 'unrealized': float, 'net': float}
    Uses FIFO matching and attributes unrealized PnL for remaining open lots to their originating trade id.
    """
    trades = db.query(Trade).filter(Trade.status.like('Filled%')).order_by(Trade.timestamp).all()

    # For each symbol, maintain deque of lots: {'qty': int, 'price': float, 'trade_id': int}
    from collections import deque, defaultdict

    books = defaultdict(deque)
    last_price = {}
    per_trade = defaultdict(lambda: {'realized': 0.0, 'unrealized': 0.0})

    for t in trades:
        sym = t.symbol
        side = t.side.upper()
        qty = int(t.qty)
        # Use executed_price if available, otherwise fall back to webhook price
        price = float(t.executed_price) if t.executed_price is not None else float(t.price)
        last_price[sym] = price

        if side == 'BUY':
            remaining = qty
            # If there are short lots (qty negative) realize against them
            while remaining > 0 and books[sym] and books[sym][0]['qty'] < 0:
                lot = books[sym][0]
                take = min(remaining, abs(lot['qty']))
                # realized for covering short: short_entry_price - cover_price
                realized_amt = (lot['price'] - price) * take
                per_trade[t.id]['realized'] += round(realized_amt, 6)
                lot['qty'] += take  # move towards zero (since lot['qty'] negative)
                remaining -= take
                if lot['qty'] == 0:
                    books[sym].popleft()
            # any remaining opens a long lot
            if remaining > 0:
                books[sym].append({'qty': remaining, 'price': price, 'trade_id': t.id})

        elif side == 'SELL':
            remaining = qty
            # match against long lots
            while remaining > 0 and books[sym] and books[sym][0]['qty'] > 0:
                lot = books[sym][0]
                take = min(remaining, lot['qty'])
                realized_amt = (price - lot['price']) * take
                per_trade[t.id]['realized'] += round(realized_amt, 6)
                lot['qty'] -= take
                remaining -= take
                if lot['qty'] == 0:
                    books[sym].popleft()
            # any remaining creates a short lot
            if remaining > 0:
                books[sym].appendleft({'qty': -remaining, 'price': price, 'trade_id': t.id})

    # After processing all trades, attribute unrealized for remaining lots to their originating trade ids using last_price
    for sym, book in books.items():
        lp = last_price.get(sym, None)
        if lp is None:
            continue
        for lot in book:
            qty = lot['qty']
            price = lot['price']
            if qty > 0:
                unreal = (lp - price) * qty
            else:
                unreal = (price - lp) * abs(qty)
            per_trade[lot.get('trade_id')]['unrealized'] += round(unreal, 6)

    # Consolidate
    out = {}
    for tid, vals in per_trade.items():
        r = round(vals.get('realized', 0.0), 6)
        u = round(vals.get('unrealized', 0.0), 6)
        out[tid] = {'realized': r, 'unrealized': u, 'net': round(r + u, 6)}
    return out