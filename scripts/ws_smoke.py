import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.main import app
from fastapi.testclient import TestClient
import asyncio, json
from app.services.broadcaster import broadcaster


def run():
    print('Starting TestClient and connecting websocket')
    with TestClient(app) as client:
        with client.websocket_connect('/dashboard/ws/trades') as ws:
            loop = asyncio.get_event_loop()
            payload_trade = {'type':'new_trade', 'trade': {'id':999,'timestamp':'2025-12-16T00:00:00','symbol':'TEST','side':'BUY','qty':1,'price':100.0,'pnl':50.0,'status':'Filled'}}
            print('Broadcasting new_trade payload:', payload_trade)
            loop.run_until_complete(broadcaster.broadcast(payload_trade))
            msg = ws.receive_json()
            print('Received via WS:', json.dumps(msg))

            payload_pnl = {'type':'pnl_update', 'tickers':[{'symbol':'TEST','position':1,'realized':50.0,'unrealized':0.0,'cumulative':50.0,'last_price':100.0}], 'daily_realized':50.0}
            print('Broadcasting pnl_update payload:', payload_pnl)
            loop.run_until_complete(broadcaster.broadcast(payload_pnl))
            msg2 = ws.receive_json()
            print('Received via WS:', json.dumps(msg2))
    print('Done')


if __name__ == "__main__":
    run()
