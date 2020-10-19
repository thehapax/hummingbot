import asyncio
import unittest
from typing import List

import conf
from hummingbot.connector.exchange.btse.btse_auth import BtseAuth
from hummingbot.connector.exchange.btse.btse_websocket import BtseWebsocket


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

    async def con_auth(self):
        await self.ws.connect()
        # BTSE API notificationAPi subscriptions has no ack
        await self.ws.subscribe(["notificationApi"])
        await self.ws.subscribe(["orderBookApi:BTC-USD_5"])

        async for response in self.ws.on_message():
            print(type(response))
            if (response.get("topic") == 'Auth_Success'):
                return response

    def test_auth(self):
        print("inside test_auth")
        result: List[str] = self.ev_loop.run_until_complete(self.con_auth())
        assert "authenticated successfully" in result["message"]
