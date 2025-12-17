# app/services/broker.py
import logging
import subprocess
import sys
from pathlib import Path


def place_order_sync(symbol: str, side: str, qty: int) -> str:
    """Run the broker worker in a fresh process and return the order status.

    This avoids asyncio event-loop issues when running IBKR code from thread
    pools by isolating the IBKR interaction into a standalone process.
    """
    worker = Path(__file__).with_name('broker_worker.py')
    cmd = [sys.executable, str(worker), symbol, side, str(qty)]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        logging.exception("Failed to start broker worker process")
        raise

    stdout = res.stdout.strip()
    stderr = res.stderr.strip()

    if res.returncode != 0:
        logging.error("broker_worker failed", extra={'stdout': stdout, 'stderr': stderr})
        raise RuntimeError(f"broker error: {stdout or stderr}")

    # Expect worker to print a machine-friendly STATUS line
    if stdout.startswith("STATUS:"):
        parsed = stdout.split("STATUS:", 1)[1].strip()
        logging.info("broker_worker status: %s", parsed)
        return parsed

    # Fallback: return raw stdout
    logging.info("broker_worker stdout: %s", stdout)
    return stdout
