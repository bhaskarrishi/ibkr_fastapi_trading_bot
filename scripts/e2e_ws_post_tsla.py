import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from websocket import create_connection
import requests

WS_URL = 'ws://127.0.0.1:8000/dashboard/ws/trades'
POST_URL = 'http://127.0.0.1:8000/webhook/tradingview'

PAYLOAD = {'symbol': 'TSLA', 'side': 'BUY', 'qty': 1, 'price': 150.0}

print('Connecting to websocket:', WS_URL)
ws = create_connection(WS_URL, timeout=5)
print('Connected. Posting webhook payload via HTTP to', POST_URL)
res = requests.post(POST_URL, json=PAYLOAD)
print('POST returned:', res.status_code, res.text)
# collect a few messages
for i in range(5):
    try:
        msg = ws.recv()
        print('WS msg:', msg)
    except Exception as e:
        print('WS recv timeout or error:', e)
        break
ws.close()
print('Done')
