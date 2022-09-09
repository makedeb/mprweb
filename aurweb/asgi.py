import hashlib
import http
import io
import os
import re
import sys
import traceback
import typing
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import TemplateNotFound
from prometheus_client import multiprocess
from sqlalchemy import and_, or_
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware

import aurweb.captcha  # noqa: F401
import aurweb.config
import aurweb.filters  # noqa: F401
import aurweb.logging
import aurweb.pkgbase.util as pkgbaseutil
from aurweb import logging, prometheus, util
from aurweb.auth import BasicAuthBackend
from aurweb.db import get_engine, query
from aurweb.models import AcceptedTerm, Term
from aurweb.packages.util import get_pkg_or_base
from aurweb.prometheus import instrumentator
from aurweb.redis import redis_connection
from aurweb.routers import APP_ROUTES
from aurweb.scripts import notify
from aurweb.templates import make_context, render_template

logger = logging.get_logger(__name__)

# Setup the FastAPI app.
app = FastAPI()

# Instrument routes with the prometheus-fastapi-instrumentator
# library with custom collectors and expose /metrics.
instrumentator().add(prometheus.http_api_requests_total())
instrumentator().add(prometheus.http_requests_total())
instrumentator().instrument(app)


@app.on_event("startup")
async def app_startup():
    # https://stackoverflow.com/questions/67054759/about-the-maximum-recursion-error-in-fastapi
    # Test failures have been observed by internal starlette code when
    # using starlette.testclient.TestClient. Looking around in regards
    # to the recursion error has really not recommended a course of action
    # other than increasing the recursion limit. For now, that is how
    # we handle the issue: an optional TEST_RECURSION_LIMIT env var
    # provided by the user. Docker uses .env's TEST_RECURSION_LIMIT
    # when running test suites.
    # TODO: Find a proper fix to this issue.
    recursion_limit = int(
        os.environ.get("TEST_RECURSION_LIMIT", sys.getrecursionlimit() + 1000)
    )
    sys.setrecursionlimit(recursion_limit)

    session_secret = aurweb.config.get("fastapi", "session_secret")
    if not session_secret:
        raise Exception("[fastapi] session_secret must not be empty")

    app.mount("/static/", StaticFiles(directory="media/"), name="static_media")

    # Add application middlewares.
    app.add_middleware(AuthenticationMiddleware, backend=BasicAuthBackend())
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

    # Add application routes.
    def add_router(module):
        app.include_router(module.router)

    util.apply_all(APP_ROUTES, add_router)

    # Initialize the database engine and ORM.
    get_engine()


def child_exit(server, worker):  # pragma: no cover
    """This function is required for gunicorn customization
    of prometheus multiprocessing."""
    multiprocess.mark_process_dead(worker.pid)


async def internal_server_error(request: Request, exc: Exception) -> Response:
    """
    Catch all uncaught Exceptions thrown in a route.

    :param request: FastAPI Request
    :return: Rendered 500.html template with status_code 500
    """
    context = make_context(request, "Internal Server Error")

    # Print out the exception via `traceback` and store the value
    # into the `traceback` context variable.
    tb_io = io.StringIO()
    traceback.print_exc(file=tb_io)
    tb = tb_io.getvalue()
    context["traceback"] = tb

    # Produce a SHA1 hash of the traceback string.
    tb_hash = hashlib.sha1(tb.encode()).hexdigest()

    # Use the first 7 characters of the sha1 for the traceback id.
    # We will use this to log and include in the notification.
    tb_id = tb_hash[:7]

    redis = redis_connection()
    pipe = redis.pipeline()
    key = f"tb:{tb_hash}"
    pipe.get(key)
    (retval,) = pipe.execute()
    if not retval:
        # Expire in one hour; this is just done to make sure we
        # don't infinitely store these values, but reduce the number
        # of automated reports (notification below). At this time of
        # writing, unexpected exceptions are not common, thus this
        # will not produce a large memory footprint in redis.
        pipe.set(key, tb)
        pipe.expire(key, 3600)
        pipe.execute()

        retval = tb
    else:
        retval = retval.decode()

    # Log details about the exception traceback.
    logger.error(f"FATAL[{tb_id}]: An unexpected exception has occurred.")
    logger.error(retval)

    # If we're on an API route, return a JSON response.
    if request.url.path.startswith("/api/"):
        return JSONResponse(content={"type": "error", "msg": "Internal server error"})

    return render_template(
        request,
        "errors/500.html",
        context,
        status_code=http.HTTPStatus.INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Handle an HTTPException thrown in a route."""
    phrase = http.HTTPStatus(exc.status_code).phrase
    context = make_context(request, phrase)
    context["exc"] = exc
    context["phrase"] = phrase

    # Additional context for some exceptions.
    if exc.status_code == http.HTTPStatus.NOT_FOUND:

        # If we're at a '/api/' endpoint, return a JSON response.
        if request.url.path.startswith("/api/"):
            return JSONResponse(content={"type": "error", "msg": "Not found."})

        tokens = request.url.path.split("/")
        matches = re.match("^([a-z0-9][a-z0-9.+_-]*?)(\\.git)?$", tokens[1])
        if matches:
            try:
                pkgbase = get_pkg_or_base(matches.group(1))
                context = pkgbaseutil.make_context(request, pkgbase)
            except HTTPException:
                pass

    try:
        return render_template(
            request, f"errors/{exc.status_code}.html", context, exc.status_code
        )
    except TemplateNotFound:
        return render_template(request, "errors/detail.html", context, exc.status_code)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: typing.Callable):
    """This middleware adds the CSP, XCTO, XFO and RP security
    headers to the HTTP response associated with request.

    CSP: Content-Security-Policy
    XCTO: X-Content-Type-Options
    RP: Referrer-Policy
    XFO: X-Frame-Options
    """
    try:
        response = await util.error_or_result(call_next, request)
    except Exception as exc:
        return await internal_server_error(request, exc)

    # Add CSP header.
    request.user.nonce
    csp = "default-src 'self';"
    script_hosts = ["https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net"]
    css_hosts = [
        "https://fonts.googleapis.com",
        "https://meyerweb.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ]
    font_hosts = ["https://fonts.gstatic.com"]
    img_hosts = ["https://img.shields.io"]

    # Scripts.
    csp += "script-src 'self' 'unsafe-inline' " + " ".join(script_hosts) + ";"

    # It's fine if css is inlined.
    csp += "style-src 'self' 'unsafe-inline' " + " ".join(css_hosts) + ";"

    # Fonts.
    csp += "font-src 'self' " + ".".join(font_hosts) + ";"

    # Images.
    csp += "img-src 'self' " + " ".join(img_hosts) + ";"

    response.headers["Content-Security-Policy"] = csp

    # Add XTCO header.
    xcto = "nosniff"
    response.headers["X-Content-Type-Options"] = xcto

    # Add Referrer Policy header.
    rp = "same-origin"
    response.headers["Referrer-Policy"] = rp

    # Add X-Frame-Options header.
    xfo = "SAMEORIGIN"
    response.headers["X-Frame-Options"] = xfo

    return response


@app.middleware("http")
async def check_terms_of_service(request: Request, call_next: typing.Callable):
    """This middleware function redirects authenticated users if they
    have any outstanding Terms to agree to."""
    if request.user.is_authenticated() and request.url.path != "/tos":
        unaccepted = (
            query(Term)
            .join(AcceptedTerm)
            .filter(
                or_(
                    AcceptedTerm.UsersID != request.user.ID,
                    and_(
                        AcceptedTerm.UsersID == request.user.ID,
                        AcceptedTerm.TermsID == Term.ID,
                        AcceptedTerm.Revision < Term.Revision,
                    ),
                )
            )
        )
        if query(Term).count() > unaccepted.count():
            return RedirectResponse("/tos", status_code=int(http.HTTPStatus.SEE_OTHER))

    return await util.error_or_result(call_next, request)


@app.middleware("http")
async def id_redirect_middleware(request: Request, call_next: typing.Callable):
    id = request.query_params.get("id")

    if id is not None:
        # Preserve query string.
        qs = []
        for k, v in request.query_params.items():
            if k != "id":
                qs.append(f"{k}={quote_plus(str(v))}")
        qs = str() if not qs else "?" + "&".join(qs)

        path = request.url.path.rstrip("/")
        return RedirectResponse(f"{path}/{id}{qs}")

    return await util.error_or_result(call_next, request)
