#!/usr/bin/env python
import asyncio
import copy
import logging
import websockets
import ujson
import hummingbot.connector.exchange.btse.btse_constants as constants
from hummingbot.core.utils.async_utils import safe_ensure_future


from typing import Optional, AsyncIterable, Any, List
from websockets.exceptions import ConnectionClosed
from hummingbot.logger import HummingbotLogger
from hummingbot.connector.exchange.btse.btse_auth import BtseAuth
from hummingbot.connector.exchange.btse.btse_utils import RequestId
from hummingbot.connector.exchange.btse.btse_periodic_checker import BtsePeriodicChecker


class BtseWebsocket(RequestId):
    MESSAGE_TIMEOUT = 30.0
    PING_TIMEOUT = 10.0
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, auth: Optional[BtseAuth] = None):
        self._auth: Optional[BtseAuth] = auth
        self._isPrivate = True if self._auth is not None else False
        self._WS_URL = constants.WSS_PRIVATE_URL if self._isPrivate else constants.WSS_PUBLIC_URL
        self._client: Optional[websockets.WebSocketClientProtocol] = None
        self._ping_checker = BtsePeriodicChecker(period_ms = 8 * 1000)

    # connect to exchange
    async def connect(self):
        try:
            self._client = await websockets.connect(self._WS_URL)
            # if auth class was passed into websocket class
            # we need to emit authenticated requests
            if self._isPrivate:
                await self._emit('authKeyExpires', None)
                # TODO: wait for response
                await asyncio.sleep(1)

            return self._client
        except Exception as e:
            self.logger().error(f"Websocket error: '{str(e)}'", exc_info=True)

    # disconnect from exchange
    async def disconnect(self):
        if self._client is None:
            return

        await self._client.close()

    # receive & parse messages
    async def _messages(self) -> AsyncIterable[Any]:
        try:
            while True:
                try:
                    raw_msg_str: str = await asyncio.wait_for(self._client.recv(), timeout=self.MESSAGE_TIMEOUT)
                    # Heartbeat keep alive response
                    if self._ping_checker.check():
                        payload = {"op": "ping"}
                        print("==== BTSE Keep Alive HEART BEAT === sending a ping: " + str(payload))
                        safe_ensure_future(self._client.send(ujson.dumps(payload)))
                    yield raw_msg_str
                except asyncio.TimeoutError:
                    await asyncio.wait_for(self._client.ping(), timeout=self.PING_TIMEOUT)
        except asyncio.TimeoutError:
            self.logger().warning("WebSocket ping timed out. Going to reconnect...")
            return
        except ConnectionClosed:
            return
        finally:
            await self.disconnect()

    # emit messages
    async def _emit(self, op: str, data: Optional[Any] = {}) -> int:
        id = self.generate_request_id()
        payload = {
            "op": op,
            "args": copy.deepcopy(data),
        }
        if self._isPrivate and op == 'authKeyExpires':
            print("====== GENERATING PRIVATE WSS PAYLOAD for BTSE WEBSOCKET =====")
            auth = self._auth.generate_auth_dict(
                uri='/spotWS',
                data=data,
            )
            payload['op'] = 'authKeyExpires'
            payload['args'] = auth['args']

        await self._client.send(ujson.dumps(payload))
        print(f'btse_websocket _emit: {str(payload)}')
#        print(f'request id: {id}')
        return id

    # request via websocket
    async def request(self, op: str, data: Optional[Any] = {}) -> int:
        return await self._emit(op, data)

    # subscribe to an op
    async def subscribe(self, channels: List[str]) -> int:
        return await self.request("subscribe", channels)

    # unsubscribe to an op
    async def unsubscribe(self, channels: List[str]) -> int:
        return await self.request("unsubscribe", channels)

    # listen to messages by op
    async def on_message(self) -> AsyncIterable[Any]:
        async for msg in self._messages():
            yield msg
