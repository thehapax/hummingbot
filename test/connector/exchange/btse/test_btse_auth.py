import asyncio
import unittest

import conf
from hummingbot.connector.exchange.btse.btse_auth import BtseAuth
from hummingbot.connector.exchange.btse.btse_websocket import BtseWebsocket
import requests
import ujson


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        api_key = conf.btse_api_key
        secret_key = conf.btse_secret_key
        print("BTSE api_key: " + str(api_key))
        print("BTSE secret_key: " + str(secret_key))
        cls.auth = BtseAuth(api_key, secret_key)
        cls.ws = BtseWebsocket(cls.auth)
        path = '/api/v3.2/user/wallet'
        cls.headers = cls.auth.get_headers(path, '')

    async def con_auth(self):
        await self.ws.connect()
        # BTSE API notificationAPi subscriptions has no ack
        await self.ws.subscribe(["notificationApi"])
        await self.ws.subscribe(["orderBookApi:BTC-USD_5"])

        async for response in self.ws.on_message():
            res = ujson.loads(response)
            print(f'response type in websocket message: {type(res)}, response: {res}')
            if (res.get("event") == 'login'):
                return res.get('success')

    def test_auth(self):
        print("inside test_auth")
        result: bool = self.ev_loop.run_until_complete(self.con_auth())
        assert result

    def test_headers(self):
        params = {'currency': 'BTC'}
        btse_test_url = 'https://testapi.btse.io/spot/api/v3.2/user/wallet'
        # params = {}
        r = requests.get(
            btse_test_url,
            params=params,
            headers=self.headers)
        response = r.json()
        print(response)
        assert response is not None
