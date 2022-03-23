import functools

from fastapi import APIRouter, Request

from aurweb import db
from aurweb.models.api_key import ApiKey
from aurweb.models.package_base import PackageBase
from aurweb.models.package_notification import PackageNotification
from aurweb.models.package_request import CLOSED_ID, PENDING_ID, PackageRequest
from aurweb.models.request_type import RequestType
from aurweb.packages.util import get_pkg_or_base
from aurweb.templates import make_context, render_template

router = APIRouter()


def get_user_from_api_key(request):
    return (
        db.query(ApiKey)
        .filter(ApiKey.Key == request.headers["Authorization"])
        .first()
        .User
    )


def auth_required(func):
    @functools.wraps(func)
    async def wrapper(request, *args, **kwargs):
        # Make sure an API key was provided.
        api_key = request.headers.get("Authorization")

        if api_key is None:
            return {"type": "error", "msg": "No API key was provided."}

        # If so, make sure it exists.
        db_api_key = db.query(ApiKey).filter(ApiKey.Key == api_key).first()

        if db_api_key is None:
            return {"type": "error", "msg": "Invalid API key."}

        # If all checks out, continue with processing the request.
        return await func(request, *args, **kwargs)

    return wrapper


@router.get("/api")
async def api(request: Request):
    context = make_context(request, "API")
    return render_template(request, "api.html", context)


@router.get("/api/test")
@router.post("/api/test")
@auth_required
async def api_test(request: Request):
    user = get_user_from_api_key(request)
    return {"type": "success", "msg": f"Succesfully authenticated as '{user.Username}'"}


@router.post("/api/adopt/{pkgbase_name}")
@auth_required
async def adopt_pkgbase(request: Request, pkgbase_name: str):
    user = get_user_from_api_key(request)
    pkgbase = get_pkg_or_base(pkgbase_name, PackageBase)
    new_maintainer_pkg_notifs = (
        db.query(PackageNotification)
        .filter(PackageNotification.PackageBaseID == pkgbase.ID)
        .filter(PackageNotification.UserID == user.ID)
        .first()
    )

    if pkgbase.Maintainer is not None:
        return {"type": "error", "msg": "Package is not an orphan."}

    with db.begin():
        pkgbase.MaintainerUID = user.ID

        if new_maintainer_pkg_notifs is None:
            db.create(PackageNotification, PackageBaseID=pkgbase.ID, UserID=user.ID)

    return {"type": "success", "msg": "Succesfully adopted pkgbase"}


@router.post("/api/disown/{pkgbase_name}")
@auth_required
async def disown_pkgbase(request: Request, pkgbase_name: str):
    user = get_user_from_api_key(request)
    pkgbase = get_pkg_or_base(pkgbase_name, PackageBase)

    if pkgbase.Maintainer is None:
        return {"type": "error", "msg": "Package is already an orphan."}

    if pkgbase.Maintainer.Username != user.Username:
        return {
            "type": "error",
            "msg": "You do not have permission to disown this package.",
        }

    # Close any pending orphan requests.
    orphan_id = db.query(RequestType).filter(RequestType.Name == "orphan").first().ID
    pkg_requests = (
        db.query(PackageRequest)
        .filter(PackageRequest.Status == PENDING_ID)
        .filter(PackageRequest.PackageBaseID == pkgbase.ID)
        .filter(PackageRequest.ReqTypeID == orphan_id)
        .all()
    )

    with db.begin():
        for pkg_request in pkg_requests:
            pkg_request.Status = CLOSED_ID

    # If there's a comaintainer, make them the new maintainer (or the first if
    # there are multiple).
    # Otherwise, just orphan the package.
    with db.begin():
        comaintainers = pkgbase.comaintainers.all()

        if len(comaintainers) != 0:
            comaintainer = comaintainers[0]
            pkgbase.MaintainerUID = comaintainer.User.ID
            db.delete(comaintainer)
        else:
            pkgbase.MaintainerUID = None

    return {"type": "success", "msg": "Succesfully disowned package."}
