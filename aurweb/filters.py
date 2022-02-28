import copy
import math

from datetime import datetime
from typing import Any, Dict
from urllib.parse import quote_plus, urlencode
from zoneinfo import ZoneInfo

import fastapi
import paginate

from jinja2 import pass_context

import aurweb.models

from aurweb import config, l10n
from aurweb.templates import register_filter, register_function


@register_filter("pager_nav")
@pass_context
def pager_nav(context: Dict[str, Any],
              page: int, total: int, prefix: str) -> str:
    page = int(page)  # Make sure this is an int.

    pp = context.get("PP", 50)

    # Setup a local query string dict, optionally passed by caller.
    q = context.get("q", dict())

    search_by = context.get("SeB", None)
    if search_by:
        q["SeB"] = search_by

    sort_by = context.get("SB", None)
    if sort_by:
        q["SB"] = sort_by

    def create_url(page: int):
        nonlocal q
        offset = max(page * pp - pp, 0)
        qs = to_qs(extend_query(q, ["O", offset]))
        return f"{prefix}?{qs}"

    # Use the paginate module to produce our linkage.
    pager = paginate.Page([], page=page + 1,
                          items_per_page=pp,
                          item_count=total,
                          url_maker=create_url)

    return pager.pager(
        link_attr={"class": "page"},
        curpage_attr={"class": "page"},
        separator="&nbsp",
        format="$link_first ~5~ $link_last",
        symbol_first="«",
        symbol_last="»")


@register_function("config_getint")
def config_getint(section: str, key: str) -> int:
    return config.getint(section, key)


@register_function("round")
def do_round(f: float) -> int:
    return round(f)


@register_filter("tr")
@pass_context
def tr(context: Dict[str, Any], value: str):
    """ A translation filter; example: {{ "Hello" | tr("de") }}. """
    _ = l10n.get_translator_for_request(context.get("request"))
    return _(value)


@register_filter("tn")
@pass_context
def tn(context: Dict[str, Any], count: int,
       singular: str, plural: str) -> str:
    """ A singular and plural translation filter.

    Example:
        {{ some_integer | tn("singular %d", "plural %d") }}

    :param context: Response context
    :param count: The number used to decide singular or plural state
    :param singular: The singular translation
    :param plural: The plural translation
    :return: Translated string
    """
    gettext = l10n.get_raw_translator_for_request(context.get("request"))
    return gettext.ngettext(singular, plural, count)


@register_filter("dt")
def timestamp_to_datetime(timestamp: int):
    return datetime.utcfromtimestamp(int(timestamp))


@register_filter("as_timezone")
def as_timezone(dt: datetime, timezone: str):
    return dt.astimezone(tz=ZoneInfo(timezone))


@register_filter("extend_query")
def extend_query(query: Dict[str, Any], *additions) -> Dict[str, Any]:
    """ Add additional key value pairs to query. """
    q = copy.copy(query)
    for k, v in list(additions):
        q[k] = v
    return q


@register_filter("urlencode")
def to_qs(query: Dict[str, Any]) -> str:
    return urlencode(query, doseq=True)


@register_filter("get_vote")
def get_vote(voteinfo, request: fastapi.Request):
    from aurweb.models import TUVote
    return voteinfo.tu_votes.filter(TUVote.User == request.user).first()


@register_filter("number_format")
def number_format(value: float, places: int):
    """ A converter function similar to PHP's number_format. """
    return f"{value:.{places}f}"


@register_filter("account_url")
@pass_context
def account_url(context: Dict[str, Any],
                user: "aurweb.models.user.User") -> str:
    base = aurweb.config.get("options", "aur_location")
    return f"{base}/account/{user.Username}"


@register_filter("quote_plus")
def _quote_plus(*args, **kwargs) -> str:
    return quote_plus(*args, **kwargs)


@register_filter("ceil")
def ceil(*args, **kwargs) -> int:
    return math.ceil(*args, **kwargs)
