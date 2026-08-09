"""Small fixture used to prove Habitat orientation and mutation."""

VALID_USERS = {"alice@example.com": "secret"}


def validate_credentials(email: str, password: str) -> bool:
    """Return whether the supplied credentials match the local fixture."""
    return VALID_USERS.get(email) == password


def login(email: str, password: str) -> str:
    if not validate_credentials(email, password):
        return "invalid"
    return "ok"
