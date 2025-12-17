import pytest
from ib_insync import IB

def test_ibkr_connection():
    ib = IB()
    try:
        ib.connect(
            host="127.0.0.1",
            port=7497,       # TWS paper trading
            clientId=99,
            timeout=3
        )
    except Exception as e:
        pytest.skip(f"IBKR TWS not available: {e}")

    try:
        if ib.isConnected():
            print("✅ Connected to IBKR TWS (Paper)")
            print("Account:", ib.managedAccounts())
        else:
            pytest.skip("IBKR TWS not connected")
    finally:
        ib.disconnect()

if __name__ == "__main__":
    test_ibkr_connection()