#!/usr/bin/env python
import asyncio
import bisect
import logging
import hummingbot.connector.exchange.btse.btse_constants as constants
import time

from collections import defaultdict, deque
from typing import Optional, Dict, List, Deque
from hummingbot.core.data_type.order_book_message import OrderBookMessageType
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.order_book_tracker import OrderBookTracker
from hummingbot.connector.exchange.btse.btse_order_book_message import BtseOrderBookMessage
from hummingbot.connector.exchange.btse.btse_active_order_tracker import BtseActiveOrderTracker
from hummingbot.connector.exchange.btse.btse_api_order_book_data_source import BtseAPIOrderBookDataSource
from hummingbot.connector.exchange.btse.btse_order_book import BtseOrderBook


class BtseOrderBookTracker(OrderBookTracker):
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, trading_pairs: Optional[List[str]] = None,):
        super().__init__(BtseAPIOrderBookDataSource(trading_pairs), trading_pairs)

        self._ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        self._order_book_snapshot_stream: asyncio.Queue = asyncio.Queue()
        self._order_book_diff_stream: asyncio.Queue = asyncio.Queue()
        self._order_book_trade_stream: asyncio.Queue = asyncio.Queue()
        self._process_msg_deque_task: Optional[asyncio.Task] = None
        self._past_diffs_windows: Dict[str, Deque] = {}
        self._order_books: Dict[str, BtseOrderBook] = {}
        self._saved_message_queues: Dict[str, Deque[BtseOrderBookMessage]] = \
            defaultdict(lambda: deque(maxlen=1000))
        self._active_order_trackers: Dict[str, BtseActiveOrderTracker] = defaultdict(BtseActiveOrderTracker)
        self._order_book_stream_listener_task: Optional[asyncio.Task] = None
        self._order_book_trade_listener_task: Optional[asyncio.Task] = None

    @property
    def exchange_name(self) -> str:
        """
        Name of the current exchange
        """
        return constants.EXCHANGE_NAME

    async def _track_single_book(self, trading_pair: str):
        """
        Update an order book with changes from the latest batch of received messages
        """
        # print(f"\n==== OB: inside _TRACK_SINGLE_BOOK: {trading_pair} -- in btse_order_book_tracker ===== \n")

        past_diffs_window: Deque[BtseOrderBookMessage] = deque()
        self._past_diffs_windows[trading_pair] = past_diffs_window

        message_queue: asyncio.Queue = self._tracking_message_queues[trading_pair]
        order_book: BtseOrderBook = self._order_books[trading_pair]
        active_order_tracker: BtseActiveOrderTracker = self._active_order_trackers[trading_pair]

        last_message_timestamp: float = time.time()
        diff_messages_accepted: int = 0

        while True:
            try:
                message: BtseOrderBookMessage = None
                saved_messages: Deque[BtseOrderBookMessage] = self._saved_message_queues[trading_pair]
                # Process saved messages first if there are any
                if len(saved_messages) > 0:
                    message = saved_messages.popleft()
                else:
                    message = await message_queue.get()
                # print("====== OB: saved messages TRACK_SINGLE_BOOK in btse_order_book_tracker\n")
                # print(saved_messages)

                # print(message.type)
                if message.type is OrderBookMessageType.DIFF:
                    # print(">>>>>> OB: DIFF - TRACK inside message.type is OrderBookMessageType.DIFF  <<<<<<<")
                    bids, asks = active_order_tracker.convert_diff_message_to_order_book_row(message)
                    order_book.apply_diffs(bids, asks, message.update_id)
                    past_diffs_window.append(message)
                    while len(past_diffs_window) > self.PAST_DIFF_WINDOW_SIZE:
                        past_diffs_window.popleft()
                    diff_messages_accepted += 1

                    # Output some statistics periodically.
                    now: float = time.time()
                    if int(now / 60.0) > int(last_message_timestamp / 60.0):
                        # print(f"Processed {diff_messages_accepted} order book diffs for {trading_pair}")
                        self.logger().debug("Processed %d order book diffs for %s.",
                                            diff_messages_accepted, trading_pair)
                        diff_messages_accepted = 0
                    last_message_timestamp = now
                elif message.type is OrderBookMessageType.SNAPSHOT:
                    # print(">>>>>> OB: SNAPSHOT- TRACK inside message.type is OrderBookMessage.Type.SNAPSHOT  <<<<<<<")
                    past_diffs: List[BtseOrderBookMessage] = list(past_diffs_window)
                    # print(" OB: PAST DIFFS: ")
                    # print(past_diffs)
                    # only replay diffs later than snapshot, first update active order with snapshot then replay diffs
                    replay_position = bisect.bisect_right(past_diffs, message)
                    replay_diffs = past_diffs[replay_position:]
                    s_bids, s_asks = active_order_tracker.convert_snapshot_message_to_order_book_row(message)
                    # print("OB: s_bids, s_asks")
                    # print(s_bids)
                    # print("OB: message update id: " + str(message.update_id))
                    order_book.apply_snapshot(s_bids, s_asks, message.update_id)
                    for diff_message in replay_diffs:
                        # print("inside diff_message in REPLAY_DIFFS ==================>>>>>> ")
                        d_bids, d_asks = active_order_tracker.convert_diff_message_to_order_book_row(diff_message)
                        order_book.apply_diffs(d_bids, d_asks, diff_message.update_id)
                    # print(f">>>>>>>> OB: Processed order book snapshot for {trading_pair}")
                    self.logger().debug("Processed order book snapshot for %s.", trading_pair)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    f"Unexpected error processing order book messages for {trading_pair}.",
                    exc_info=True,
                    app_warning_msg="Unexpected error processing order book messages. Retrying after 5 seconds."
                )
                await asyncio.sleep(5.0)

    '''
    async def _order_book_diff_router(self):
        """
        Route the real-time order book diff messages to the correct order book.
        """
        print("======= OB: INSIDE _order_book_diff_router =========\n\n")
        last_message_timestamp: float = time.time()
        messages_queued: int = 0
        messages_accepted: int = 0
        messages_rejected: int = 0
        while True:
            try:
                order_book_message: BtseOrderBookMessage = await self._order_book_diff_stream.get()
                trading_pair: str = order_book_message.trading_pair
                print("\n\n ***** ============")
                print(f"OB - Diff Router BTSE OrderBookTracker: ==== > trading pair: {trading_pair}\n")
                print(order_book_message)
                #print("================\n\n")

                print("\n\n _tracking_message_queues \n")
                print(self._tracking_message_queues)

                if trading_pair not in self._tracking_message_queues:
                    print(">>>>>>>>>>>> NOT IN TRACKING MESSAGE QUEUES - ADD <<<<<<<<<<<<<<")
                    print("OB -- Saving messages queues - Diff Router")
                    messages_queued += 1
                    # Save diff messages received before snapshots are ready
                    # only this line different
                    self._saved_message_queues[trading_pair].append(order_book_message)
                    continue

                message_queue: asyncio.Queue = self._tracking_message_queues[trading_pair]
                # Check the order book's initial update ID. If it's larger, don't bother.
                order_book: BtseOrderBook = self._order_books[trading_pair]
                print("OB - order_book.snapshot_uid : " + str(order_book.snapshot_uid))
                print("OB - ob_message.update_id : "  + str(order_book_message.update_id))

                if order_book.snapshot_uid > order_book_message.update_id: # message should be greater than snapshot?
                    print("OB - snapshot_uid >  update_id \n\n")
                    messages_rejected += 1
                    continue

                print("OB  - PASS - no reject order_book_message, therefore add to _tracking_message_queues ")
                await message_queue.put(order_book_message)
                messages_accepted += 1

                # Log some statistics.
                now: float = time.time()
                if int(now / 60.0) > int(last_message_timestamp / 60.0):
                    print(f"Diff messages processed: {messages_accepted}, rejected: {messages_rejected}, queued: {messages_queued}")
                    self.logger().debug("Diff messages processed: %d, rejected: %d, queued: %d",
                                        messages_accepted,
                                        messages_rejected,
                                        messages_queued)
                    messages_accepted = 0
                    messages_rejected = 0
                    messages_queued = 0

                last_message_timestamp = now
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    f'{"Unexpected error routing order book messages."}',
                    exc_info=True,
                    app_warning_msg=f'{"Unexpected error routing order book messages. Retrying after 5 seconds."}'
                )
                await asyncio.sleep(5.0)
'''

    '''
    @property
    def data_source(self) -> OrderBookTrackerDataSource:
        if not self._data_source:
            self._data_source = BtseAPIOrderBookDataSource(trading_pairs=self._trading_pairs)
        return self._data_source
    '''
