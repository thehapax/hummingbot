import time

_last_tracking_nonce: int = 0


# return the nonce as a string instead of as an int.
def get_tracking_nonce() -> str:
    global _last_tracking_nonce
    nonce = int(time.time())
    _last_tracking_nonce = nonce if nonce > _last_tracking_nonce else _last_tracking_nonce + 1
    return str(_last_tracking_nonce)
