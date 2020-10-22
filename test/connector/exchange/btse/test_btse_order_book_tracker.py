#!/usr/bin/env python
from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../../../../")))
import math
import time
import asyncio
import logging
import unittest
from typing import Dict, Optional, List
from hummingbot.core.event.event_logger import EventLogger
from hummingbot.core.event.events import OrderBookEvent, OrderBookTradeEvent, TradeType
from hummingbot.connector.exchange.btse.btse_order_book_tracker import BtseOrderBookTracker
from hummingbot.connector.exchange.btse.btse_api_order_book_data_source import BtseAPIOrderBookDataSource
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.utils.async_utils import (
    safe_ensure_future,
)


class BtseOrderBookTrackerUnitTest(unittest.TestCase):
    order_book_tracker: Optional[BtseOrderBookTracker] = None
    events: List[OrderBookEvent] = [
        OrderBookEvent.TradeEvent
    ]
    trading_pairs: List[str] = [
        # "BTC-USDT",
        "ETH-USDT",
    ]

    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.order_book_tracker: BtseOrderBookTracker = BtseOrderBookTracker(trading_pairs=cls.trading_pairs)
        cls.order_book_tracker_task: asyncio.Task = safe_ensure_future(cls.order_book_tracker.start())
        cls.ev_loop.run_until_complete(cls.wait_til_tracker_ready())

    @classmethod
    async def wait_til_tracker_ready(cls):
        await cls.order_book_tracker._order_books_initialized.wait()

    async def run_parallel_async(self, *tasks, timeout=None):
        future: asyncio.Future = asyncio.ensure_future(asyncio.gather(*tasks))
        timer = 0
        while not future.done():
            if timeout and timer > timeout:
                raise Exception("Timeout running parallel async tasks in tests")
            timer += 1
            now = time.time()
            _next_iteration = now // 1.0 + 1  # noqa: F841
            await asyncio.sleep(1.0)
        return future.result()

    def run_parallel(self, *tasks):
        return self.ev_loop.run_until_complete(self.run_parallel_async(*tasks))

    def setUp(self):
        self.event_logger = EventLogger()
        for event_tag in self.events:
            for trading_pair, order_book in self.order_book_tracker.order_books.items():
                order_book.add_listener(event_tag, self.event_logger)

    def test_order_book_trade_event_emission(self):
        """
        Tests if the order book tracker is able to retrieve order book trade message from exchange and emit order book
        trade events after correctly parsing the trade messages
        """
        self.run_parallel(self.event_logger.wait_for(OrderBookTradeEvent))
        for ob_trade_event in self.event_logger.event_log:
            self.assertTrue(type(ob_trade_event) == OrderBookTradeEvent)
            self.assertTrue(ob_trade_event.trading_pair in self.trading_pairs)
            self.assertTrue(type(ob_trade_event.timestamp) in [float, int])
            self.assertTrue(type(ob_trade_event.amount) == float)
            self.assertTrue(type(ob_trade_event.price) == float)
            self.assertTrue(type(ob_trade_event.type) == TradeType)
            # datetime is in seconds
            self.assertTrue(math.ceil(math.log10(ob_trade_event.timestamp)) == 10)
            self.assertTrue(ob_trade_event.amount > 0)
            self.assertTrue(ob_trade_event.price > 0)

    def test_api_get_last_traded_prices(self):
        prices = self.ev_loop.run_until_complete(
            BtseAPIOrderBookDataSource.get_last_traded_prices(["BTC-USDT", "LTC-BTC"]))
        for key, value in prices.items():
            print(f"{key} last_trade_price: {value}")
        self.assertGreater(prices["BTC-USDT"], 1000)
        self.assertLess(prices["LTC-BTC"], 1)

    def test_tracker_integrity(self):
        print("==== TEST TODO - inside test_tracker_integrity")
        # Wait 5 seconds to process some diffs.
#        self.ev_loop.run_until_complete(asyncio.sleep(2.0))
        order_books: Dict[str, OrderBook] = self.order_book_tracker.order_books
        print(">>>> TEST_TRACKER_INTEGRITY")
        print(order_books)
        eth_usdt: OrderBook = order_books["ETH-USDT"]
        self.assertIsNot(eth_usdt.last_diff_uid, 0)
        self.assertGreaterEqual(eth_usdt.get_price_for_volume(True, 10).result_price,
                                eth_usdt.get_price(True))
        self.assertLessEqual(eth_usdt.get_price_for_volume(False, 10).result_price,
                             eth_usdt.get_price(False))


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
