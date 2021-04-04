#!/usr/bin/env python

import sys
import asyncio
# import logging
import unittest
import conf

from os.path import join, realpath
from hummingbot.connector.exchange.btse.btse_user_stream_tracker import BtseUserStreamTracker
from hummingbot.connector.exchange.btse.btse_auth import BtseAuth
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.connector.exchange.btse import btse_constants as Constants

import requests
import json


sys.path.insert(0, realpath(join(__file__, "../../../")))


class BtseUserStreamTrackerUnitTest(unittest.TestCase):
    api_key = conf.btse_api_key
    api_secret = conf.btse_secret_key

    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.btse_auth = BtseAuth(cls.api_key, cls.api_secret)
        cls.trading_pairs = ["BTC-USDT"]
        cls.user_stream_tracker: BtseUserStreamTracker = BtseUserStreamTracker(
            btse_auth=cls.btse_auth, trading_pairs=cls.trading_pairs)
        cls.user_stream_tracker_task: asyncio.Task = safe_ensure_future(cls.user_stream_tracker.start())

    def test_user_stream(self):
        # Wait process some msgs. this should only contain content if there is a user trade
        # otherwise no data will be sent.
        print("inside test_user_stream.... waiting 60 seconds...")
        self.ev_loop.run_until_complete(asyncio.sleep(10.0))

        limit_order_form = {
            "price": 37050,
            "side": "BUY",
            "size": 0.002,
            "symbol": "BTC-USDT",
            "time_in_force": "GTC",
            "triggerPrice": 0,
            "txType": "LIMIT",
            "type": "LIMIT",
            "clOrderID": "MYOWNORDERID2",
        }
        path = '/api/v3.2/order'
        r = requests.post(
            Constants.REST_URL + 'order',
            json=limit_order_form,
            headers=self.btse_auth.get_headers(path, json.dumps(limit_order_form))
        )
        print(r.text)

        self.ev_loop.run_until_complete(asyncio.sleep(5.0))
        print(self.user_stream_tracker.user_stream)

        print("last recv time")
        print(self.user_stream_tracker.last_recv_time)
