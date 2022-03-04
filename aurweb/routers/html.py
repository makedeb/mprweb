""" AURWeb's primary routing module. Define all routes via @app.app.{get,post}
decorators in some way; more complex routes should be defined in their
own modules and imported here. """
import os

from http import HTTPStatus

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from sqlalchemy import and_, case, or_

import aurweb.config
import aurweb.models.package_request

from aurweb import cookies, db, models, time, util
from aurweb.cache import db_count_cache
from aurweb.models.account_type import TRUSTED_USER_AND_DEV_ID, TRUSTED_USER_ID
from aurweb.models.package_base import PackageBase
from aurweb.models.package_request import PENDING_ID
from aurweb.packages.util import query_notified, query_voted, updated_packages
from aurweb.templates import make_context, render_template
from aurweb.packages.search import PackageSearch

router = APIRouter()


@router.get("/favicon.ico")
async def favicon(request: Request):
    """ Some browsers attempt to find a website's favicon via root uri at
    /favicon.ico, so provide a redirection here to our static icon. """
    return RedirectResponse("/static/images/favicon.ico")


@router.post("/language", response_class=RedirectResponse)
async def language(request: Request,
                   set_lang: str = Form(...),
                   next: str = Form(...),
                   q: str = Form(default=None)):
    """
    A POST route used to set a session's language.

    Return a 303 See Other redirect to {next}?next={next}. If we are
    setting the language on any page, we want to preserve query
    parameters across the redirect.
    """
    if next[0] != '/':
        return HTMLResponse(b"Invalid 'next' parameter.", status_code=400)

    query_string = "?" + q if q else str()

    # If the user is authenticated, update the user's LangPreference.
    if request.user.is_authenticated():
        with db.begin():
            request.user.LangPreference = set_lang

    # In any case, set the response's AURLANG cookie that never expires.
    response = RedirectResponse(url=f"{next}{query_string}",
                                status_code=HTTPStatus.SEE_OTHER)
    secure = aurweb.config.getboolean("options", "disable_http_login")
    response.set_cookie("AURLANG", set_lang,
                        secure=secure, httponly=secure,
                        samesite=cookies.samesite())
    return response


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """ Homepage route. """
    context = make_context(request, "Home")
    cache_expire = 300  # Five minutes.

    # Get the 10 most recently updated packages.
    context["package_updates"] = updated_packages(10, cache_expire)

    # Get the 10 most popular packages.
    # If for any reason a popular package isn't owned by anyone, we don't want to recommend it on the front page, as there might be a concerning reason why it was orphaned.
    search = PackageSearch()
    search.sort_by("p")
    
    context["popular_packages"] = search.results().filter(PackageBase.MaintainerUID != None).limit(10)

    return render_template(request, "home.html", context)


@router.get("/about", response_class=HTMLResponse)
async def index(request: Request):
    """ Instance information. """
    context = make_context(request, "About")
    context["ssh_key_ed25519"] = aurweb.config.get("fingerprints", "Ed25519")
    context["ssh_key_ecdsa"] = aurweb.config.get("fingerprints", "ECDSA")
    context["ssh_key_rsa"] = aurweb.config.get("fingerprints", "RSA")
    return render_template(request, "about.html", context)


@router.get("/metrics")
async def metrics(request: Request):
    registry = CollectorRegistry()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR", None):  # pragma: no cover
        multiprocess.MultiProcessCollector(registry)
    data = generate_latest(registry)
    headers = {
        "Content-Type": CONTENT_TYPE_LATEST,
        "Content-Length": str(len(data))
    }
    return Response(data, headers=headers)


@router.get("/raisefivethree", response_class=HTMLResponse)
async def raise_service_unavailable(request: Request):
    raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE)
