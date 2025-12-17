import requests

POST_URL = 'http://127.0.0.1:8000/webhook/tradingview'
API_PNL = 'http://127.0.0.1:8000/dashboard/api/pnl'
WS_STATUS = 'http://127.0.0.1:8000/dashboard/api/ws_status'

PAYLOAD = {'symbol':'E2E_UI','side':'BUY','qty':1,'price':9.87}

print('WS status before:', requests.get(WS_STATUS).json())
res = requests.post(POST_URL, json=PAYLOAD)
print('POST returned:', res.status_code, res.text)
print('API PNL now:', requests.get(API_PNL).json())
print('WS status after:', requests.get(WS_STATUS).json())
