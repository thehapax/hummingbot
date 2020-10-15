from decimal import Decimal

EXCHANGE_NAME = "btse"

# Production
# BTSE_Endpoint = 'https://api.btse.com/spot/api/v3.2'
# BTSE_WSEndpoint = 'wss://ws.btse.com'
# WSS_PRIVATE_URL = 'wss://ws.btse.com/spotWS'
# WSS_PUBLIC_URL = 'wss://ws.btse.com/spotWS'

# Testnet
BTSE_Endpoint = 'https://testapi.btse.io/spot/api/v3.2/'
BTSE_WSEndpoint = 'wss://testws.btse.io'
WSS_PRIVATE_URL = 'wss://testws.btse.io/spotWS'
WSS_PUBLIC_URL = 'wss://testws.btse.io/spotWS'


# Example: REST_URL = "https://api.btse.com/spot/api/v3.2/"
REST_URL = BTSE_Endpoint

# supported BTSE currencies
CURRENCIES = [
    "BTC",
    "BTC-LIQUID",
    "USDT-OMNI",
    "USDT-ERC20",
    "USDT-LIQUID",
    "BCB",
    "LTC",
    "XRP",
    "ETH",
    "XMR",
    "TRYB",
    "TUSD",
    "USDC",
    "XAUT",
    "BTSE"
]

# https://www.btse.com/apiexplorer/spot/#apistate

BTSE_ENUM = {
    1: "MARKET_UNAVAILABLE",
    2: "ORDER_INSERTED",
    4: "ORDER_FULLY_TRANSACTED",
    5: "ORDER_PARTIALLY_TRANSACTED",
    6: "ORDER_CANCELLED",
    8: "INSUFFICIENT_BALANCE",
    9: "TRIGGER_INSERTED",
    10: "TRIGGER_ACTIVATED",
    12: "ERROR_UPDATE_RISK_LIMIT",
    28: "TRANSFER_UNSUCCESSFUL",
    27: "TRANSFER_SUCCESSFUL",
    41: "ERROR_INVALID_RISK_LIMIT",
    64: "STATUS_LIQUIDATION",
    101: "FUTURES_ORDER_PRICE_OUTSIDE_LIQUIDATION_PRICE",
    1003: "ORDER_LIQUIDATION",
    1004: "ORDER_ADL"
}

API_STATUS = {
    200: "API request was successful, refer to the specific API response for expected payload",
    400: "Bad Request. Server will not process this request. This is usually due to invalid parameters sent in request",
    401: "Unauthorized request. Server will not process this request as it does not have valid authentication credentials",
    403: "Forbidden request. Credentials were provided but they were insufficient to perform the request",
    404: "Not found. Indicates that the server understood the request but could not find a correct representation for the target resource",
    405: "Method not allowed. Indicates that the request method is not known to the requested server",
    408: "Request timeout. Indicates that thAe server did not complete the request. BTSE API timeouts are set at 30secs",
    429: "Too many requests. Indicates that the client has exceeded the rates limits set by the server. Refer to Rate Limits for more details",
    500: "Internal server error. Indicates that the server encountered an unexpected condition resulting in not being able to fulfill the request",
    503: "Service Unavailable"
}

# do we need this API_STATUS or is it just BTSE_ENUM
API_REASONS = BTSE_ENUM

# merge two dicts into 1
API_REASONS.update(API_STATUS)

# https://support.btse.com/en/support/solutions/articles/43000533815-spot-trading-limits
BASE_ORDER_MIN = {
    "BTC": Decimal("0.001"),
    "ETH-BTC": Decimal("0.001"),
    "ETH": Decimal("0.01"),
    "LTC": Decimal("0.01"),
    "LTC-BTC": Decimal("0.001"),
    "LTC-ETH": Decimal("0.05"),
    "XMR-BTC": Decimal("0.001"),
    "XMR-ETH": Decimal("0.05"),
    "XMR": Decimal("0.01"),
    "USDT": Decimal("1"),
    "BTSE": Decimal("0.0005"),
    "XAUT": Decimal("0.001"),
    "TRYB-USDT": Decimal("0.1"),
    "XRP": Decimal("0.1"),
    "BCB": Decimal("0.0001"),
    "LEO": Decimal("0.1"),
    "TRX": Decimal("0.1"),
    "STAKE": Decimal("0.01"),
    "STAKE-BTC": Decimal("0.001"),
    "STAKE-ETH": Decimal("0.05"),
    "HXRO-USD": Decimal("0.01"),
    "HXRO-USDT": Decimal("0.01"),
    "HXRO-TUSD": Decimal("0.01"),
    "HXRO-USDC": Decimal("0.01"),
    "HXRO-BTC": Decimal("1"),
    "HXRO-ETH": Decimal("1")
}


# from kraken constants
# replace these values with btse values instead of kraken
'''
CRYPTO_QUOTES = [
    "XBT",
    "ETH",
    "USDT",
    "DAI",
    "USDC",
]

ADDED_CRYPTO_QUOTES = [
    "XXBT",
    "XETH",
    "BTC",
]

FIAT_QUOTES = [
    "USD",
    "EUR",
    "CAD",
    "JPY",
    "GBP",
    "CHF",
    "AUD"
]

FIAT_QUOTES = ["Z" + quote for quote in FIAT_QUOTES] + FIAT_QUOTES

QUOTES = CRYPTO_QUOTES + ADDED_CRYPTO_QUOTES + FIAT_QUOTES

'''
