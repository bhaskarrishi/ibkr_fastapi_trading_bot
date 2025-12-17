import sys
import sys
from ib_insync import IB, Stock, MarketOrder


def main(symbol: str, side: str, qty: int) -> int:
    """Run a synchronous IBKR order placement in a fresh process.
    Prints a clear machine-friendly STATUS line on stdout (e.g. `STATUS: Filled`)
    and prints errors to stderr. Returns 0 on success, non-zero on error.
    """
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=1)

        contract = Stock(symbol.upper(), 'SMART', 'USD')
        ib.qualifyContracts(contract)

        order = MarketOrder(side.upper(), qty)
        # Explicitly set time-in-force to avoid order preset cancellations
        try:
            order.tif = 'GTC'
        except Exception:
            # Some versions may expect different attribute; ignore if not supported
            pass

        trade = ib.placeOrder(contract, order)

        # Wait until order is filled/cancelled or until timeout
        status = trade.orderStatus.status
        max_wait_s = 30
        waited = 0.0
        while status not in ('Filled', 'Cancelled') and waited < max_wait_s:
            ib.sleep(0.5)
            waited += 0.5
            status = trade.orderStatus.status

        if status not in ('Filled', 'Cancelled'):
            # Try to cancel the order if it didn't complete in time
            try:
                ib.cancelOrder(trade.order)
                # give a short moment for cancel to propagate
                ib.sleep(0.5)
                status = trade.orderStatus.status
            except Exception:
                pass

        # Refresh status after possible cancel
        status = trade.orderStatus.status
        # Try to extract a human-readable reason from trade logs for cancelled orders
        reason = ''
        try:
            messages = [entry.message for entry in getattr(trade, 'log', []) if getattr(entry, 'message', '')]
            if messages:
                reason = ' | '.join(messages)
        except Exception:
            reason = ''

        if reason:
            print(f"STATUS: {status} | reason: {reason}", flush=True)
        else:
            print(f"STATUS: {status}", flush=True)

        return 0

    except Exception as e:
        # Print error details to stderr for debugging, but provide machine-friendly STATUS too
        try:
            sys.stderr.write(str(e) + "\n")
            sys.stderr.flush()
        except Exception:
            pass
        print(f"STATUS: ERROR | reason: {e}", flush=True)
        return 2

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print('Usage: broker_worker.py SYMBOL SIDE QTY')
        sys.exit(2)
    sym, side, qty = sys.argv[1], sys.argv[2], int(sys.argv[3])
    code = main(sym, side, qty)
    sys.exit(code)
