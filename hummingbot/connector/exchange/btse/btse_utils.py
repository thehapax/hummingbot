import math
from typing import Dict, List
from hummingbot.core.utils.tracking_nonce import get_tracking_nonce, get_tracking_nonce_low_res
import hummingbot.connector.exchange.btse.btse_constants as Constants
import ujson
import locale
from decimal import Decimal


# round down to the nearest multiple of a
def round_down(x, a):
    return math.floor(x / a) * a


# round up - to use with minimum order size
def round_up(x, a):
    return math.ceil(x / a) * a


# round to the nearest multiple of a
def round_nearest(x, a):
    return round(x / a) * a


# adjust price for order based on btse size/price increment restrictions.
def adjust_increment(price, minpriceinc):
    try:
        price = Decimal(price)
        print(f'>> adjust_increment, input price: {price}, minpriceinc: {minpriceinc}\n')
        print(f'Type of minpriceinc {type(minpriceinc)}, price: {type(price)}\n')

        if 'e' in str(minpriceinc):
            p = Decimal(locale.format_string("%f", minpriceinc))
        else:
            p = Decimal(str(minpriceinc))

        min_price_decimals = len(str(p).split(".")[1])
        minpriceinc = Decimal(minpriceinc)

        print(f'Inside Adjust_increment: min price inc: {minpriceinc},' +
              f' number of decimals allowed: {min_price_decimals}\n\n')

        deci = price - math.floor(price)
        if deci == 0:
            adjusted_price = price
            print(f'\n Deci - adjusted price is price: {price}')
            return adjusted_price

        remainder = deci % minpriceinc
        if remainder == 0.0:  # we are at no remainder so obeys step.
            adjusted_price = price
            print(f'remainder - adjusted price is price: {price}')
        else:
            near_price = round_nearest(price, minpriceinc)
            adjusted_price = round(near_price, min_price_decimals)
            print(f'round_nearest price: {near_price}, adj_price: {adjusted_price}')

        return adjusted_price
    except Exception as e:
        print(f'Exception thrown in adjust_increment: {e}')
        return e


# Calculate size for order within btse exchange bounds
def bounded_size(size, minsize, maxsize, minsizeinc):
    try:
        adjusted_size = size
        min_sizeinc = minsizeinc
        min_size = minsize

        if 'e' in str(minsizeinc):
            min_sizeinc = Decimal(locale.format_string("%f", minsizeinc))
        if 'e' in str(minsize):
            min_size = Decimal(locale.format_string("%f", minsize))

        minsizeinc_decimals = len(str(min_sizeinc).split(".")[1])
        # print(f'\n minsize_inc decimals: {minsizeinc_decimals}')
        # print(f'\n min_sizeinc: {min_sizeinc}, min_size: {min_size}\n')

        if size < maxsize and size > min_size:
            # print("adjusted size within bounds, ok")
            adjusted_size = size
        elif size <= min_size:
            # print("make minsize adjusted size")
            adjusted_size = min_size
        elif size >= maxsize:
            # print("make adjusted_size maxsize")
            adjusted_size = maxsize
            # print(f'\n>> post switch adjusted_size: {adjusted_size}')
            # min size decimals

        bounded_size = round_up(Decimal(adjusted_size), Decimal(min_sizeinc))
        print(f'>> Bounded Adjusted Size: {bounded_size}, minsize: {min_sizeinc}')
        bounded_size = round(bounded_size, minsizeinc_decimals)
        print(f'\n bounded size rounded off : {bounded_size}')

        return bounded_size
    except Exception as e:
        print(f'Exception in bounded_size: {e}')
        return e


def get_status_msg(code):
    msg = ''
    try:
        msg = Constants.BTSE_ENUM[code]
    except Exception as e:
        print(e)
    return msg


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
