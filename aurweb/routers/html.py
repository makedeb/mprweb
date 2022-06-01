""" AURWeb's primary routing module. Define all routes via @app.app.{get,post}
decorators in some way; more complex routes should be defined in their
own modules and imported here. """
import os
from http import HTTPStatus

import pygit2
from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from sqlalchemy import case

import aurweb.config
import aurweb.models.package_request
from aurweb import cookies, db, models
from aurweb.auth import requires_auth
from aurweb.models.account_type import TRUSTED_USER_ID
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.package_request import PENDING_ID
from aurweb.models.user import User
from aurweb.packages.search import PackageSearch
from aurweb.templates import make_context, render_template
from aurweb.util import get_current_time

router = APIRouter()


@router.get("/favicon.ico")
async def favicon(request: Request):
    """Some browsers attempt to find a website's favicon via root uri at
    /favicon.ico, so provide a redirection here to our static icon."""
    return RedirectResponse("/static/images/favicon.ico")


@router.post("/language", response_class=RedirectResponse)
async def language(
    request: Request,
    set_lang: str = Form(...),
    next: str = Form(...),
    q: str = Form(default=None),
):
    """
    A POST route used to set a session's language.

    Return a 303 See Other redirect to {next}?next={next}. If we are
    setting the language on any page, we want to preserve query
    parameters across the redirect.
    """
    if next[0] != "/":
        return HTMLResponse(b"Invalid 'next' parameter.", status_code=400)

    query_string = "?" + q if q else str()

    # If the user is authenticated, update the user's LangPreference.
    if request.user.is_authenticated():
        with db.begin():
            request.user.LangPreference = set_lang

    # In any case, set the response's AURLANG cookie that never expires.
    response = RedirectResponse(
        url=f"{next}{query_string}", status_code=HTTPStatus.SEE_OTHER
    )
    secure = aurweb.config.getboolean("options", "disable_http_login")
    response.set_cookie(
        "AURLANG", set_lang, secure=secure, httponly=secure, samesite=cookies.samesite()
    )
    return response


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Homepage route."""
    context = make_context(request, "Home")

    # Get the 10 most recently updated packages.
    context["package_updates"] = (
        db.query(Package)
        .join(PackageBase)
        .filter(models.PackageBase.PackagerUID.isnot(None))
        .order_by(models.PackageBase.ModifiedTS.desc())
        .limit(10)
    ).all()

    # Get the 10 most popular packages.
    #
    # If for any reason a popular package isn't owned by anyone, we don't want to
    # recommend it on the front page, as there might be a concerning reason why it was
    # orphaned.
    search = PackageSearch()
    search.sort_by("p")

    context["popular_packages"] = (
        search.results().filter(PackageBase.MaintainerUID is not None).limit(10)
    )

    return render_template(request, "home.html", context)


def get_number_of_commits():
    commits = 0

    for directory in os.listdir("/aurweb/aur.git"):
        repo = pygit2.Repository(f"/aurweb/aur.git/{directory}")
        branch = repo.references.get("refs/heads/master")

        # The branch won't exist for the repository if there haven't been any
        # commits to it yet.
        if branch is None:
            continue

        for commit in repo.walk(branch.target.hex):
            commits += 1

    return commits


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """Instance information."""
    context = make_context(request, "About")

    # Get the number of packages.
    context["number_of_packages"] = db.query(Package).count()

    # Get the number of orphan packages.
    context["number_of_orphaned_packages"] = (
        db.query(PackageBase)
        .filter(PackageBase.MaintainerUID == None)  # noqa: E711
        .count()
    )

    # Get the number of users.
    context["number_of_users"] = db.query(User).count()

    # Get the number of users who maintain a package (users who are maintainers).
    context["number_of_maintainers"] = (
        db.query(PackageBase).group_by(PackageBase.MaintainerUID).count()
    )

    # Get the number of Trusted Users.
    context["number_of_trusted_users"] = (
        db.query(User).filter(User.AccountTypeID == TRUSTED_USER_ID).count()
    )

    # Get the number of commits.
    context["number_of_commits"] = get_number_of_commits()

    # Get the list of SSH keys.
    context["ssh_key_ed25519"] = aurweb.config.get("fingerprints", "Ed25519")
    context["ssh_key_ecdsa"] = aurweb.config.get("fingerprints", "ECDSA")
    context["ssh_key_rsa"] = aurweb.config.get("fingerprints", "RSA")

    return render_template(request, "about.html", context)


@router.get("/mpr-archives")
async def mpr_archives(request: Request):
    context = make_context(request, "MPR Archives")
    return render_template(request, "mpr-archives.html", context)


@router.get("/metrics")
async def metrics(request: Request):
    registry = CollectorRegistry()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR", None):  # pragma: no cover
        multiprocess.MultiProcessCollector(registry)
    data = generate_latest(registry)
    headers = {"Content-Type": CONTENT_TYPE_LATEST, "Content-Length": str(len(data))}
    return Response(data, headers=headers)


@router.get("/pkgstats")
@requires_auth
async def pkgstats(request: Request):
    """Package Statistics for the current user."""
    context = make_context(request, "Package Statistics")
    context["request"] = request

    # Packages maintained by the user that have been flagged.
    PackageSearch(request.user)
    maintained = (
        PackageSearch(request.user).search_by("m", request.user.Username).results()
    )

    context["flagged_packages"] = (
        maintained.filter(models.PackageBase.OutOfDateTS.isnot(None))
        .order_by(models.PackageBase.ModifiedTS.desc(), models.Package.Name.asc())
        .with_entities(
            models.Package.ID,
            models.Package.Name,
            models.Package.PackageBaseID,
            models.Package.Version,
            models.Package.Description,
            models.PackageBase.Popularity,
            models.PackageBase.NumVotes,
            models.PackageBase.OutOfDateTS,
            models.User.Username.label("Maintainer"),
            models.PackageVote.PackageBaseID.label("Voted"),
            models.PackageNotification.PackageBaseID.label("Notify"),
        )
        .limit(10)
        .all()
    )

    # Package requests created by request.user.
    archive_time = aurweb.config.getint("options", "request_archive_time")
    start = get_current_time() - archive_time

    context["package_requests"] = (
        request.user.package_requests.filter(models.PackageRequest.RequestTS >= start)
        .order_by(
            # Order primarily by the Status column being PENDING_ID, and secondarily by
            # RequestTS; both in descending order.
            case([(models.PackageRequest.Status == PENDING_ID, 1)], else_=0).desc(),
            models.PackageRequest.RequestTS.desc(),
        )
        .limit(10)
        .all()
    )

    # Packages that the request user maintains or comaintains.
    context["packages"] = (
        maintained.with_entities(
            models.Package.ID,
            models.Package.Name,
            models.Package.PackageBaseID,
            models.Package.Version,
            models.Package.Description,
            models.PackageBase.Popularity,
            models.PackageBase.NumVotes,
            models.PackageBase.OutOfDateTS,
            models.User.Username.label("Maintainer"),
            models.PackageVote.PackageBaseID.label("Voted"),
            models.PackageNotification.PackageBaseID.label("Notify"),
        )
        .limit(10)
        .all()
    )

    # Any packages that the request user comaintains.
    context["comaintained"] = (
        PackageSearch(request.user)
        .search_by("c", request.user.Username)
        .sort_by("p", "a")
        .results()
        .with_entities(
            models.Package.ID,
            models.Package.Name,
            models.Package.PackageBaseID,
            models.Package.Version,
            models.Package.Description,
            models.PackageBase.Popularity,
            models.PackageBase.NumVotes,
            models.PackageBase.OutOfDateTS,
            models.User.Username.label("Maintainer"),
            models.PackageVote.PackageBaseID.label("Voted"),
            models.PackageNotification.PackageBaseID.label("Notify"),
        )
        .limit(10)
        .all()
    )

    return render_template(request, "pkgstats.html", context)


@router.get("/raisefivethree", response_class=HTMLResponse)
async def raise_service_unavailable(request: Request):
    context = make_context(request, "Service Unavailable")
    raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE)
    return render_template(request, "about.html", context)
