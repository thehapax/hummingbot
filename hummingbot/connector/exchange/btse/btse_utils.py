# copied from crypto_com utils - TODO make sure remove unused methods
import math
from typing import Dict, List
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce, get_tracking_nonce_low_res
import hummingbot.connector.exchange.btse.btse_constants as Constants
import ujson


def get_base(symbol):
    pairs = symbol.split('-')
    return pairs[0]


def get_quote(symbol):
    pairs = symbol.split('-')
    return pairs[1]


def reshape(orderbook_data):
    newob = {}
    bids = []
    asks = []
    t = orderbook_data['timestamp']
    for i in orderbook_data['buyQuote']:
        bids.append(list(i.values()))
    for i in orderbook_data['sellQuote']:
        asks.append(list(i.values()))
    newob = {'bids': bids, 'asks': asks, 't': t}
    return newob


def get_auth_responses(response):
    lookup = {'UNLOGIN_USER connect success': 'Auth_Connect_No_Login',
              'connect success': 'Auth_Connected_Token',
              'is authenticated successfully': 'Auth_Success',
              'AUTHENTICATE ERROR': 'Auth_Failed'}

    if "topic" in str(response):
        return ujson.loads(response)

    for k, v in lookup.items():
        if k in response:
            rdict = {"topic": str(v), "message": str(response)}
            return rdict


def is_json(myjson):
    try:
        json_object = ujson.loads(myjson)
        if json_object:
            return True
    except ValueError:
        return False


# deeply merge two dictionaries
def merge_dicts(source: Dict, destination: Dict) -> Dict:
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge_dicts(value, node)
        else:
            destination[key] = value

    return destination


# join paths
def join_paths(*paths: List[str]) -> str:
    return "/".join(paths)


# get timestamp in milliseconds
def get_ms_timestamp() -> int:
    return get_tracking_nonce_low_res()


# convert milliseconds timestamp to seconds
def ms_timestamp_to_s(ms: int) -> int:
    return math.floor(ms / 1e3)


# Request ID class
class RequestId:
    """
    Generate request ids
    """
    _request_id: int = 0

    @classmethod
    def generate_request_id(cls) -> int:
        return get_tracking_nonce()


# example: 'orderBookApi:BTC-USD_5' to 'BTC-USD'
def get_symbol_from_topic(topic: str) -> str:
    return topic.split(':').pop().split('_')[0]


def get_new_client_order_id(is_buy: bool, trading_pair: str) -> str:
    side = "buy" if is_buy else "sell"
    return f"{side}-{trading_pair}-{get_tracking_nonce()}"


def get_api_reason(code: str) -> str:
    return Constants.API_REASONS.get(int(code), code)
