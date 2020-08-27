import re

BTSE_REST_URL = "https://api.btse.com/spot/api/v3.2"
BTSE_REST_AUTH_URL = "https://api.btse.com/spot/api/v3.2"
BTSE_WS_URI = "wss://ws.btse.com/spotWS"
BTSE_WS_AUTH_URI = "wss://ws.btse.com/spotWS"

TESTNET_REST_URL = "https://testapi.btse.io/spot"
TESTNET_WS_URL = "wss://testws.btse.io/spotWS"

TRADING_PAIR_SPLITTER = re.compile(r"^(\w+)(BTC|ETH|USD|USDT|USDC|TUSD)$")
# do we really need this?


class SubmitOrder:
    OID = 0

    def __init__(self, oid):
        self.oid = str(oid)

    @classmethod
    def parse(cls, order_snapshot):
        return cls(order_snapshot[cls.OID])


class ContentEventType:
    HEART_BEAT = "hb"
    AUTH = "auth"
    INFO = "info"


'''
Supported Currencies
    BTC
    BTC-LIQUID
    USDT-OMNI
    USDT-ERC20
    USDT-LIQUID
    BCB
    LTC
    XRP
    ETH
    XMR
    TRYB
    TUSD
    USDC
    XAUT
    BTSE
'''


'''

    1: MARKET_UNAVAILABLE = Futures market is unavailable
    2: ORDER_INSERTED = Order is inserted successfully
    4: ORDER_FULLY_TRANSACTED = Order is fully transacted
    5: ORDER_PARTIALLY_TRANSACTED = Order is partially transacted
    6: ORDER_CANCELLED = Order is cancelled successfully
    8: INSUFFICIENT_BALANCE = Insufficient balance in account
    9: TRIGGER_INSERTED = Trigger Order is inserted successfully
    10: TRIGGER_ACTIVATED = Trigger Order is activated successfully
    12: ERROR_UPDATE_RISK_LIMIT = Error in updating risk limit
    28: TRANSFER_UNSUCCESSFUL = Transfer funds between spot and futures is unsuccessful
    27: TRANSFER_SUCCESSFUL = Transfer funds between futures and spot is successful
    41: ERROR_INVALID_RISK_LIMIT = Invalid risk limit was specified
    64: STATUS_LIQUIDATION = Account is undergoing liquidation
    101: FUTURES_ORDER_PRICE_OUTSIDE_LIQUIDATION_PRICE = Futures order is outside of liquidation price
    1003: ORDER_LIQUIDATION = Order is undergoing liquidation
    1004: ORDER_ADL = Order is undergoing ADL
'''


'''
API status

    200 - API request was successful, refer to the specific API response for expected payload
    400 - Bad Request. Server will not process this request. This is usually due to invalid parameters sent in request
    401 - Unauthorized request. Server will not process this request as it does not have valid authentication credentials
    403 - Forbidden request. Credentials were provided but they were insufficient to perform the request
    404 - Not found. Indicates that the server understood the request but could not find a correct representation for the target resource
    405 - Method not allowed. Indicates that the request method is not known to the requested server
    408 - Request timeout. Indicates that the server did not complete the request. BTSE API timeouts are set at 30secs
    429 - Too many requests. Indicates that the client has exceeded the rates limits set by the server. Refer to Rate Limits for more details
    500 - Internal server error. Indicates that the server encountered an unexpected condition resulting in not being able to fulfill the request
'''
