from typing import (
    Optional,
    Dict,
    Any
)
import hashlib
import hmac
from hummingbot.connector.exchange.btse.btse_tracking_nonce import get_tracking_nonce


class BtseAuth:
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def generate_auth_dict(self, uri: str, data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Generates authentication signature and returns it in a dictionary
        :return: a dictionary of request info including the request signature and post data
        """
        # Decode API private key from base64 format displayed in account management
        # api_secret: bytes = base64.b64decode(self.secret_key)
        api_secret: bytes = bytes(self.secret_key, 'latin-1')
        api_nonce: str = get_tracking_nonce()
        api_post: str = "nonce=" + api_nonce

        path = uri + api_nonce + ''
        signature = hmac.new(
            api_secret,
            msg=bytes(path, 'latin-1'),
            digestmod=hashlib.sha384
        ).hexdigest()

        # unused if statement
        if data is not None:
            for key, value in data.items():
                api_post += f"&{key}={value}"

        auth_payload = {
            'op': 'authKeyExpires',
            'args': [self.api_key, api_nonce, signature + ""],
        }
        return auth_payload

    def get_headers(self, method: str, path_url: str, data: str = "") -> Dict[str, any]:
        """
        Generates authentication headers required by btse
        :param method: GET / POST / etc.
        :param path_url: e.g. "/accounts"
        :param body: request payload
        :return: a dictionary of auth headers
        """
        nonce = get_tracking_nonce()
        message = path_url + nonce + data

        headers = {}

        signature = hmac.new(
            bytes(self.secret_key, 'latin-1'),
            msg=bytes(message, 'latin-1'),
            digestmod=hashlib.sha384
        ).hexdigest()

        headers = {
            'btse-api': self.api_key,
            'btse-nonce': nonce,
            'btse-sign': signature
        }
        return headers
