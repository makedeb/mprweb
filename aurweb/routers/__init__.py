"""
API routers for FastAPI.

See https://fastapi.tiangolo.com/tutorial/bigger-applications/
"""
from . import (
    accounts,
    api,
    auth,
    html,
    packages,
    pkgbase,
    requests,
    rpc,
    rss,
    trusted_user,
)

"""
aurweb application routes. This constant can be any iterable
and each element must have a .router attribute which points
to a fastapi.APIRouter.
"""
APP_ROUTES = [
    accounts,
    api,
    auth,
    html,
    packages,
    pkgbase,
    requests,
    trusted_user,
    rss,
    rpc,
]

# Hack to support global 'safe-directory' directives in FastAPI code. See
# 'docker/scripts/run-fastapi.sh' and
# https://github.com/libgit2/pygit2/issues/1156.
import pygit2  # noqa: E402

pygit2.option(pygit2.GIT_OPT_SET_OWNER_VALIDATION, 0)
del pygit2
