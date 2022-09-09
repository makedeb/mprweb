import http
import re
from unittest import mock

import fastapi
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import aurweb.asgi
import aurweb.config
import aurweb.redis
from aurweb.testing.email import Email
from aurweb.testing.requests import Request


@pytest.fixture
def setup(db_test, email_test):
    return


@pytest.mark.asyncio
async def test_asgi_startup_session_secret_exception(monkeypatch):
    """Test that we get an IOError on app_startup when we cannot
    connect to options.redis_address."""

    redis_addr = aurweb.config.get("options", "redis_address")

    def mock_get(section: str, key: str):
        if section == "fastapi" and key == "session_secret":
            return None
        return redis_addr

    with mock.patch("aurweb.config.get", side_effect=mock_get):
        with pytest.raises(Exception):
            await aurweb.asgi.app_startup()


@pytest.mark.asyncio
async def test_asgi_http_exception_handler():
    exc = HTTPException(status_code=422, detail="EXCEPTION!")
    phrase = http.HTTPStatus(exc.status_code).phrase
    response = await aurweb.asgi.http_exception_handler(Request(), exc)
    assert response.status_code == 422
    content = response.body.decode()
    print(content)
    assert f"MPR - {phrase}" in content


def test_internal_server_error(setup: None, caplog: pytest.LogCaptureFixture):
    config_getboolean = aurweb.config.getboolean

    def mock_getboolean(section: str, key: str) -> bool:
        if section == "options" and key == "traceback":
            return True
        return config_getboolean(section, key)

    @aurweb.asgi.app.get("/internal_server_error")
    async def internal_server_error(request: fastapi.Request):
        raise ValueError("test exception")

    with mock.patch("aurweb.config.getboolean", side_effect=mock_getboolean):
        with TestClient(app=aurweb.asgi.app) as request:
            resp = request.get("/internal_server_error")
    assert resp.status_code == int(http.HTTPStatus.INTERNAL_SERVER_ERROR)

    # Assert that the exception got logged with with its traceback id.
    expr = r"FATAL\[.{7}\]"
    assert re.search(expr, caplog.text)

    # Let's do it again; no email should be sent the next time,
    # since the hash is stored in redis.
    with mock.patch("aurweb.config.getboolean", side_effect=mock_getboolean):
        with TestClient(app=aurweb.asgi.app) as request:
            resp = request.get("/internal_server_error")
    assert resp.status_code == int(http.HTTPStatus.INTERNAL_SERVER_ERROR)
