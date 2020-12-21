#!/usr/bin/env python

import time
import asyncio
import logging
from typing import Optional, List, AsyncIterable, Any
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger
from .btse_auth import BtseAuth
from .btse_websocket import BtseWebsocket


class BtseAPIUserStreamDataSource(UserStreamTrackerDataSource):
    MAX_RETRIES = 20
    MESSAGE_TIMEOUT = 30.0

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, btse_auth: BtseAuth, trading_pairs: Optional[List[str]] = []):
        self._btse_auth: BtseAuth = btse_auth
        self._trading_pairs = trading_pairs
        self._current_listen_key = None
        self._listen_for_user_stream_task = None
        self._last_recv_time: float = 0
        super().__init__()

    @property
    def last_recv_time(self) -> float:
        return self._last_recv_time

    async def _listen_to_orders_trades_balances(self) -> AsyncIterable[Any]:
        """
        Subscribe to active orders via web socket
        """
        try:
            ws = BtseWebsocket(self._btse_auth)
            await ws.connect()
            await ws.subscribe(["notificationApiV1"])
            print("Websocket subscribe to notifications api, \n in _listen_to_orders_trades_balances in api_user_stream_data \n")
            if self.last_recv_time == 0:
                self._last_recv_time = time.time()
                print(f"setting initial time: {self._last_recv_time}")
                # initial time is zero, set to non-zero

            async for msg in ws.on_message():
                print(f'Data returned websocket message: {msg}')
                if 'notificationsApiV1' not in msg:
                    continue
                # print("API USER STREAM: inside _listen_to_orders_trades_balances in api_user_stream_data_source")
                print(f"WS_SOCKET: {msg}")
                yield msg
                self._last_recv_time = time.time()
        except Exception as e:
            raise e
        finally:
            await ws.disconnect()
            await asyncio.sleep(5)

    async def listen_for_user_stream(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue) -> AsyncIterable[Any]:
        """
        *required
        Subscribe to user stream via web socket, and keep the connection open for incoming messages
        :param ev_loop: ev_loop to execute this function in
        :param output: an async queue where the incoming messages are stored
        """

        while True:
            try:
                async for msg in self._listen_to_orders_trades_balances():
                    output.put_nowait(msg)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error with Btse WebSocket connection. " "Retrying after 30 seconds...", exc_info=True
                )
                await asyncio.sleep(30.0)
