ACTIVE_INTERACTIONS = set()


def _key(user_id: int, channel_id: int, command: str) -> str:
    return f"{user_id}:{channel_id}:{command}"


def check_active_interaction(user_id: int, channel_id: int, command: str) -> bool:
    return _key(user_id, channel_id, command) in ACTIVE_INTERACTIONS


def add_active_interaction(user_id: int, channel_id: int, command: str):
    ACTIVE_INTERACTIONS.add(_key(user_id, channel_id, command))


def remove_active_interaction(user_id: int, channel_id: int, command: str):
    ACTIVE_INTERACTIONS.discard(_key(user_id, channel_id, command))
