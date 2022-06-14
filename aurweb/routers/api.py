import functools
import hashlib

import orjson
from fastapi import APIRouter, Request

from aurweb import config, db, time
from aurweb.models.account_type import TRUSTED_USER_ID
from aurweb.models.api_key import ApiKey
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.package_comment import PackageComment
from aurweb.models.package_notification import PackageNotification
from aurweb.models.package_request import CLOSED_ID, PENDING_ID, PackageRequest
from aurweb.models.request_type import RequestType
from aurweb.models.user import User
from aurweb.packages.util import get_pkg_or_base
from aurweb.routers.html import get_number_of_commits
from aurweb.scripts.rendercomment import update_comment_render
from aurweb.templates import make_context, render_template

router = APIRouter()


class MissingJsonKeyException(Exception):
    pass


# Helpful functions.
def hash_api_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_user_from_api_key(request):
    api_key = hash_api_key(request.headers["Authorization"])

    return db.query(ApiKey).filter(ApiKey.KeyHash == api_key).first().User


def get_json_item(body, *args):
    try:
        for item in args:
            body = body[item]
    except (IndexError, KeyError):
        raise MissingJsonKeyException

    return body


# Function wrappers.
def auth_required(func):
    @functools.wraps(func)
    async def wrapper(request, *args, **kwargs):
        # Make sure an API key was provided.
        api_key = request.headers.get("Authorization")

        if api_key is None:
            return {
                "type": "error",
                "code": "err_missing_api_key",
                "msg": "No API key was provided.",
            }

        # If so, make sure it exists.
        hashed_api_key = hash_api_key(api_key)
        db_api_key = db.query(ApiKey).filter(ApiKey.KeyHash == hashed_api_key).first()

        if db_api_key is None:
            return {
                "type": "error",
                "code": "err_invalid_api_key",
                "msg": "Invalid API key.",
            }

        # If all checks out, continue with processing the request.
        return await func(request, *args, **kwargs)

    return wrapper


def catch_exceptions(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except orjson.JSONDecodeError:
            return {
                "type": "error",
                "code": "err_invalid_json_body",
                "msg": "Invalid JSON body in request.",
            }
        except MissingJsonKeyException:
            return {
                "type": "error",
                "code": "err_missing_json_key",
                "msg": "Missing JSON items in body of request.",
            }

    return wrapper


@router.get("/api")
async def api(request: Request):
    context = make_context(request, "API")
    return render_template(request, "api.html", context)


@router.get("/api/meta")
async def api_meta():
    packages = db.query(Package).count()
    orphan_packages = (
        db.query(PackageBase)
        .filter(PackageBase.MaintainerUID == None)  # noqa: E711
        .count()
    )
    users = db.query(User).count()
    maintainers = db.query(PackageBase).group_by(PackageBase.MaintainerUID).count()
    trusted_users = db.query(User).filter(User.AccountTypeID == TRUSTED_USER_ID).count()
    commits = get_number_of_commits()

    return {
        "ssh_key_fingerprints": {
            "ED25519": config.get("fingerprints", "Ed25519"),
            "ECDSA": config.get("fingerprints", "ECDSA"),
            "RSA": config.get("fingerprints", "RSA"),
        },
        "statistics": {
            "packages": packages,
            "orphan_packages": orphan_packages,
            "package_commits": commits,
            "users": users,
            "maintainers": maintainers,
            "trusted_users": trusted_users,
        },
    }


@router.get("/api/test")
@router.post("/api/test")
@auth_required
async def api_test(request: Request):
    user = get_user_from_api_key(request)
    return {
        "type": "success",
        "msg": f"Succesfully authenticated as '{user.Username}'",
        "user": user.Username,
    }


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


@router.post("/api/comment/{pkgbase_name}")
@auth_required
@catch_exceptions
async def post_comment(request: Request, pkgbase_name: str):
    user = get_user_from_api_key(request)
    pkgbase = get_pkg_or_base(pkgbase_name, PackageBase)

    # Get the comment from the request.
    body = orjson.loads(await request.body())
    msg = get_json_item(body, "msg")

    # Create the comment.
    with db.begin():
        comment = db.create(
            PackageComment,
            User=user,
            PackageBase=pkgbase,
            Comments=msg,
            RenderedComment=str(),
            CommentTS=time.utcnow(),
        )

    update_comment_render(comment)

    aur_location = config.get("options", "aur_location")

    return {
        "type": "success",
        "msg": "Succesfully posted comment.",
        "link": f"{aur_location}/packages/{pkgbase.Name}/#comment-{comment.ID}",
    }


@router.get("/api/list-comments/{pkgbase_name}")
async def get_comments(pkgbase_name: str):
    pkgbase = get_pkg_or_base(pkgbase_name, PackageBase)
    comments = (
        db.query(PackageComment)
        .filter(PackageComment.PackageBaseID == pkgbase.ID)
        .all()
    )

    result = []

    for comment in comments:
        result += [
            {
                "date": comment.CommentTS,
                "msg": comment.Comments,
                "msg_rendered": comment.RenderedComment,
                "user": comment.User.Username,
            }
        ]

    return result
