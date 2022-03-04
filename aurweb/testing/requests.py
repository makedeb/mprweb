from typing import Dict

import aurweb.config


class User:
    """A fake User model."""

    # Fake columns.
    LangPreference = aurweb.config.get("options", "default_lang")
    Timezone = aurweb.config.get("options", "default_timezone")

    # A fake authenticated flag.
    authenticated = False

    def is_authenticated(self):
        return self.authenticated


class Client:
    """A fake FastAPI Request.client object."""

    # A fake host.
    host = "127.0.0.1"


class URL:
    path = "/"


class Request:
    """A fake Request object which mimics a FastAPI Request for tests."""

    client = Client()
    url = URL()

    def __init__(
        self,
        user: User = User(),
        authenticated: bool = False,
        method: str = "GET",
        headers: Dict[str, str] = dict(),
        cookies: Dict[str, str] = dict(),
    ) -> "Request":
        self.user = user
        self.user.authenticated = authenticated

        self.method = method.upper()
        self.headers = headers
        self.cookies = cookies
