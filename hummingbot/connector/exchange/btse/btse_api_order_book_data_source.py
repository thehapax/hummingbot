#!/usr/bin/env python
import asyncio
import logging
import time
import aiohttp
import pandas as pd
import hummingbot.connector.exchange.btse.btse_constants as constants

from typing import Optional, List, Dict, Any
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.logger import HummingbotLogger
from . import btse_utils
from .btse_active_order_tracker import BtseActiveOrderTracker
from .btse_order_book import BtseOrderBook
from .btse_websocket import BtseWebsocket
from .btse_utils import ms_timestamp_to_s

import ujson


class BtseAPIOrderBookDataSource(OrderBookTrackerDataSource):
    MAX_RETRIES = 20
    MESSAGE_TIMEOUT = 30.0
    SNAPSHOT_TIMEOUT = 10.0

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, trading_pairs: List[str] = None):
        super().__init__(trading_pairs)
        self._trading_pairs: List[str] = trading_pairs
        self._snapshot_msg: Dict[str, any] = {}

    @classmethod
    async def get_last_traded_prices(cls, trading_pairs: List[str]) -> Dict[str, float]:
        tasks = [cls.get_last_traded_price(t_pair) for t_pair in trading_pairs]
        results = await safe_gather(*tasks)
        return {t_pair: result for t_pair, result in zip(trading_pairs, results)}

    @classmethod
    async def get_last_traded_price(cls, trading_pair: str) -> float:
        async with aiohttp.ClientSession() as client:
            price = -1
            resp = await client.get(f"{constants.REST_URL}price",
                                    params={'symbol': trading_pair})
            resp_json = await resp.json()
            if resp_json[0]["symbol"] == trading_pair:
                price = float(resp_json[0]["lastPrice"])
            return price

    @staticmethod
    async def get_order_book_data(trading_pair: str) -> Dict[str, any]:
        """
        Get whole orderbook
        """
        print(f"API : [{trading_pair}] inside get_order_book_data in btse_api_order_book_data_source")
        params = {'symbol': trading_pair}

        async with aiohttp.ClientSession() as client:
            orderbook_response = await client.get(
                f"{constants.REST_URL}orderbook/L2",
                params=params
            )
            if orderbook_response.status != 200:
                raise IOError(
                    f"Error fetching OrderBook for {trading_pair} at {constants.EXCHANGE_NAME}. "
                    f"HTTP status is {orderbook_response.status}."
                )
            orderbook_data: Dict[str, Any] = await safe_gather(orderbook_response.json())
            data: Dict[str, Any] = btse_utils.reshape(orderbook_data[0])
        return data

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        # print("\nAPI: >>>> GET NEW ORDER BOOK  - inside get_new_order_book in btse_api_order_book_data_source")
        snapshot: Dict[str, Any] = await self.get_order_book_data(trading_pair)
        # snapshot_timestamp: int = ms_timestamp_to_s(snapshot["timestamp"])
        snapshot_timestamp: float = time.time()  # why would be using local time instead of snapshot time?
        snapshot_msg: OrderBookMessage = BtseOrderBook.snapshot_message_from_exchange(
            snapshot,
            snapshot_timestamp,
            metadata={"trading_pair": trading_pair}
        )
        order_book = self.order_book_create_function()
        active_order_tracker: BtseActiveOrderTracker = BtseActiveOrderTracker()
        bids, asks = active_order_tracker.convert_snapshot_message_to_order_book_row(snapshot_msg)
        order_book.apply_snapshot(bids, asks, snapshot_msg.update_id)
        return order_book

    async def listen_for_trades(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        """
        Listen for trades using websocket trade channel
        """
        while True:
            try:
                ws = BtseWebsocket(auth=None)
                await ws.connect()
                await ws.subscribe(list(map(
                    lambda pair: f"tradeHistoryApi:{pair}",
                    self._trading_pairs
                )))
                async for response in ws.on_message():
                    # print(f'>>>>> LISTEN FOR TRADES response: {str(response)}')
                    res = ujson.loads(str(response))
                    if res.get("data") is None:
                        continue

                    for trade in res["data"]:
                        trade: Dict[Any] = trade
                        print(f'\n LISTEN FOR TRADE DATA : {trade}')
                        # ---> TODO : Reshape the trade object into correct format.
                        trade_timestamp: int = ms_timestamp_to_s(trade["timestamp"])
                        trade_msg: OrderBookMessage = BtseOrderBook.trade_message_from_exchange(
                            trade,
                            trade_timestamp,
                            metadata={"trading_pair": trade["symbol"]}
                        )
                        output.put_nowait(trade_msg)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error.", exc_info=True)
                await asyncio.sleep(5.0)
            finally:
                await ws.disconnect()

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        """
        Listen for orderbook diffs using websocket book channel
        """
        while True:
            try:
                ws = BtseWebsocket(auth=None)
                await ws.connect()
                await ws.subscribe(list(map(
                    lambda pair: f"orderBookL2Api:{pair}_150",
                    self._trading_pairs
                )))
                async for response in ws.on_message():
                    response = ujson.loads(str(response))
                    if response.get('data') is None:
                        continue

                    # print("\n API: Data Response from listen_for_order_book_diffs is not None ")
                    order_book_data = btse_utils.reshape(response['data'])
                    # order_book_data = response['data']
                    timestamp: int = ms_timestamp_to_s(response['data']['timestamp'])
                    # print(f"API - OB Diffs timestamp {timestamp} \n\n")
                    # data in this channel is not order book diff but the entire order book (up to depth 150).
                    # so we need to convert it into a order book snapshot.
                    # Btse does not offer order book diff ws updates.
                    orderbook_msg: OrderBookMessage = BtseOrderBook.diff_message_from_exchange(
                        order_book_data,
                        timestamp, metadata={"trading_pair": btse_utils.get_symbol_from_topic(response["topic"])}
                    )
                    # orderbook_msg: OrderBookMessage = BtseOrderBook.snapshot_message_from_exchange(
                    #    order_book_data,
                    #    timestamp,
                    #    metadata={"trading_pair": btse_utils.get_symbol_from_topic(response["topic"])}
                    # )
                    output.put_nowait(orderbook_msg)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unexpected error with WebSocket connection.",
                    exc_info=True,
                    app_warning_msg="Unexpected error with WebSocket connection. Retrying in 30 seconds. "
                                    "Check network connection."
                )
                await asyncio.sleep(30.0)
            finally:
                await ws.disconnect()

    # timestamp from btse is same format as crypto_com which is 13 digits, kraken is 10
    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.BaseEventLoop, output: asyncio.Queue):
        """
        Listen for orderbook snapshots by fetching orderbook
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    try:
                        snapshot: Dict[str, any] = await self.get_order_book_data(trading_pair)
                        snapshot_timestamp: int = ms_timestamp_to_s(snapshot["timestamp"])
                        snapshot_msg: OrderBookMessage = BtseOrderBook.snapshot_message_from_exchange(
                            snapshot,
                            snapshot_timestamp,
                            metadata={"trading_pair": trading_pair}
                        )
                        print("\n API: Response from listen_for_ob snapshots in btse_api_ob_datasource: ")
                        # print(snapshot)
                        output.put_nowait(snapshot_msg)
                        self.logger().debug(f"Saved order book snapshot for {trading_pair}")
                        # Be careful not to go above API rate limits.
                        await asyncio.sleep(5.0)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.logger().network(
                            "Unexpected error with WebSocket connection.",
                            exc_info=True,
                            app_warning_msg="Unexpected error with WebSocket connection. Retrying in 5 seconds. "
                                            "Check network connection."
                        )
                        await asyncio.sleep(5.0)
                this_hour: pd.Timestamp = pd.Timestamp.utcnow().replace(minute=0, second=0, microsecond=0)
                next_hour: pd.Timestamp = this_hour + pd.Timedelta(hours=1)
                delta: float = next_hour.timestamp() - time.time()
                await asyncio.sleep(delta)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error.", exc_info=True)
                await asyncio.sleep(5.0)
