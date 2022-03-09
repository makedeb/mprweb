from http import HTTPStatus

import pygit2
from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import and_

from aurweb import config, db, l10n, logging, templates, time, util
from aurweb.auth import creds, requires_auth
from aurweb.exceptions import InvariantError, ValidationError
from aurweb.models import Package, PackageBase
from aurweb.models.package_comment import PackageComment
from aurweb.models.package_keyword import PackageKeyword
from aurweb.models.package_notification import PackageNotification
from aurweb.models.package_request import ACCEPTED_ID, PENDING_ID, PackageRequest
from aurweb.models.package_vote import PackageVote
from aurweb.models.request_type import DELETION_ID, MERGE_ID, ORPHAN_ID
from aurweb.packages.requests import update_closure_comment
from aurweb.packages.util import get_pkg_or_base, get_pkgbase_comment
from aurweb.pkgbase import actions
from aurweb.pkgbase import util as pkgbaseutil
from aurweb.pkgbase import validate
from aurweb.scripts import notify, popupdate
from aurweb.scripts.rendercomment import update_comment_render_fastapi
from aurweb.templates import make_variable_context, render_template
from aurweb.util import get_current_time

logger = logging.get_logger(__name__)
router = APIRouter()


@router.get("/pkgbase/{name}")
async def pkgbase(request: Request, name: str) -> Response:
    """
    Single package base view.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :return: HTMLResponse
    """
    # Get the PackageBase.
    pkgbase = get_pkg_or_base(name, PackageBase)

    # If this is not a split package, redirect to /packages/{name}.
    if pkgbase.packages.count() == 1:
        return RedirectResponse(
            f"/packages/{name}", status_code=int(HTTPStatus.SEE_OTHER)
        )

    # Add our base information.
    context = pkgbaseutil.make_context(request, pkgbase)
    context["packages"] = pkgbase.packages.all()

    return render_template(request, "pkgbase/index.html", context)


@router.get("/pkgbase/{name}/voters")
async def pkgbase_voters(request: Request, name: str) -> Response:
    """
    View of package base voters.

    Requires `request.user` has creds.PKGBASE_LIST_VOTERS credential.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :return: HTMLResponse
    """
    # Get the PackageBase.
    pkgbase = get_pkg_or_base(name, PackageBase)

    if not request.user.has_credential(creds.PKGBASE_LIST_VOTERS):
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Voters")
    context["pkgbase"] = pkgbase

    return render_template(request, "pkgbase/voters.html", context)


@router.get("/pkgbase/{name}/flag-comment")
async def pkgbase_flag_comment(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    if pkgbase.Flagger is None:
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Flag Comment")
    context["pkgbase"] = pkgbase
    return render_template(request, "pkgbase/flag-comment.html", context)


@router.post("/pkgbase/{name}/keywords")
async def pkgbase_keywords(
    request: Request, name: str, keywords: str = Form(default=str())
):
    pkgbase = get_pkg_or_base(name, PackageBase)
    keywords = set(keywords.split(" "))

    # Delete all keywords which are not supplied by the user.
    other_keywords = pkgbase.keywords.filter(~PackageKeyword.Keyword.in_(keywords))
    other_keyword_strings = [kwd.Keyword for kwd in other_keywords]

    existing_keywords = set(
        kwd.Keyword
        for kwd in pkgbase.keywords.filter(
            ~PackageKeyword.Keyword.in_(other_keyword_strings)
        )
    )
    with db.begin():
        db.delete_all(other_keywords)
        for keyword in keywords.difference(existing_keywords):
            db.create(PackageKeyword, PackageBase=pkgbase, Keyword=keyword)

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.get("/pkgbase/{name}/flag")
@requires_auth
async def pkgbase_flag_get(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    has_cred = request.user.has_credential(creds.PKGBASE_FLAG)
    if not has_cred or pkgbase.Flagger is not None:
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Flag Package Out-Of-Date")
    context["pkgbase"] = pkgbase
    return render_template(request, "pkgbase/flag.html", context)


@router.post("/pkgbase/{name}/flag")
@requires_auth
async def pkgbase_flag_post(
    request: Request, name: str, comments: str = Form(default=str())
):
    pkgbase = get_pkg_or_base(name, PackageBase)

    if not comments:
        context = templates.make_context(request, "Flag Package Out-Of-Date")
        context["pkgbase"] = pkgbase
        context["errors"] = [
            "The selected packages have not been flagged, " "please enter a comment."
        ]
        return render_template(
            request, "pkgbase/flag.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    has_cred = request.user.has_credential(creds.PKGBASE_FLAG)
    if has_cred and not pkgbase.Flagger:
        now = time.utcnow()
        with db.begin():
            pkgbase.OutOfDateTS = now
            pkgbase.Flagger = request.user
            pkgbase.FlaggerComment = comments

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/comments")
@requires_auth
async def pkgbase_comments_post(
    request: Request,
    name: str,
    comment: str = Form(default=str()),
    enable_notifications: bool = Form(default=False),
):
    """Add a new comment via POST request."""
    pkgbase = get_pkg_or_base(name, PackageBase)

    if not comment:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST)

    # If the provided comment is different than the record's version,
    # update the db record.
    now = time.utcnow()
    with db.begin():
        comment = db.create(
            PackageComment,
            User=request.user,
            PackageBase=pkgbase,
            Comments=comment,
            RenderedComment=str(),
            CommentTS=now,
        )

        if enable_notifications and not request.user.notified(pkgbase):
            db.create(PackageNotification, User=request.user, PackageBase=pkgbase)
    update_comment_render_fastapi(comment)

    # Redirect to the pkgbase page.
    return RedirectResponse(
        f"/pkgbase/{pkgbase.Name}#comment-{comment.ID}",
        status_code=HTTPStatus.SEE_OTHER,
    )


@router.get("/pkgbase/{name}/comments/{id}/edit")
@requires_auth
async def pkgbase_comment_edit(
    request: Request, name: str, id: int, next: str = Form(default=None)
):
    """
    Render the non-javascript edit form.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :param id: PackageComment.ID
    :param next: Optional `next` parameter used in the POST request
    :return: HTMLResponse
    """
    pkgbase = get_pkg_or_base(name, PackageBase)
    comment = get_pkgbase_comment(pkgbase, id)

    if not next:
        next = f"/pkgbase/{name}"

    context = await make_variable_context(request, "Edit comment", next=next)
    context["comment"] = comment
    return render_template(request, "pkgbase/comments/edit.html", context)


@router.post("/pkgbase/{name}/comments/{id}")
@requires_auth
async def pkgbase_comment_post(
    request: Request,
    name: str,
    id: int,
    comment: str = Form(default=str()),
    enable_notifications: bool = Form(default=False),
    next: str = Form(default=None),
):
    """Edit an existing comment."""
    pkgbase = get_pkg_or_base(name, PackageBase)
    db_comment = get_pkgbase_comment(pkgbase, id)

    if not comment:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST)

    # If the provided comment is different than the record's version,
    # update the db record.
    now = time.utcnow()
    if db_comment.Comments != comment:
        with db.begin():
            db_comment.Comments = comment
            db_comment.Editor = request.user
            db_comment.EditedTS = now

            db_notif = request.user.notifications.filter(
                PackageNotification.PackageBaseID == pkgbase.ID
            ).first()
            if enable_notifications and not db_notif:
                db.create(PackageNotification, User=request.user, PackageBase=pkgbase)
    update_comment_render_fastapi(db_comment)

    if not next:
        next = f"/pkgbase/{pkgbase.Name}"

    # Redirect to the pkgbase page anchored to the updated comment.
    return RedirectResponse(
        f"{next}#comment-{db_comment.ID}", status_code=HTTPStatus.SEE_OTHER
    )


@router.post("/pkgbase/{name}/comments/{id}/pin")
@requires_auth
async def pkgbase_comment_pin(
    request: Request, name: str, id: int, next: str = Form(default=None)
):
    """
    Pin a comment.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :param id: PackageComment.ID
    :param next: Optional `next` parameter used in the POST request
    :return: RedirectResponse to `next`
    """
    pkgbase = get_pkg_or_base(name, PackageBase)
    comment = get_pkgbase_comment(pkgbase, id)

    has_cred = request.user.has_credential(
        creds.COMMENT_PIN, approved=[pkgbase.Maintainer]
    )
    if not has_cred:
        _ = l10n.get_translator_for_request(request)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=_("You are not allowed to pin this comment."),
        )

    now = time.utcnow()
    with db.begin():
        comment.PinnedTS = now

    if not next:
        next = f"/pkgbase/{name}"

    return RedirectResponse(next, status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/comments/{id}/unpin")
@requires_auth
async def pkgbase_comment_unpin(
    request: Request, name: str, id: int, next: str = Form(default=None)
):
    """
    Unpin a comment.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :param id: PackageComment.ID
    :param next: Optional `next` parameter used in the POST request
    :return: RedirectResponse to `next`
    """
    pkgbase = get_pkg_or_base(name, PackageBase)
    comment = get_pkgbase_comment(pkgbase, id)

    has_cred = request.user.has_credential(
        creds.COMMENT_PIN, approved=[pkgbase.Maintainer]
    )
    if not has_cred:
        _ = l10n.get_translator_for_request(request)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=_("You are not allowed to unpin this comment."),
        )

    with db.begin():
        comment.PinnedTS = 0

    if not next:
        next = f"/pkgbase/{name}"

    return RedirectResponse(next, status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/comments/{id}/delete")
@requires_auth
async def pkgbase_comment_delete(
    request: Request, name: str, id: int, next: str = Form(default=None)
):
    """
    Delete a comment.

    This action does **not** delete the comment from the database, but
    sets PackageBase.DelTS and PackageBase.DeleterUID, which is used to
    decide who gets to view the comment and what utilities it gets.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :param id: PackageComment.ID
    :param next: Optional `next` parameter used in the POST request
    :return: RedirectResposne to `next`
    """
    pkgbase = get_pkg_or_base(name, PackageBase)
    comment = get_pkgbase_comment(pkgbase, id)

    authorized = request.user.has_credential(creds.COMMENT_DELETE, [comment.User])
    if not authorized:
        _ = l10n.get_translator_for_request(request)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=_("You are not allowed to delete this comment."),
        )

    now = time.utcnow()
    with db.begin():
        comment.Deleter = request.user
        comment.DelTS = now

    if not next:
        next = f"/pkgbase/{name}"

    return RedirectResponse(next, status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/comments/{id}/undelete")
@requires_auth
async def pkgbase_comment_undelete(
    request: Request, name: str, id: int, next: str = Form(default=None)
):
    """
    Undelete a comment.

    This action does **not** undelete any comment from the database, but
    unsets PackageBase.DelTS and PackageBase.DeleterUID which restores
    the comment to a standard state.

    :param request: FastAPI Request
    :param name: PackageBase.Name
    :param id: PackageComment.ID
    :param next: Optional `next` parameter used in the POST request
    :return: RedirectResponse to `next`
    """
    pkgbase = get_pkg_or_base(name, PackageBase)
    comment = get_pkgbase_comment(pkgbase, id)

    has_cred = request.user.has_credential(
        creds.COMMENT_UNDELETE, approved=[comment.User]
    )
    if not has_cred:
        _ = l10n.get_translator_for_request(request)
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail=_("You are not allowed to undelete this comment."),
        )

    with db.begin():
        comment.Deleter = None
        comment.DelTS = None

    if not next:
        next = f"/pkgbase/{name}"

    return RedirectResponse(next, status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/vote")
@requires_auth
async def pkgbase_vote(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    vote = pkgbase.package_votes.filter(PackageVote.UsersID == request.user.ID).first()
    has_cred = request.user.has_credential(creds.PKGBASE_VOTE)
    if has_cred and not vote:
        now = time.utcnow()
        with db.begin():
            db.create(PackageVote, User=request.user, PackageBase=pkgbase, VoteTS=now)

        # Update NumVotes/Popularity.
        popupdate.run_single(pkgbase)

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/unvote")
@requires_auth
async def pkgbase_unvote(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    vote = pkgbase.package_votes.filter(PackageVote.UsersID == request.user.ID).first()
    has_cred = request.user.has_credential(creds.PKGBASE_VOTE)
    if has_cred and vote:
        with db.begin():
            db.delete(vote)

        # Update NumVotes/Popularity.
        popupdate.run_single(pkgbase)

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/notify")
@requires_auth
async def pkgbase_notify(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)
    actions.pkgbase_notify_instance(request, pkgbase)
    return RedirectResponse(
        f"/pkgbase/{name}/#package-actions", status_code=HTTPStatus.SEE_OTHER
    )


@router.post("/pkgbase/{name}/unnotify")
@requires_auth
async def pkgbase_unnotify(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)
    actions.pkgbase_unnotify_instance(request, pkgbase)
    return RedirectResponse(
        f"/pkgbase/{name}/#package-actions", status_code=HTTPStatus.SEE_OTHER
    )


@router.post("/pkgbase/{name}/unflag")
@requires_auth
async def pkgbase_unflag(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)
    actions.pkgbase_unflag_instance(request, pkgbase)
    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.get("/pkgbase/{name}/disown")
@requires_auth
async def pkgbase_disown_get(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    has_cred = request.user.has_credential(
        creds.PKGBASE_DISOWN, approved=[pkgbase.Maintainer]
    )
    if not has_cred:
        return RedirectResponse(f"/pkgbase/{name}", HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Disown Package")
    context["pkgbase"] = pkgbase
    return render_template(request, "pkgbase/disown.html", context)


@router.post("/pkgbase/{name}/disown")
@requires_auth
async def pkgbase_disown_post(
    request: Request,
    name: str,
    comments: str = Form(default=str()),
    confirm: bool = Form(default=False),
):
    pkgbase = get_pkg_or_base(name, PackageBase)

    has_cred = request.user.has_credential(
        creds.PKGBASE_DISOWN, approved=[pkgbase.Maintainer]
    )
    if not has_cred:
        return RedirectResponse(f"/pkgbase/{name}", HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Disown Package")
    context["pkgbase"] = pkgbase
    if not confirm:
        context["errors"] = [
            (
                "The selected packages have not been disowned, "
                "check the confirmation checkbox."
            )
        ]
        return render_template(
            request, "pkgbase/disown.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    with db.begin():
        update_closure_comment(pkgbase, ORPHAN_ID, comments)

    try:
        actions.pkgbase_disown_instance(request, pkgbase)
    except InvariantError as exc:
        context["errors"] = [str(exc)]
        return render_template(
            request, "pkgbase/disown.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/adopt")
@requires_auth
async def pkgbase_adopt_post(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)

    has_cred = request.user.has_credential(creds.PKGBASE_ADOPT)
    if has_cred or not pkgbase.Maintainer:
        # If the user has credentials, they'll adopt the package regardless
        # of maintainership. Otherwise, we'll promote the user to maintainer
        # if no maintainer currently exists.
        actions.pkgbase_adopt_instance(request, pkgbase)

    return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)


@router.get("/pkgbase/{name}/comaintainers")
@requires_auth
async def pkgbase_comaintainers(request: Request, name: str) -> Response:
    # Get the PackageBase.
    pkgbase = get_pkg_or_base(name, PackageBase)

    # Unauthorized users (Non-TU/Dev and not the pkgbase maintainer)
    # get redirected to the package base's page.
    has_creds = request.user.has_credential(
        creds.PKGBASE_EDIT_COMAINTAINERS, approved=[pkgbase.Maintainer]
    )
    if not has_creds:
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    # Add our base information.
    context = templates.make_context(request, "Manage Co-maintainers")
    context.update(
        {
            "pkgbase": pkgbase,
            "comaintainers": [c.User.Username for c in pkgbase.comaintainers],
        }
    )

    return render_template(request, "pkgbase/comaintainers.html", context)


@router.post("/pkgbase/{name}/comaintainers")
@requires_auth
async def pkgbase_comaintainers_post(
    request: Request, name: str, users: str = Form(default=str())
) -> Response:
    # Get the PackageBase.
    pkgbase = get_pkg_or_base(name, PackageBase)

    # Unauthorized users (Non-TU/Dev and not the pkgbase maintainer)
    # get redirected to the package base's page.
    has_creds = request.user.has_credential(
        creds.PKGBASE_EDIT_COMAINTAINERS, approved=[pkgbase.Maintainer]
    )
    if not has_creds:
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    users = {e.strip() for e in users.split("\n") if bool(e.strip())}
    records = {c.User.Username for c in pkgbase.comaintainers}

    users_to_rm = records.difference(users)
    pkgbaseutil.remove_comaintainers(pkgbase, users_to_rm)
    logger.debug(
        f"{request.user} removed comaintainers from " f"{pkgbase.Name}: {users_to_rm}"
    )

    users_to_add = users.difference(records)
    error = pkgbaseutil.add_comaintainers(request, pkgbase, users_to_add)
    if error:
        context = templates.make_context(request, "Manage Co-maintainers")
        context["pkgbase"] = pkgbase
        context["comaintainers"] = [c.User.Username for c in pkgbase.comaintainers]
        context["errors"] = [error]
        return render_template(request, "pkgbase/comaintainers.html", context)

    logger.debug(
        f"{request.user} added comaintainers to " f"{pkgbase.Name}: {users_to_add}"
    )

    return RedirectResponse(
        f"/pkgbase/{pkgbase.Name}", status_code=HTTPStatus.SEE_OTHER
    )


@router.get("/pkgbase/{name}/request")
@requires_auth
async def pkgbase_request(request: Request, name: str):
    pkgbase = get_pkg_or_base(name, PackageBase)
    context = await make_variable_context(request, "Submit Request")
    context["pkgbase"] = pkgbase
    return render_template(request, "pkgbase/request.html", context)


@router.post("/pkgbase/{name}/request")
@requires_auth
async def pkgbase_request_post(
    request: Request,
    name: str,
    type: str = Form(...),
    merge_into: str = Form(default=None),
    comments: str = Form(default=str()),
):
    pkgbase = get_pkg_or_base(name, PackageBase)

    # Create our render context.
    context = await make_variable_context(request, "Submit Request")
    context["pkgbase"] = pkgbase

    types = {"deletion": DELETION_ID, "merge": MERGE_ID, "orphan": ORPHAN_ID}

    if type not in types:
        # In the case that someone crafted a POST request with an invalid
        # type, just return them to the request form with BAD_REQUEST status.
        return render_template(
            request, "pkgbase/request.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    try:
        validate.request(pkgbase, type, comments, merge_into, context)
    except ValidationError as exc:
        logger.error(f"Request Validation Error: {str(exc.data)}")
        context["errors"] = exc.data
        return render_template(request, "pkgbase/request.html", context)

    # All good. Create a new PackageRequest based on the given type.
    now = time.utcnow()
    with db.begin():
        pkgreq = db.create(
            PackageRequest,
            ReqTypeID=types.get(type),
            User=request.user,
            RequestTS=now,
            PackageBase=pkgbase,
            PackageBaseName=pkgbase.Name,
            MergeBaseName=merge_into,
            Comments=comments,
            ClosureComment=str(),
        )

    # Prepare notification object.
    notif = notify.RequestOpenNotification(
        request.user.ID,
        pkgreq.ID,
        type,
        pkgreq.PackageBase.ID,
        merge_into=merge_into or None,
    )

    # Send the notification now that we're out of the DB scope.
    notif.send()

    auto_orphan_age = config.getint("options", "auto_orphan_age")
    auto_delete_age = config.getint("options", "auto_delete_age")

    ood_ts = pkgbase.OutOfDateTS or 0
    flagged = ood_ts and (now - ood_ts) >= auto_orphan_age
    is_maintainer = pkgbase.Maintainer == request.user
    outdated = (now - pkgbase.SubmittedTS) <= auto_delete_age

    if type == "orphan" and flagged:
        # This request should be auto-accepted.
        with db.begin():
            pkgbase.Maintainer = None
            pkgreq.Status = ACCEPTED_ID
        notif = notify.RequestCloseNotification(
            request.user.ID, pkgreq.ID, pkgreq.status_display()
        )
        notif.send()
        logger.debug(f"New request #{pkgreq.ID} is marked for auto-orphan.")
    elif type == "deletion" and is_maintainer and outdated:
        # This request should be auto-accepted.
        notifs = actions.pkgbase_delete_instance(request, pkgbase, comments=comments)
        util.apply_all(notifs, lambda n: n.send())
        logger.debug(f"New request #{pkgreq.ID} is marked for auto-deletion.")

    # Redirect the submitting user to /packages.
    return RedirectResponse("/packages", status_code=HTTPStatus.SEE_OTHER)


@router.get("/pkgbase/{name}/delete")
@requires_auth
async def pkgbase_delete_get(request: Request, name: str):
    if not request.user.has_credential(creds.PKGBASE_DELETE):
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    context = templates.make_context(request, "Package Deletion")
    context["pkgbase"] = get_pkg_or_base(name, PackageBase)
    return render_template(request, "pkgbase/delete.html", context)


@router.post("/pkgbase/{name}/delete")
@requires_auth
async def pkgbase_delete_post(
    request: Request,
    name: str,
    confirm: bool = Form(default=False),
    comments: str = Form(default=str()),
):
    pkgbase = get_pkg_or_base(name, PackageBase)

    if not request.user.has_credential(creds.PKGBASE_DELETE):
        return RedirectResponse(f"/pkgbase/{name}", status_code=HTTPStatus.SEE_OTHER)

    if not confirm:
        context = templates.make_context(request, "Package Deletion")
        context["pkgbase"] = pkgbase
        context["errors"] = [
            (
                "The selected packages have not been deleted, "
                "check the confirmation checkbox."
            )
        ]
        return render_template(
            request, "pkgbase/delete.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    if comments:
        # Update any existing deletion requests' ClosureComment.
        with db.begin():
            requests = pkgbase.requests.filter(
                and_(
                    PackageRequest.Status == PENDING_ID,
                    PackageRequest.ReqTypeID == DELETION_ID,
                )
            )
            for pkgreq in requests:
                pkgreq.ClosureComment = comments

    notifs = actions.pkgbase_delete_instance(request, pkgbase, comments=comments)
    util.apply_all(notifs, lambda n: n.send())
    return RedirectResponse("/packages", status_code=HTTPStatus.SEE_OTHER)


@router.get("/pkgbase/{name}/merge")
@requires_auth
async def pkgbase_merge_get(
    request: Request,
    name: str,
    into: str = Query(default=str()),
    next: str = Query(default=str()),
):
    pkgbase = get_pkg_or_base(name, PackageBase)

    context = templates.make_context(request, "Package Merging")
    context.update({"pkgbase": pkgbase, "into": into, "next": next})

    status_code = HTTPStatus.OK
    # TODO: Lookup errors from credential instead of hardcoding them.
    # Idea: Something like credential_errors(creds.PKGBASE_MERGE).
    # Perhaps additionally: bad_credential_status_code(creds.PKGBASE_MERGE).
    # Don't take these examples verbatim. We should find good naming.
    if not request.user.has_credential(creds.PKGBASE_MERGE):
        context["errors"] = ["Only Trusted Users and Developers can merge packages."]
        status_code = HTTPStatus.UNAUTHORIZED

    return render_template(
        request, "pkgbase/merge.html", context, status_code=status_code
    )


@router.post("/pkgbase/{name}/merge")
@requires_auth
async def pkgbase_merge_post(
    request: Request,
    name: str,
    into: str = Form(default=str()),
    comments: str = Form(default=str()),
    confirm: bool = Form(default=False),
    next: str = Form(default=str()),
):

    pkgbase = get_pkg_or_base(name, PackageBase)
    context = await make_variable_context(request, "Package Merging")
    context["pkgbase"] = pkgbase

    # TODO: Lookup errors from credential instead of hardcoding them.
    if not request.user.has_credential(creds.PKGBASE_MERGE):
        context["errors"] = ["Only Trusted Users and Developers can merge packages."]
        return render_template(
            request, "pkgbase/merge.html", context, status_code=HTTPStatus.UNAUTHORIZED
        )

    if not confirm:
        context["errors"] = [
            "The selected packages have not been deleted, "
            "check the confirmation checkbox."
        ]
        return render_template(
            request, "pkgbase/merge.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    try:
        target = get_pkg_or_base(into, PackageBase)
    except HTTPException:
        context["errors"] = ["Cannot find package to merge votes and comments into."]
        return render_template(
            request, "pkgbase/merge.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    if pkgbase == target:
        context["errors"] = ["Cannot merge a package base with itself."]
        return render_template(
            request, "pkgbase/merge.html", context, status_code=HTTPStatus.BAD_REQUEST
        )

    with db.begin():
        update_closure_comment(pkgbase, MERGE_ID, comments, target=target)

    # Merge pkgbase into target.
    actions.pkgbase_merge_instance(request, pkgbase, target, comments=comments)

    if not next:
        next = f"/pkgbase/{target.Name}"

    # Redirect to the newly merged into package.
    return RedirectResponse(next, status_code=HTTPStatus.SEE_OTHER)


@router.post("/pkgbase/{name}/repology-check")
@requires_auth
async def repology_check(
    request: Request, name: str, repology_check: str = Form(default=str())
):
    enable_str = "Enable Repology Out of Date Notifications"

    pkgbase = get_pkg_or_base(name, Package).PackageBase

    if (request.user != pkgbase.Maintainer) and (
        not request.user.has_credential(creds.PKGBASE_REPOLOGY_CHECK)
    ):
        return RedirectResponse(
            f"/pkgbase/{pkgbase.Name}/#integrations", status_code=HTTPStatus.SEE_OTHER
        )

    with db.begin():
        if repology_check == enable_str:
            pkgbase.RepologyCheck = 1
        else:
            pkgbase.RepologyCheck = 0

    return RedirectResponse(
        f"/pkgbase/{pkgbase.Name}/#integrations", status_code=HTTPStatus.SEE_OTHER
    )


# Git routes.
def get_git_file(filename, branch_name):
    # Get the needed git information.
    repo = pygit2.Repository("/aurweb/aur.git/")

    # Return an error if we couldn't find the branch.
    try:
        repo.revparse_single(branch_name)
    except KeyError:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    branch = repo.revparse_single(branch_name)

    # Get the requested file.
    requested_file = None

    for tree_file in branch.tree:
        if tree_file.name == filename:
            requested_file = tree_file
            break

    # If we couldn't find the file, return an error.
    if requested_file is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    return requested_file


@router.get("/pkgbase/{name}/git")
async def git_info(request: Request, name: str):
    pkg = get_pkg_or_base(name, Package)
    pkgbase = pkg.PackageBase
    context = pkgbaseutil.make_context(request, pkgbase)

    # Get the needed git information.
    repo = pygit2.Repository("/aurweb/aur.git/")

    # Return an error if we couldn't find the branch.
    try:
        repo.revparse_single(name) is not None
    except KeyError:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    branch = repo.revparse_single(name)
    commit = repo.revparse_single(branch.hex)

    # Get the number of commits in the last week, month, and year.
    time = get_current_time()
    day_seconds = 86400  # Number of seconds in a year.
    one_week_back = time - (day_seconds * 7)
    one_month_back = time - (day_seconds * 31)
    one_year_back = time - (day_seconds * 365)

    past_week_commits = 0
    past_month_commits = 0
    past_year_commits = 0
    commits = []
    committers = {}

    for i in repo.walk(branch.hex):
        commits += [i]

        if i.author.name not in committers:
            committers[i.author.name] = 1
        else:
            committers[i.author.name] += 1

        if i.commit_time >= one_week_back:
            past_week_commits += 1

        if i.commit_time >= one_month_back:
            past_month_commits += 1

        if i.commit_time >= one_year_back:
            past_year_commits += 1

    # Sort the committers list by number of commits.
    committers = dict(sorted(committers.items(), key=lambda item: item[0]))

    # Get the tree for the latest commit.
    tree = [file.name for file in branch.tree]

    context["pkg"] = pkg
    context["pkgbase"] = pkgbase
    context["commit"] = commit
    context["files"] = [file.name for file in commit.tree]
    context["past_week_commits"] = past_week_commits
    context["past_month_commits"] = past_month_commits
    context["past_year_commits"] = past_year_commits
    context["commits"] = commits
    context["committers"] = committers
    context["tree"] = tree

    return render_template(request, "pkgbase/git.html", context)


@router.get("/pkgbase/{name}/git/tree/{file}")
async def git_tree(request: Request, name: str, file: str):
    pkg = get_pkg_or_base(name, Package)
    pkgbase = pkg.PackageBase
    context = pkgbaseutil.make_context(request, pkgbase)

    file_data = get_git_file(file, name)
    context["pkg"] = pkg
    context["pkgbase"] = pkgbase
    context["file"] = file
    context["file_data"] = file_data.data.decode()

    return render_template(request, "pkgbase/git/tree.html", context)


@router.get("/pkgbase/{name}/git/raw/{file}")
async def git_raw(request: Request, name: str, file: str):
    file_data = get_git_file(file, name)
    return Response(content=file_data.data.decode())


@router.get("/pkgbase/{name}/git/commit/{commit_hash}")
async def git_commit(request: Request, name: str, commit_hash: str):
    pkg = get_pkg_or_base(name, Package)
    pkgbase = pkg.PackageBase
    context = pkgbaseutil.make_context(request, pkgbase)

    # Get the needed git information.
    repo = pygit2.Repository("/aurweb/aur.git/")

    # Return an error if we couldn't find the branch.
    try:
        repo.revparse_single(name) is not None
    except KeyError:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    branch = repo.revparse_single(name)

    # If the user requested 'latest' as the commit, redirect to the last commit.
    if commit_hash == "latest":
        return RedirectResponse(
            f"/pkgbase/{pkgbase.Name}/git/commit/{branch.id.hex}",
            status_code=int(HTTPStatus.TEMPORARY_REDIRECT),
        )

    # Scan the branch for the requested commit.
    requested_commit = None

    for commit in repo.walk(branch.id):
        if commit.id.hex == commit_hash:
            requested_commit = commit

    # If we couldn't find the requested commit, return an error.
    if requested_commit is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    # Get the diff between the parent commit and the requested one.
    try:
        diff = repo.diff(
            requested_commit.parents[0].id.hex, requested_commit.id.hex
        ).patch
    # If this is the first commit, there will be no parent commit.
    except IndexError:
        diff = "No diff found."

    context["pkg"] = pkg
    context["pkgbase"] = pkgbase
    context["requested_commit"] = requested_commit
    context["commit_hash"] = requested_commit.id.hex
    context["diff"] = diff

    return render_template(request, "pkgbase/git/commit.html", context)
