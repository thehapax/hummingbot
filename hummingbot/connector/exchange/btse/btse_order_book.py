#!/usr/bin/env python

import logging
import hummingbot.connector.exchange.btse.btse_constants as constants

from sqlalchemy.engine import RowProxy
from typing import (
    Optional,
    Dict,
    List, Any)
from hummingbot.logger import HummingbotLogger
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import (
    OrderBookMessage, OrderBookMessageType
)
from hummingbot.connector.exchange.btse.btse_order_book_message import BtseOrderBookMessage

_btob_logger = None


class BtseOrderBook(OrderBook):
    @classmethod
    def logger(cls) -> HummingbotLogger:
        global _btob_logger
        if _btob_logger is None:
            _btob_logger = logging.getLogger(__name__)
        return _btob_logger

    @classmethod
    def snapshot_message_from_exchange(cls,
                                       msg: Dict[str, any],
                                       timestamp: float,
                                       metadata: Optional[Dict] = None):
        """
        Convert json snapshot data into standard OrderBookMessage format
        :param msg: json snapshot data from live web socket stream
        :param timestamp: timestamp attached to incoming data
        :return: BtseOrderBookMessage
        """

        if metadata:
            msg.update(metadata)

        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=msg,
            timestamp=timestamp
        )

    @classmethod
    def snapshot_message_from_db(cls, record: RowProxy, metadata: Optional[Dict] = None):
        """
        *used for backtesting
        Convert a row of snapshot data into standard OrderBookMessage format
        :param record: a row of snapshot data from the database
        :return: BtseOrderBookMessage
        """
        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=record.json,
            timestamp=record.timestamp
        )

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None):
        """
        Convert json diff data into standard OrderBookMessage format
        :param msg: json diff data from live web socket stream
        :param timestamp: timestamp attached to incoming data
        :return: BtseOrderBookMessage
        """

        if metadata:
            msg.update(metadata)

        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content=msg,
            timestamp=timestamp
        )

    @classmethod
    def diff_message_from_db(cls, record: RowProxy, metadata: Optional[Dict] = None):
        """
        *used for backtesting
        Convert a row of diff data into standard OrderBookMessage format
        :param record: a row of diff data from the database
        :return: BtseOrderBookMessage
        """
        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content=record.json,
            timestamp=record.timestamp
        )

    @classmethod
    def trade_message_from_exchange(cls,
                                    msg: Dict[str, Any],
                                    timestamp: Optional[float] = None,
                                    metadata: Optional[Dict] = None):
        """
        Convert a trade data into standard OrderBookMessage format
        :param record: a trade data from the database
        :return: BtseOrderBookMessage
        """
        '''  if the trade data is public this is format - last 50 recent, plus updates
        {
            "topic": "tradeHistoryApi:BTC-USD",
            "data": [
            {
            "symbol": "BTC-USD",
            "side": "SELL",
            "size": 0.007,
            "price": 5302.8,
            "tradeId": 118974855,
            "timestamp": 1584446020295
            }]
        }
        '''

        if metadata:
            msg.update(metadata)

        # TODO check if valid for btse
        msg.update({
            "exchange_order_id": msg.get("tradeId"),
            "trade_type": msg.get("side"),
            "price": msg.get("price"),
            "amount": msg.get("size"),
        })

        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content=msg,
            timestamp=timestamp
        )

    @classmethod
    def trade_message_from_db(cls, record: RowProxy, metadata: Optional[Dict] = None):
        """
        *used for backtesting
        Convert a row of trade data into standard OrderBookMessage format
        :param record: a row of trade data from the database
        :return: BtseOrderBookMessage
        """
        return BtseOrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content=record.json,
            timestamp=record.timestamp
        )

    @classmethod
    def from_snapshot(cls, snapshot: OrderBookMessage):
        raise NotImplementedError(constants.EXCHANGE_NAME + " order book needs to retain individual order data.")

    @classmethod
    def restore_from_snapshot_and_diffs(self, snapshot: OrderBookMessage, diffs: List[OrderBookMessage]):
        raise NotImplementedError(constants.EXCHANGE_NAME + " order book needs to retain individual order data.")
