# IBKR FastAPI Trading Bot

Developer setup

1. Create and activate a virtual environment

- PowerShell (Windows):

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

2. Install runtime requirements

  ```powershell
  pip install -r requirements.txt
  ```

3. Install development/test requirements

  ```powershell
  pip install -r dev-requirements.txt
  ```

Running tests

- Run the test suite with:

```powershell
pytest -q
```

Notes

- If you plan to place real IBKR orders, install `ib_insync` and ensure TWS/Gateway is available. For testing, the test suite mocks `place_order_sync` so IBKR connectivity is not required.

Risk management

- The app includes a basic RiskManager with configurable settings available via environment variables or `app/config.py` defaults:
  - `MAX_ORDER_QTY` (default 100)
  - `MAX_ORDER_NOTIONAL` (default 50000)
  - `MAX_POSITION_PER_SYMBOL` (default 1000)
  - `MAX_TOTAL_EXPOSURE` (default 250000)
  - `MAX_DAILY_LOSS` (default 2000)

- Orders rejected by the RiskManager are saved in the `trades` table with `status` set to `risk_rejected: <reason>` so you can audit rejections.
- To tune risk parameters, set the environment variables (for example in `.env`) or edit `app/config.py`.

- In VS Code, select the project virtual environment as the Python interpreter so the language server resolves `fastapi`, `sqlalchemy`, and other packages.
