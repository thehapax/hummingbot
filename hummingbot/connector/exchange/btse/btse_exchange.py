import logging
from typing import (
    Dict,
    List,
    Optional,
    Any,
    AsyncIterable,
)
from decimal import Decimal, getcontext
import asyncio
import json
import aiohttp
import math
import time
from async_timeout import timeout

from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.logger import HummingbotLogger
from hummingbot.core.clock import Clock
from hummingbot.core.utils.async_utils import safe_ensure_future, safe_gather
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.event.events import (
    MarketEvent,
    BuyOrderCompletedEvent,
    SellOrderCompletedEvent,
    OrderFilledEvent,
    OrderCancelledEvent,
    BuyOrderCreatedEvent,
    SellOrderCreatedEvent,
    MarketOrderFailureEvent,
    OrderType,
    TradeType,
    TradeFee
)
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.connector.exchange.btse.btse_order_book_tracker import BtseOrderBookTracker
from hummingbot.connector.exchange.btse.btse_user_stream_tracker import BtseUserStreamTracker
from hummingbot.connector.exchange.btse.btse_auth import BtseAuth
from hummingbot.connector.exchange.btse.btse_in_flight_order import BtseInFlightOrder
from hummingbot.connector.exchange.btse import btse_utils
from hummingbot.connector.exchange.btse import btse_constants as Constants
from hummingbot.core.utils.estimate_fee import estimate_fee
from hummingbot.connector.exchange.btse.btse_utils import get_status_msg

btsee_logger = None
s_decimal_NaN = Decimal("nan")
getcontext().prec = 10


class BtseExchange(ExchangeBase):
    """
    BtseExchange connects with BTSE.com exchange and provides order book pricing, user account tracking and
    trading functionality.
    """
    API_CALL_TIMEOUT = 10.0
    SHORT_POLL_INTERVAL = 2.0  # 5.0
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 1.0  # 10.0
    LONG_POLL_INTERVAL = 12.0  # 120.0

    MAKER_FEE_PERCENTAGE_DEFAULT = 0.0005
    TAKER_FEE_PERCENTAGE_DEFAULT = 0.001
    # 0.0500%/0.1000% is highest M/T
    # set some default values - need to update actual values

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global btsee_logger
        if btsee_logger is None:
            btsee_logger = logging.getLogger(__name__)
        return btsee_logger

    def __init__(self,
                 btse_api_key: str,
                 btse_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True
                 ):
        """
        :param btse_api_key: The API key to connect to private BTSE.com APIs.
        :param btse_api_secret: The API secret.
        :param trading_pairs: The market trading pairs which to track order book data.
        :param trading_required: Whether actual trading is needed.
        """
        super().__init__()
        self._trading_required = trading_required
        self._btse_auth = BtseAuth(btse_api_key, btse_api_secret)
        self._order_book_tracker = BtseOrderBookTracker(trading_pairs=trading_pairs)
        self._user_stream_tracker = BtseUserStreamTracker(self._btse_auth, trading_pairs)
        self._ev_loop = asyncio.get_event_loop()
        self._shared_client = None
        self._poll_notifier = asyncio.Event()
        self._last_timestamp = 0
        self._in_flight_orders = {}  # Dict[client_order_id:str, BtseInFlightOrder]
        self._order_not_found_records = {}  # Dict[client_order_id:str, count:int]
        self._trading_rules = {}  # Dict[trading_pair:str, TradingRule]
        self._status_polling_task = None
        self._user_stream_event_listener_task = None
        self._trading_rules_polling_task = None
        self._last_poll_timestamp = 0
        self._maker_fee_percentage = Decimal(self.MAKER_FEE_PERCENTAGE_DEFAULT)
        self._taker_fee_percentage = Decimal(self.TAKER_FEE_PERCENTAGE_DEFAULT)

    @property
    def name(self) -> str:
        return "btse"

    @property
    def order_books(self) -> Dict[str, OrderBook]:
        print("-- EX: inside property: order book tracker in BtseExchange")
        return self._order_book_tracker.order_books

    @property
    def trading_rules(self) -> Dict[str, TradingRule]:
        print("inside trading rules in BtseExchange")
        return self._trading_rules

    @property
    def in_flight_orders(self) -> Dict[str, BtseInFlightOrder]:
        print("get in flight orders in BtseExchange")
        return self._in_flight_orders

    @property
    def status_dict(self) -> Dict[str, bool]:
        """
        A dictionary of statuses of various connector's components.
        """
        return {
            "order_books_initialized": self._order_book_tracker.ready,
            "account_balance": len(self._account_balances) > 0 if self._trading_required else True,
            "trading_rule_initialized": len(self._trading_rules) > 0,
            "user_stream_initialized":
                self._user_stream_tracker.data_source.last_recv_time > 0 if self._trading_required else True,
        }

    # @property # delete this property when testing fixed
    # def obt_ready(self) -> bool:
    #    get orderbook initialized status
    #    return self._order_book_tracker._order_books_initialized.is_set()

    @property
    def ready(self) -> bool:
        """
        :return True when all statuses pass, this might take 5-10 seconds for all the connector's components and
        services to be ready.
        """
        return all(self.status_dict.values())

    @property
    def limit_orders(self) -> List[LimitOrder]:
        return [
            in_flight_order.to_limit_order()
            for in_flight_order in self._in_flight_orders.values()
        ]

    @property
    def tracking_states(self) -> Dict[str, any]:
        """
        :return active in-flight orders in json format, is used to save in sqlite db.
        """
        return {
            key: value.to_json()
            for key, value in self._in_flight_orders.items()
            if not value.is_done
        }

    def restore_tracking_states(self, saved_states: Dict[str, any]):
        """
        Restore in-flight orders from saved tracking states, this is st the connector can pick up on where it left off
        when it disconnects.
        :param saved_states: The saved tracking_states.
        """
        self._in_flight_orders.update({
            key: BtseInFlightOrder.from_json(value)
            for key, value in saved_states.items()
        })

    def supported_order_types(self) -> List[OrderType]:
        """
        :return a list of OrderType supported by this connector.
        Note that Market order type is no longer required and will not be used.
        """
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER]

    def start(self, clock: Clock, timestamp: float):
        """
        This function is called automatically by the clock.
        """
        super().start(clock, timestamp)

    def stop(self, clock: Clock):
        """
        This function is called automatically by the clock.
        """
        super().stop(clock)

    async def start_network(self):
        """
        This function is required by NetworkIterator base class and is called automatically.
        It starts tracking order book, polling trading rules,
        updating statuses and tracking user data.
        """
        self._order_book_tracker.start()
        # need to wait for this to come back
        # check orderbook status if started - ready state
        print(" -- EX: post order_book_tracker.start")

        self._trading_rules_polling_task = safe_ensure_future(self._trading_rules_polling_loop())
        if self._trading_required:
            print("_trading_required in btse_exchange")
            self._status_polling_task = safe_ensure_future(self._status_polling_loop())
            self._user_stream_tracker_task = safe_ensure_future(self._user_stream_tracker.start())
            self._user_stream_event_listener_task = safe_ensure_future(self._user_stream_event_listener())

    async def stop_network(self):
        """
        This function is required by NetworkIterator base class and is called automatically.
        """
        self._order_book_tracker.stop()
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._trading_rules_polling_task is not None:
            self._trading_rules_polling_task.cancel()
            self._trading_rules_polling_task = None
        if self._status_polling_task is not None:
            self._status_polling_task.cancel()
            self._status_polling_task = None
        if self._user_stream_tracker_task is not None:
            self._user_stream_tracker_task.cancel()
            self._user_stream_tracker_task = None
        if self._user_stream_event_listener_task is not None:
            self._user_stream_event_listener_task.cancel()
            self._user_stream_event_listener_task = None

    async def check_network(self) -> NetworkStatus:
        """
        This function is required by NetworkIterator base class and is called periodically to check
        the network connection. Simply ping the network (or call any light weight public API).
        """
        try:
            print("-- EX inside check network")
            await safe_gather(
                self._update_balances(),
                self._update_order_status(),)
            # rest api check only, should be websocket eventually
            # this puts a load on the network, but we don't have another fast option atm.
        except asyncio.CancelledError:
            raise
        except Exception:
            return NetworkStatus.NOT_CONNECTED
        return NetworkStatus.CONNECTED

    async def _http_client(self) -> aiohttp.ClientSession:
        """
        :returns Shared client session instance
        """
        if self._shared_client is None:
            self._shared_client = aiohttp.ClientSession()
        return self._shared_client

    async def _trading_rules_polling_loop(self):
        """
        Periodically update trading rule.
        """
        while True:
            try:
                await self._update_trading_rules()
                await asyncio.sleep(120)  # originally 60
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f'EXCEPTION TRADING RULES {e} \n\n')
                self.logger().network(f"Unexpected error while fetching trading rules. Error: {str(e)}",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch new trading rules from BTSE.com. "
                                                      "Check network connection.")
                await asyncio.sleep(0.5)

    # check - replace public/get-instruments
    async def _update_trading_rules(self):
        print("inside _update_trading_rules in BtseExchange")
        # params={'symbol':'BTC-USDT'} ######  temporary for testing, can delete anytime
        # get all markets
        params = {}
        market_info = await self._api_request(method="get",
                                              path="market_summary",
                                              params=params,
                                              is_auth_required=False)
        # print(market_info)
        self._trading_rules.clear()
        self._trading_rules = self._format_trading_rules(market_info)

    # check - update trading rules for btse.com
    def _format_trading_rules(self, markets_info: Dict[str, Any]) -> Dict[str, TradingRule]:
        """
        Converts json API response into a dictionary of trading rules.
        For BTSE, don't convert floats to decimal, to preserve format of float
        :param markets_info: The json API response
        :return A dictionary of trading rules.
        """
        result = {}
        for rule in markets_info:
            try:
                trading_pair = rule["symbol"]
                price_step = rule['minPriceIncrement']
                quantity_step = rule['minSizeIncrement']
                minordersize = rule['minOrderSize']
                maxordersize = rule['maxOrderSize']
                minvalidprice = rule['minValidPrice']

                result[trading_pair] = TradingRule(trading_pair,
                                                   min_price_increment=price_step,
                                                   min_base_amount_increment=quantity_step,
                                                   min_quote_amount_increment=quantity_step,
                                                   min_order_size=minordersize,
                                                   max_order_size=maxordersize,
                                                   min_order_value=minvalidprice)
            except Exception as e:
                print(f'trading rules EXCEPTION: {e}')
                self.logger().error(f"Error parsing the trading pair rule {rule}. Skipping.", exc_info=True)
        return result

    async def _api_request(self,
                           method: str,
                           path: str,
                           params: Dict[str, Any] = {},
                           is_auth_required: bool = False) -> Dict[str, Any]:
        """
        Sends an aiohttp request and waits for a response.
        :param method: The HTTP method, e.g. get or post
        :param path_url: The path url or the API end point
        :param is_auth_required: Whether an authentication is required, when True the function will add encrypted
        signature to the request.
        :returns A response in json format.
        """
        prefix = '/api/v3.2/'
        path_url = prefix + path
        url = f"{Constants.REST_URL}{path}"

        print(f'_api_request URL {url}')
        headers = {'Accept': 'application/json;charset=UTF-8'}

        if is_auth_required:
            print("auth required")
            headers = self._btse_auth.get_headers(path_url, '')
            # does it really work?
            #  headers=make_headers(path_url, '')
        print("inside_api_request -- \n")
        # print(f"inside _api_request FULL URL : {url} : path_url: {path_url} \n\t param =  {params} headers = {headers} ")
        # get default set of headers
        client = await self._http_client()
        try:
            if method == "get":
                async with client.request('get', url=url, params=params, headers=headers) as response:
                    # print(f"\n INSIDE CLIENT.GET: url: {url} params: {params} header: {headers}\n")
                    result = await response.text()
                    # print(f"\n GET response: {result}")

            elif method == "post":
                jsond = json.dumps(params)
                headers = self._btse_auth.get_headers(path_url, jsond)
                # print(f"\n INSIDE CLIENT.POST: url: {url}, json: {params}, headers: {headers}\n")
                async with client.request('post', url=url, json=params, headers=headers) as response:
                    result = await response.text()
                    print(f"\n POST response: {result}")

            elif method == "delete":
                headers = self._btse_auth.get_headers(path_url, '')
                # print(f"\n INSIDE DELETE order. {url}, params: {params}, headers: {headers}\n")
                async with client.request('delete', url=url, params=params, headers=headers) as response:
                    result = await response.text()
                    print(f"\n DELETE response: {result}")
            else:
                raise NotImplementedError

            parsed_response = json.loads(result)

        except Exception as e:
            print(f'Exception in _api_request : {e}')
            raise IOError(f"Error parsing data from {url}. Error: {str(e)}")
        if response.status != 200:
            print("Exception in _api_request response status !=200 ")
            raise IOError(f"Error fetching data from {url}. HTTP status is {response.status}. "
                          f"Message: {parsed_response}")
        print(f"REQUEST: {method} {path_url} {params}")
        # print(f"RESPONSE: {parsed_response}")
        return parsed_response

    def get_order_price_quantum(self, trading_pair: str, price: Decimal):
        """
        Returns a price step, a minimum price increment for a given trading pair.
        """
        trading_rule = self._trading_rules[trading_pair]
        # print(f'\n >>>> TRADING RULES : {trading_rule}')
        minpriceinc = trading_rule.min_price_increment
        minvalidprice = trading_rule.min_order_value
        print(f'\nget_order_price_quantum: {trading_pair}, price: {price},' +
              f'minpriceinc: {minpriceinc}, minvalidprice: {minvalidprice}')
        price_quantized = btse_utils.adjust_increment(price, minpriceinc)

        if price_quantized < minvalidprice:
            price_quantized = minvalidprice
        print(f'>> get_order_price_quantum - Quantized Price : {price_quantized}')
        return price_quantized

    def get_order_size_quantum(self, trading_pair: str, order_size: Decimal):
        """
        Returns an order amount step, a minimum amount increment for a given trading pair.
        """
        trading_rule = self._trading_rules[trading_pair]
        minsize = trading_rule.min_order_size
        maxsize = trading_rule.max_order_size
        minsizeinc = trading_rule.min_base_amount_increment
        print(f"get_order_size_quantum trading rule: pair {trading_pair} " +
              f" price: {order_size}, minsize: {minsize}")
        print(f'\n\tmax: {maxsize}, minsizeinc: {minsizeinc}\n')
        size_quantized = btse_utils.bounded_size(order_size, minsize, maxsize, minsizeinc)
        return size_quantized

    def get_order_book(self, trading_pair: str) -> OrderBook:
        print("-- EX inside get_order_book")
        if trading_pair not in self._order_book_tracker.order_books:
            raise ValueError(f"No order book exists for '{trading_pair}'.")
        return self._order_book_tracker.order_books[trading_pair]

    def buy(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
            price: Decimal = s_decimal_NaN, **kwargs) -> str:
        """
        Buys an amount of base asset (of the given trading pair). This function returns immediately.
        To see an actual order, you'll have to wait for BuyOrderCreatedEvent.
        :param trading_pair: The market (e.g. BTC-USDT) to buy from
        :param amount: The amount in base token value
        :param order_type: The order type
        :param price: The price (note: this is no longer optional)
        :returns A new internal order id
        """
        order_id: str = btse_utils.get_new_client_order_id(True, trading_pair)
        print(f"placing BUY order id: {order_id}, {trading_pair}, {str(amount)}, {order_type}, {str(price)}\n")
        safe_ensure_future(self._create_order(TradeType.BUY, order_id, trading_pair, amount, order_type, price))
        return order_id

    def sell(self, trading_pair: str, amount: Decimal, order_type=OrderType.MARKET,
             price: Decimal = s_decimal_NaN, **kwargs) -> str:
        """
        Sells an amount of base asset (of the given trading pair). This function returns immediately.
        To see an actual order, you'll have to wait for SellOrderCreatedEvent.
        :param trading_pair: The market (e.g. BTC-USDT) to sell from
        :param amount: The amount in base token value
        :param order_type: The order type
        :param price: The price (note: this is no longer optional)
        :returns A new internal order id
        """
        order_id: str = btse_utils.get_new_client_order_id(False, trading_pair)
        safe_ensure_future(self._create_order(TradeType.SELL, order_id, trading_pair, amount, order_type, price))
        print(f"placing SELL order id: {order_id}, {trading_pair}, {str(amount)}, {order_type}, {str(price)}\n\n")
        return order_id

    def cancel(self, trading_pair: str, order_id: str):
        """
        Cancel an order. This function returns immediately.
        To get the cancellation result, you'll have to wait for OrderCancelledEvent.
        :param trading_pair: The market (e.g. BTC-USDT) of the order.
        :param order_id: The internal order id (also called client_order_id)
        """
        safe_ensure_future(self._execute_cancel(trading_pair, order_id, True))
        return order_id

    def quantize_order_amount(self, trading_pair: str, amount: Decimal) -> Decimal:
        """
        Applies trading rule to quantize order amount.
        """
        # round_amount = round(amount, 3)
        print("\n\t Inside Quantize Order SIZE/AMOUNT \n")
        quantize_amount = self.get_order_size_quantum(trading_pair, amount)
        print(f'BTSE quantize_order_amount OVERRIDE  : {quantize_amount}')
        return quantize_amount

    def quantize_order_price(self, trading_pair: str, price: Decimal) -> Decimal:
        """
        Applies trading rule to quantize order price.
        """
        print("\n\t Inside Quantize Order Price \n")
        quantize_price = self.get_order_price_quantum(trading_pair, price)
        print(f'BTSE quantize_order_price OVERRIDE  : {quantize_price}')
        return quantize_price

    # check for btse.com - using POST method from REST API to create orders
    async def _create_order(self,
                            trade_type: TradeType,
                            order_id: str,
                            trading_pair: str,
                            amount: Decimal,
                            order_type: OrderType,
                            price: Decimal):
        """
        Calls create-order API end point to place an order, starts tracking the order and triggers order created event.
        :param trade_type: BUY or SELL
        :param order_id: Internal order id (also called client_order_id)
        :param trading_pair: The market to place order
        :param amount: The order amount (in base token value)
        :param order_type: The order type
        :param price: The order price
        """
        '''
        Error code market order {"errorCode":400,"message":"BADREQUEST: Size and Price should not be mixed","status":400}
        '''
        print("____inside _create_order")
        if not order_type.is_limit_type():
            print(f"Unsupported order type: {order_type}")
            raise Exception(f"Unsupported order type: {order_type}")
        trading_rule = self._trading_rules[trading_pair]

        amount = self.quantize_order_amount(trading_pair, amount)
        price = self.quantize_order_price(trading_pair, price)

        print(f'\n\n RETURNED QUANTIZED amount: {amount}, price: {price}')

        if amount < trading_rule.min_order_size:
            print(f'Buy order {amount} is lower than the minimum order size')
            raise ValueError(f"Buy order amount {amount} is lower than the minimum order size "
                             f"{trading_rule.min_order_size}.")

        api_params = {"symbol": trading_pair,
                      "side": trade_type.name,
                      "type": "LIMIT",
                      "price": f"{price}",
                      "size": f"{amount}",
                      "triggerPrice": 0,
                      "time_in_force": "GTC",
                      "txType": "LIMIT",
                      "clOrderID": order_id,
                      }

        # if order_type is OrderType.LIMIT_MAKER:
        #    api_params["exec_inst"] = "POST_ONLY"
        print("api_params in create order: ")
        print(api_params)
        print("\n")
        try:
            order_result = await self._api_request(method="post",
                                                   path="order",
                                                   params=api_params,
                                                   is_auth_required=True)
            print(f"\n\nOrder Result: {order_result}\n\n")

            exchange_order_id = order_result[0]['orderID']
            tracked_order = self._in_flight_orders.get(order_id)
            print(f' ===== in flight orders pass1 ===== exchange_order_id {exchange_order_id} \n')
            v = self._in_flight_orders.values()
            print(v)

            print(f"\n\t Client order id: {order_id}")
            print(f"\n\t Exchange order id: {exchange_order_id}")

            if tracked_order is None:
                print("Tracked order cannot be found")

            if tracked_order is not None:
                self.logger().info(f"Created {order_type.name} {trade_type.name} order {order_id} for "
                                   f"{amount} {trading_pair}.")
                tracked_order.exchange_order_id = exchange_order_id

            event_tag = MarketEvent.BuyOrderCreated if trade_type is TradeType.BUY else MarketEvent.SellOrderCreated
            event_class = BuyOrderCreatedEvent if trade_type is TradeType.BUY else SellOrderCreatedEvent

            print(f' \n\n EVENT TAG: {event_tag}, \n EVENT CLASS: {event_class}\n')
            # only create a tracking order if successfully created via API

            self.start_tracking_order(order_id,
                                      exchange_order_id,
                                      trading_pair,
                                      trade_type,
                                      price,
                                      amount,
                                      order_type)

            self.trigger_event(event_tag,
                               event_class(
                                   self.current_timestamp,
                                   order_type,
                                   trading_pair,
                                   amount,
                                   price,
                                   order_id
                               ))

            print(' ===== in flight orders - post add ===== \n')
            v = self._in_flight_orders.values()
            print(v)
            print("\n\n")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Exception thrown {e}")

            self.stop_tracking_order(order_id)
            self.logger().network(
                f"Error submitting {trade_type.name} {order_type.name} order to BTSE.com for "
                f"{amount} {trading_pair} "
                f"{price}.",
                exc_info=True,
                app_warning_msg=str(e)
            )
            self.trigger_event(MarketEvent.OrderFailure,
                               MarketOrderFailureEvent(self.current_timestamp, order_id, order_type))

    def start_tracking_order(self,
                             order_id: str,
                             exchange_order_id: str,
                             trading_pair: str,
                             trade_type: TradeType,
                             price: Decimal,
                             amount: Decimal,
                             order_type: OrderType):
        """
        Starts tracking an order by simply adding it into _in_flight_orders dictionary.
        """
        self._in_flight_orders[order_id] = BtseInFlightOrder(
            client_order_id=order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=trading_pair,
            order_type=order_type,
            trade_type=trade_type,
            price=price,
            amount=amount
        )

    def stop_tracking_order(self, order_id: str):
        """
        Stops tracking an order by simply removing it from _in_flight_orders dictionary.
        """
        if order_id in self._in_flight_orders:
            del self._in_flight_orders[order_id]

    async def _execute_cancel(self, trading_pair: str, order_id: str, wait_for_status: bool = False) -> str:
        """
        Executes order cancellation process by first calling cancel-order API. The API result doesn't confirm whether
        the cancellation is successful, it simply states it receives the request.
        :param trading_pair: The market trading pair
        :param order_id: The internal order id
        :param wait_for_status: Whether to wait for the cancellation result, this is done by waiting for
        order.last_state to change to CANCELED
        """
        try:
            print(f"\n INSIDE CANCEL ORDER: trading_pair {trading_pair} order_id: {order_id}")

            tracked_order = self._in_flight_orders.get(order_id)
            print(f'\n Cancel tracked order: {tracked_order}, order_id: {order_id}\n')
            if tracked_order is None:
                raise ValueError(f"Failed to cancel order id: {order_id}. Order not found.")
            if tracked_order.exchange_order_id is None:
                await tracked_order.get_exchange_order_id()
            ex_order_id = tracked_order.exchange_order_id

            print(f'\n\n CANCELLED ex_order_id : {ex_order_id}')
            # ex_order_id - as option in _api_request 2/18/21
            result = await self._api_request(
                method="delete",
                path="order",
                params={"symbol": trading_pair, 'clOrderID': order_id},  # client order ID
                is_auth_required=True
            )
            print(f"\nCancel _api_request Response from BTSE: {result}")
            if type(result) == list:
                code = result[0]['status']
                msg = get_status_msg(code)
                print(f'\nCancel Order Status Message: {msg}, order_id : {order_id}')
                if msg == "ORDER_CANCELLED":
                    print("inside ORDER_CANCELLED in execute cancel")
                    if wait_for_status:
                        from hummingbot.core.utils.async_utils import wait_til
                        await wait_til(lambda: tracked_order.is_cancelled)
                    tracked_order = self._in_flight_orders[order_id]
                    print(f"tracked_order: {tracked_order}")
                    self.trigger_event(MarketEvent.OrderCancelled,
                                       OrderCancelledEvent(self.current_timestamp, order_id))
                    tracked_order.cancelled_event.set()
                    self.stop_tracking_order(order_id)
                    print(f"trigger_event - ORDER_CANCELLED: {order_id}.\n\n")
                    self.logger().info(f"Successfully cancelled order {order_id}.")
                    return order_id
            else:   # error dict returned, get actual error message and return
                msg = result['message']
                print(f'cancelled error: {msg}')
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f'Exception in Cancelling order: {e}')
            self.logger().network(
                f"Failed to cancel order {order_id}: {str(e)}",
                exc_info=True,
                app_warning_msg=f"Failed to cancel the order {order_id} on Btse. "
                                f"Check API key and network connection."
            )

    async def _status_polling_loop(self):
        """
        Periodically update user balances and order status via REST API.
        This usually serves as a fallback measure for web socket API updates.
        However, since BTSE does not have sufficient websocket data pushes, we poll here
        """
        while True:
            try:
                print("inside _status_polling_loop")
                self._poll_notifier = asyncio.Event()
                await self._poll_notifier.wait()
                await safe_gather(
                    self._update_balances(),  # done 10/8/20
                    self._update_order_status(),  # rest api trade history only
                )
                self._last_poll_timestamp = self.current_timestamp
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(str(e), exc_info=True)
                self.logger().network("Unexpected error while fetching account updates.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch account updates from BTSE.com. "
                                                      "Check API key and network connection.")
                await asyncio.sleep(0.5)

    async def _update_balances(self):
        """
        Calls REST API to update total and available balances.
        """
        print("inside _update_balances in btse_exchange")
        account_info = await self._api_request(method="get",
                                               path="user/wallet",
                                               params={},
                                               is_auth_required=True)
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()
        for account in account_info:
            asset_name = account["currency"]
            self._account_available_balances[asset_name] = Decimal(str(account["available"]))
            self._account_balances[asset_name] = Decimal(str(account["total"]))
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    async def _update_order_status(self):
        """
        Calls REST API to get status update for each in-flight order.
        """
        print("\n\n UPDATE ORDER STATUS -- inside _update_order_status in btse_exchange")
        last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL

        print(f'last_tick:{last_tick}, current tick: {current_tick}\n ')
        print(f'len inflight: {len(self.in_flight_orders)}')

        if len(self._in_flight_orders) > 0:
            tracked_orders = list(self._in_flight_orders.values())
            print(f'len of tracked orders: {len(self.in_flight_orders)}\n')
            tasks = []
            for tracked_order in tracked_orders:
                order_id = await tracked_order.get_exchange_order_id()
                tasks.append(self._api_request(method="get",
                                               path="user/open_orders",
                                               params={"orderID": order_id},
                                               is_auth_required=True))
            print(f'\n _update_order_status: Polling for order status of {len(tasks)} orders\n')
            self.logger().debug(f"Polling for order status updates of {len(tasks)} orders.")
            update_results = await safe_gather(*tasks, return_exceptions=True)
            print(f"\n\n _update_order_status: len of update_results : {len(update_results)} \n")

            for update_result in update_results:
                if isinstance(update_result, Exception):
                    raise update_result
                if not update_result:
                    self.logger().info(f"_update_order_status result not in resp: {update_result}")
                    print("\n No trades in update_order_status\n")
                    continue
                for trade_msg in update_result:
                    print(f"\n\n _process_trade_message in _update_order_status in btse_exchange: {trade_msg}\n")
                    await self._process_trade_message(trade_msg)

    async def _process_order_message(self, order_msg: Dict[str, Any]):
        """
        Updates in-flight order and triggers cancellation or failure event if needed.
        :param order_msg: The order response from web socket API (REST interim)
        (REST API not same format, only open orders)
        """
        print(f"\ninside _process_order_message in btse_exchange: {order_msg}\n")
        client_order_id = order_msg["clOrderID"]
        if client_order_id not in self._in_flight_orders:
            return
        tracked_order = self._in_flight_orders[client_order_id]
        print(f'tracked_order {tracked_order}\n')
        tracked_order.last_state = order_msg["status"]  # websocket or REST: order_msg['orderState']

        if tracked_order.is_cancelled:
            self.logger().info(f"Successfully cancelled order {client_order_id}.")
            print('\n\n >>>> inside tracked_order.is cancelled \n')
            self.trigger_event(MarketEvent.OrderCancelled,
                               OrderCancelledEvent(
                                   self.current_timestamp,
                                   client_order_id))
            tracked_order.cancelled_event.set()
            self.stop_tracking_order(client_order_id)
            print('\n\n TRIGGERED OrderCancelledEvent via MarketEvent')
        elif tracked_order.is_done:
            print('\n\n TRACKED ORDER IS DONE')
            self.logger().info(f"Successfully COMPLETED order {client_order_id}.")
            print(f'\n TradeType : {tracked_order.trade_type}')
            event_tag = MarketEvent.BuyOrderCompleted if tracked_order.trade_type is TradeType.BUY else MarketEvent.SellOrderCompleted
            event_class = BuyOrderCompletedEvent if tracked_order.trade_type is TradeType.BUY \
                else SellOrderCompletedEvent
            # Question: do OrderCompletedEvent data get written into a log somewhere?
            base_asset = btse_utils.get_base(tracked_order.trading_pair)
            quote_asset = btse_utils.get_quote(tracked_order.trading_pair)
            print(f'\n\n>>>>> BUY/SELLORDER COMPLETED EVENT size: {tracked_order.amount} price: {tracked_order.price}')
            print(f"base_asset: {base_asset}, quote_asset: {quote_asset}")
            print(f"fee_asset: {tracked_order.fee_asset}, fee_paid: {tracked_order.fee_paid}")
            print(f"order_msg size: {order_msg['size']}, amount: {order_msg['price']}")
            print(f'Order Type: {tracked_order.order_type}, order_id: {tracked_order.client_order_id}\n')
            self.trigger_event(event_tag,
                               event_class(self.current_timestamp,
                                           tracked_order.client_order_id,
                                           base_asset,
                                           quote_asset,
                                           tracked_order.fee_asset,
                                           Decimal(order_msg['size']) + Decimal(0),
                                           Decimal(order_msg['price'] * order_msg['size']) + Decimal(0),
                                           tracked_order.fee_paid,
                                           tracked_order.order_type))
            print('TRIGGERING ORDER FILLED EVENT')
            self.trigger_event(MarketEvent.OrderFilled,
                               OrderFilledEvent(
                                   self.current_timestamp,
                                   tracked_order.client_order_id,
                                   tracked_order.trading_pair,
                                   tracked_order.trade_type,
                                   tracked_order.order_type,
                                   Decimal(str(order_msg["price"])) + Decimal(0),
                                   Decimal(str(order_msg["size"])) + Decimal(0),
                                   tracked_order.fee_paid,
                                   exchange_trade_id=order_msg["orderID"]))

            self.stop_tracking_order(tracked_order.client_order_id)
        elif tracked_order.is_failure:
            print('\n\n tracker order is failure')
            self.logger().info(f"The market order {client_order_id} has failed according to order status API. "
                               f"Reason: {btse_utils.get_api_reason(order_msg['status'])}")
            self.trigger_event(MarketEvent.OrderFailure,
                               MarketOrderFailureEvent(
                                   self.current_timestamp,
                                   client_order_id,
                                   tracked_order.order_type
                               ))
            self.stop_tracking_order(client_order_id)
            print('\n\n end tracked order is failure')

    async def _process_trade_message(self, trade_msg: Dict[str, Any]):
        """
        Updates in-flight order and trigger order filled event for trade message received. Triggers order completed
        event if the total executed amount equals to the specified order amount.
        """
        print(f"\n inside process trade_message in btse_exchange: {trade_msg['orderID']}")
        orderID = trade_msg['orderID']
        track_order = [o for o in self._in_flight_orders.values() if trade_msg["orderID"] == o.client_order_id]
        print(f'\n>>>>> process_trade_msg - track_order: {track_order}')
        print(self.in_flight_orders)
        if not track_order:
            # print('TRADE ORDER CANNOT BE FOUND IN INFLIGHT ORDERS')
            return
        tracked_order = track_order[0]
        feeCurrency = 'BTC'  # temporary place holder
        feeAmount = 0.1  # temp place holder
        trade_history = await self._api_request(method="get",
                                                path="user/trade_history",
                                                params={"orderID": orderID},
                                                # "startTime": int(self._last_poll_timestamp)},
                                                is_auth_required=True)
        print(f"\n\n _process_trade_message: trade_history : {trade_history}\n\n")
        if len(trade_history) > 0:
            trade_hist = trade_history[0]
            feeCurrency = trade_hist['feeCurrency']
            feeAmount = trade_hist['feeAmount']
            print(f'\n\n TRADE_HISTORY feeCurrency {feeCurrency}, feeAmount {feeAmount}\n')
        # append feeCurrency, feeAmount to tracked_order
        tracked_order.fee_asset = feeCurrency
        tracked_order.fee_amount = feeAmount

        trade_msg["feeCurrency"] = feeCurrency
        trade_msg["feeAmount"] = feeAmount

        updated = tracked_order.update_with_trade_update(trade_msg)
        print(f'\n>>>> updated : {updated}')
        if not updated:
            return
        print("\n trigger event\n")
        # trigger orderfilled
        trade_fee = estimate_fee("btse", OrderType.LIMIT_MAKER)
        print(f'getting trade fee: {trade_fee} \n')
        print(f'ORDER FILLED Event size: {tracked_order.amount} price: {tracked_order.price}')
        print(f'trading pair: {tracked_order.trading_pair}, trading type: {tracked_order.trade_type}')
        print(f'fee_asset: {tracked_order.fee_asset}, fee_paid: {tracked_order.fee_paid}')
        print(f"trade_msg size: {trade_msg['size']}, amount: {trade_msg['price']}")
        print(f'order type: {tracked_order.order_type}, order_id: {tracked_order.client_order_id}\n')

        self.trigger_event(
            MarketEvent.OrderFilled,
            OrderFilledEvent(
                self.current_timestamp,
                tracked_order.client_order_id,
                tracked_order.trading_pair,
                tracked_order.trade_type,
                tracked_order.order_type,
                Decimal(str(trade_msg["price"])) + Decimal(0),
                Decimal(str(trade_msg["size"])) + Decimal(0),
                trade_fee,
                exchange_trade_id=trade_msg["orderID"]
            )
        )
        print("\n MarketEvent.OrderFilled Trigger event\n")
        print(f'\n >>> tracked_order.executed_amt base : {tracked_order.executed_amount_base}, amt: {tracked_order.amount}\n')
        print(f'\n tracked_order.fee_amount: {tracked_order.fee_amount} fee_currency: {tracked_order.fee_asset}\n')

        if math.isclose(tracked_order.executed_amount_base, tracked_order.amount) or \
                tracked_order.executed_amount_base >= tracked_order.amount:
            tracked_order.last_state = "ORDER_FULLY_TRANSACTED"
            print('\n ******   inside process_trade_message: ORDER FULLY TRANSACTED ')
            self.logger().info(f"The {tracked_order.trade_type.name} order "
                               f"{tracked_order.client_order_id} has completed "
                               f"according to order status API.")
            event_tag = MarketEvent.BuyOrderCompleted if tracked_order.trade_type is TradeType.BUY \
                else MarketEvent.SellOrderCompleted
            event_class = BuyOrderCompletedEvent if tracked_order.trade_type is TradeType.BUY \
                else SellOrderCompletedEvent

            base_asset = btse_utils.get_base(tracked_order.trading_pair)
            quote_asset = btse_utils.get_quote(tracked_order.trading_pair)

            print(f'Buy/SellOrderCompletedEvent size: {tracked_order.amount} price: {tracked_order.price}')
            print(f"base_asset: {base_asset}, quote_asset: {quote_asset}")
            print(f"fee_asset: {tracked_order.fee_asset}, fee_paid: {tracked_order.fee_paid}")
            print(f"order_msg size: {trade_msg['size']}, amount: {trade_msg['price']}")
            print(f'Order Type: {tracked_order.order_type}, order_id: {tracked_order.client_order_id}\n')

            self.trigger_event(event_tag,
                               event_class(self.current_timestamp,
                                           tracked_order.client_order_id,
                                           base_asset,
                                           quote_asset,
                                           tracked_order.fee_asset,
                                           Decimal(trade_msg['size']) + Decimal(0),
                                           Decimal(trade_msg['price'] * trade_msg['size']) + Decimal(0),
                                           tracked_order.fee_amount,
                                           tracked_order.order_type))
            self.stop_tracking_order(tracked_order.client_order_id)
            print(f'\n trigger event order completed event, and stop tracking order: {tracked_order}')

    async def cancel_all(self, timeout_seconds: float):
        """
        Cancels all in-flight orders and waits for cancellation results.
        Used by bot's top level stop and exit commands (cancelling outstanding orders on exit)
        :param timeout_seconds: The timeout at which the operation will be canceled.
        :returns List of CancellationResult which indicates whether each order is successfully cancelled.
        """
        print("\n ********* inside cancel_all in btse_exchange *********")
        incomplete_orders = [o for o in self._in_flight_orders.values() if not o.is_done]
        tasks = [self._execute_cancel(o.trading_pair, o.client_order_id, True) for o in incomplete_orders]
        order_id_set = set([o.client_order_id for o in incomplete_orders])
        successful_cancellations = []
        try:
            async with timeout(timeout_seconds):
                results = await safe_gather(*tasks, return_exceptions=True)
                for result in results:
                    if result is not None and not isinstance(result, Exception):
                        order_id_set.remove(result)
                        successful_cancellations.append(CancellationResult(result, True))
                        # self.trigger_event(MarketEvent.OrderCancelled,
                        #                   OrderCancelledEvent(self.current_timestamp,
                        #                                       order_id=result.order_id))
        except Exception:
            self.logger().error("Cancel all failed.", exc_info=True)
            self.logger().network(
                "Unexpected error cancelling orders.",
                exc_info=True,
                app_warning_msg="Failed to cancel order on BTSE.com. Check API key and network connection."
            )

        failed_cancellations = [CancellationResult(oid, False) for oid in order_id_set]
        print(f'\nSuccessful Cancellations : {successful_cancellations}')
        print(f'\nFailed Cancellations: {failed_cancellations}\n')
        return successful_cancellations + failed_cancellations

    def tick(self, timestamp: float):
        """
        Is called automatically by the clock for each clock's tick (1 second by default).
        It checks if status polling task is due for execution.
        """
        print(f"user stream tracker last recv time: {self._user_stream_tracker.last_recv_time}")
        now = time.time()
        poll_interval = (self.SHORT_POLL_INTERVAL
                         if now - self._user_stream_tracker.last_recv_time > 60.0
                         else self.LONG_POLL_INTERVAL)
        last_tick = self._last_timestamp / poll_interval
        current_tick = timestamp / poll_interval
        if current_tick > last_tick:
            if not self._poll_notifier.is_set():
                self._poll_notifier.set()
        self._last_timestamp = timestamp
        print(f'\n Tick : _last_timestamp: {self._last_timestamp},' +
              f'current_tick: {current_tick}, last_tick: {last_tick}\n')
        print(f'now {now}, poll_interval: {poll_interval}\n\n')

    def get_fee(self,
                base_currency: str,
                quote_currency: str,
                order_type: OrderType,
                order_side: TradeType,
                amount: Decimal,
                price: Decimal = s_decimal_NaN) -> TradeFee:
        """
        To get trading fee, this function is simplified by using fee override configuration. Most parameters to this
        function are ignored except order_type. Use OrderType.LIMIT_MAKER to specify you want trading fee for
        maker order.
        """
        is_maker = order_type is OrderType.LIMIT_MAKER
        return estimate_fee("btse", is_maker)

    async def _iter_user_event_queue(self) -> AsyncIterable[Dict[str, any]]:
        while True:
            try:
                yield await self._user_stream_tracker.user_stream.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().network(
                    "Unknown error. Retrying after 1 seconds.",
                    exc_info=True,
                    app_warning_msg="Could not fetch user events from Btse. Check API key and network connection."
                )
                await asyncio.sleep(1.0)

    async def _user_stream_event_listener(self):
        """
        Listens to message in _user_stream_tracker.user_stream queue. The messages are put in by
        BtseAPIUserStreamDataSource.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                trade_msg = event_message["data"]
                print(f"\n\n *** inside _USER_STREAM_EVENT_LISTENER in btse_exchange: {type(trade_msg)} \n")

                if type(trade_msg) == list:  # handle a list of dicts
                    for trade_msg in event_message["data"]:
                        print(f'\n TRADE MESSAGE is list: {trade_msg}\n')
                        # await self._process_trade_message(trade_msg) # don't use for now
                        await self._process_order_message(trade_msg)  # websocket ongoing order messages
                elif type(trade_msg) == dict:  # handle a single dict
                    print(f'\n TRADE MSG is dict: {trade_msg}\n')
                    await self._process_order_message(trade_msg)  # websocket ongoing order messages
                    # await self._process_trade_message(trade_msg) # don't use for now
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await asyncio.sleep(5.0)
