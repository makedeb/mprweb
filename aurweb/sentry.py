from typing import Callable

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from aurweb import config


def setup():
    """Set up this process for Sentry logging."""
    sentry_dsn = config.get_with_fallback("sentry", "dsn", None)
    sentry_traces_sample_rate = config.get_with_fallback(
        "sentry", "traces_sample_rate", "0.0"
    )

    if sentry_dsn is not None:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[LoggingIntegration(event_level=None)],
            traces_sample_rate=float(sentry_traces_sample_rate),
            send_default_pii=True,
            with_locals=True,
        )


def capture_exception(exc: Exception):
    sentry_sdk.capture_exception(exc)


def run_fn(fn: Callable, err_fn: Callable = None):
    """
    Run a function, logging the exception to Sentry if one occurs.
    If 'err_fn' is passed in, it's ran when an exception occurs, after the exception is
    reported to Sentry.
    """

    try:
        fn()
    except Exception as exc:
        setup()
        capture_exception(exc)
        sentry_sdk.flush()

        if err_fn is not None:
            err_fn()
