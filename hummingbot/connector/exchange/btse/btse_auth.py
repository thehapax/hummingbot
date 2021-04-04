from typing import (
    Optional,
    Dict,
    Any
)
import hashlib
import hmac
from hummingbot.connector.exchange.btse.btse_tracking_nonce import get_tracking_nonce
import time
import conf


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

    def get_headers(self, path_url: str, data: str = "") -> Dict[str, any]:
        """
        Generates authentication headers required by btse
        :param path_url: e.g. "/accounts"
        :param data: request payload
        :return: a dictionary of auth headers
        """
        # print("******* INSIDE GET HEADERS *******")
        # print(f'\n SECRET KEY : {self.secret_key}, API-KEY : {self.api_key} ')
        # api_secret: bytes = bytes(self.secret_key, 'latin-1')
        # api_key: bytes = bytes(self.api_key, 'latin-1')

        nonce = get_tracking_nonce()
        # nonce = str(int(time.time()*1000))
        # print(f'\nget_tracking_nonce: {nonce}')

        message = path_url + nonce + data
        print(f'MESSAGE: {message}')

        # bheaders = {}
        signature = hmac.new(
            bytes(self.secret_key, 'latin-1'),
            msg=bytes(message, 'latin-1'),
            digestmod=hashlib.sha384
        ).hexdigest()

        headers = {
            'btse-api': self.api_key,
            'btse-nonce': nonce,
            'btse-sign': signature,
            'Accept': 'application/json;charset=UTF-8',
            'Content-Type': 'application/json',
        }
        # print(f'headers: {headers}')
        return headers

    def make_headers(self, path: str, data: str = "") -> Dict[str, any]:
        print("******* INSIDE MAKE HEADERS *******")
        API_KEY = conf.btse_api_key
        API_SECRET = conf.btse_secret_key
        nonce = str(int(time.time() * 1000))
        print("nonce:" + nonce)
        message = path + nonce + data
        print(f'MESSAGE - make_headers: {message}')
        headers = {}
        passph = API_SECRET
        print(f'api-pass: {passph}')

        signature = hmac.new(
            bytes(API_SECRET, 'latin-1'),
            msg=bytes(message, 'latin-1'),
            digestmod=hashlib.sha384
        ).hexdigest()

        headers = {
            'btse-api': API_KEY,
            'btse-nonce': nonce,
            'btse-sign': signature,
            'Accept': 'application/json;charset=UTF-8',
            'Content-Type': 'application/json',
        }
        print(headers)
        return headers
