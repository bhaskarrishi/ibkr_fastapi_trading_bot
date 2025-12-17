from fastapi.testclient import TestClient
from app.main import app
import sqlite3

client = TestClient(app)
payload = {'symbol': 'TSLA', 'side': 'BUY', 'qty': 1, 'price': 300.0}
print('Posting webhook:', payload)
resp = client.post('/webhook/tradingview', json=payload)
print('HTTP:', resp.status_code, resp.text)

conn = sqlite3.connect('trades.db')
c = conn.cursor()
rows = c.execute('select id,symbol,side,qty,price,status,timestamp from trades order by id desc limit 5').fetchall()
print('DB rows:')
for r in rows:
    print(r)
conn.close()
