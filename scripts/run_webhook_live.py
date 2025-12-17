from fastapi.testclient import TestClient
from app.main import app
import sqlite3

payload = {"symbol": "AAPL", "side": "BUY", "qty": 1, "price": 150.0}

client = TestClient(app)
print('Sending webhook...')
resp = client.post('/webhook/tradingview', json=payload)
print('Response:', resp.status_code, resp.text)

print('\nChecking DB...')
conn = sqlite3.connect('trades.db')
c = conn.cursor()
c.execute('select id,symbol,side,qty,price,status,timestamp from trades order by id desc limit 1')
row = c.fetchone()
print('Latest trade row:', row)
conn.close()