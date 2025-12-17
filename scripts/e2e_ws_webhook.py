import sys, os, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Ensure websocket-client is available
try:
    from websocket import create_connection
except Exception:
    print('websocket-client not installed; installing...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'websocket-client'])
    from websocket import create_connection

import requests

WS_URL = 'ws://127.0.0.1:8000/dashboard/ws/trades'
POST_URL = 'http://127.0.0.1:8000/webhook/tradingview'

PAYLOAD = {'symbol': 'E2E', 'side': 'BUY', 'qty': 1, 'price': 123.45}


def run_once():
    print('Connecting to websocket:', WS_URL)
    ws = create_connection(WS_URL, timeout=5)
    print('Connected. Posting webhook payload via HTTP to', POST_URL)
    r = requests.post(POST_URL, json=PAYLOAD)
    print('POST status:', r.status_code, 'body:', r.text)

    # attempt to receive up to 5 messages with small timeout
    for i in range(5):
        try:
            msg = ws.recv()
            print('WS msg:', msg)
        except Exception as e:
            print('WS recv timeout or error:', e)
            break

    try:
        ws.close()
    except:
        pass


if __name__ == '__main__':
    run_once()
