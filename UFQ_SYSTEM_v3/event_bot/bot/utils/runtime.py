# Runtime-detected values holder
_bot_username = None


def set_bot_username(username: str):
    global _bot_username
    _bot_username = username


def get_bot_username():
    return _bot_username
