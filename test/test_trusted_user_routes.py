import re
from http import HTTPStatus
from typing import Tuple

import pytest
from fastapi.testclient import TestClient

from aurweb import config, db, filters, time
from aurweb.models.account_type import AccountType
from aurweb.models.tu_voteinfo import TUVoteInfo
from aurweb.models.user import User
from aurweb.testing.requests import Request

DATETIME_REGEX = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
PARTICIPATION_REGEX = r"^1?[0-9]{2}[%]$"  # 0% - 100%


def get_table(root, class_name):
    table = root.xpath(f'//table[contains(@class, "{class_name}")]')[0]
    return table


def get_table_rows(table):
    tbody = table.xpath("./tbody")[0]
    return tbody.xpath("./tr")


def get_pkglist_directions(table):
    stats = table.getparent().xpath("./div[@class='pkglist-stats']")[0]
    nav = stats.xpath("./p[@class='pkglist-nav']")[0]
    return nav.xpath("./a")


def get_a(node):
    return node.xpath("./a")[0].text.strip()


def get_span(node):
    return node.xpath("./span")[0].text.strip()


def assert_current_vote_html(row, expected):
    columns = row.xpath("./td")
    proposal, start, end, user, voted = columns
    p, s, e, u, v = expected  # Column expectations.
    assert re.match(p, get_a(proposal)) is not None
    assert re.match(s, start.text) is not None
    assert re.match(e, end.text) is not None
    assert re.match(u, get_a(user)) is not None
    assert re.match(v, get_span(voted)) is not None


def assert_past_vote_html(row, expected):
    columns = row.xpath("./td")
    proposal, start, end, user, yes, no, voted = columns  # Real columns.
    p, s, e, u, y, n, v = expected  # Column expectations.
    assert re.match(p, get_a(proposal)) is not None
    assert re.match(s, start.text) is not None
    assert re.match(e, end.text) is not None
    assert re.match(u, get_a(user)) is not None
    assert re.match(y, yes.text) is not None
    assert re.match(n, no.text) is not None
    assert re.match(v, get_span(voted)) is not None


@pytest.fixture(autouse=True)
def setup(db_test):
    return


@pytest.fixture
def client():
    from aurweb.asgi import app

    yield TestClient(app=app)


@pytest.fixture
def tu_user():
    tu_type = db.query(AccountType, AccountType.AccountType == "Trusted User").first()
    with db.begin():
        tu_user = db.create(
            User,
            Username="test_tu",
            Email="test_tu@example.org",
            RealName="Test TU",
            Passwd="testPassword",
            AccountType=tu_type,
        )
    yield tu_user


@pytest.fixture
def user():
    user_type = db.query(AccountType, AccountType.AccountType == "User").first()
    with db.begin():
        user = db.create(
            User,
            Username="test",
            Email="test@example.org",
            RealName="Test User",
            Passwd="testPassword",
            AccountType=user_type,
        )
    yield user


@pytest.fixture
def proposal(user, tu_user):
    ts = time.utcnow()
    agenda = "Test proposal."
    start = ts - 5
    end = ts + 1000

    with db.begin():
        voteinfo = db.create(
            TUVoteInfo,
            Agenda=agenda,
            Quorum=0.0,
            User=user.Username,
            Submitter=tu_user,
            Submitted=start,
            End=end,
        )
    yield (tu_user, user, voteinfo)


def test_tu_index_guest(client):
    headers = {"referer": config.get("options", "aur_location") + "/tu"}
    with client as request:
        response = request.get("/tu", allow_redirects=False, headers=headers)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)

    params = filters.urlencode({"next": "/tu"})
    assert response.headers.get("location") == f"/login?{params}"


def test_tu_index_unauthorized(client: TestClient, user: User):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        # Login as a normal user, not a TU.
        response = request.get("/tu", cookies=cookies, allow_redirects=False)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
    assert response.headers.get("location") == "/"


def test_tu_proposal_not_found(client, tu_user):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        response = request.get("/tu", params={"id": 1}, cookies=cookies)
    assert response.status_code == int(HTTPStatus.NOT_FOUND)


def test_tu_proposal_unauthorized(
    client: TestClient, user: User, proposal: Tuple[User, User, TUVoteInfo]
):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    endpoint = f"/tu/{proposal[2].ID}"
    with client as request:
        response = request.get(endpoint, cookies=cookies, allow_redirects=False)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
    assert response.headers.get("location") == "/tu"

    with client as request:
        response = request.post(
            endpoint, cookies=cookies, data={"decision": False}, allow_redirects=False
        )
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
    assert response.headers.get("location") == "/tu"


def test_tu_proposal_vote_not_found(client, tu_user):
    """Test POST request to a missing vote."""
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        data = {"decision": "Yes"}
        response = request.post(
            "/tu/1", cookies=cookies, data=data, allow_redirects=False
        )
    assert response.status_code == int(HTTPStatus.NOT_FOUND)


def test_tu_proposal_vote_invalid_decision(client, proposal):
    tu_user, user, voteinfo = proposal

    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        data = {"decision": "EVIL"}
        response = request.post(f"/tu/{voteinfo.ID}", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.BAD_REQUEST)
    assert response.text == "Invalid 'decision' value."


def test_tu_addvote(client: TestClient, tu_user: User):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        response = request.get("/addvote", cookies=cookies)
    assert response.status_code == int(HTTPStatus.OK)


def test_tu_addvote_unauthorized(
    client: TestClient, user: User, proposal: Tuple[User, User, TUVoteInfo]
):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        response = request.get("/addvote", cookies=cookies, allow_redirects=False)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
    assert response.headers.get("location") == "/tu"

    with client as request:
        response = request.post("/addvote", cookies=cookies, allow_redirects=False)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
    assert response.headers.get("location") == "/tu"


def test_tu_addvote_post(client: TestClient, tu_user: User, user: User):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}

    data = {"user": user.Username, "type": "add_tu", "agenda": "Blah"}

    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)

    voteinfo = db.query(TUVoteInfo, TUVoteInfo.Agenda == "Blah").first()
    assert voteinfo is not None


def test_tu_addvote_post_cant_duplicate_username(
    client: TestClient, tu_user: User, user: User
):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}

    data = {"user": user.Username, "type": "add_tu", "agenda": "Blah"}

    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)

    voteinfo = db.query(TUVoteInfo, TUVoteInfo.Agenda == "Blah").first()
    assert voteinfo is not None

    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.BAD_REQUEST)


def test_tu_addvote_post_invalid_username(client: TestClient, tu_user: User):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    data = {"user": "fakeusername"}
    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.NOT_FOUND)


def test_tu_addvote_post_invalid_type(client: TestClient, tu_user: User, user: User):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    data = {"user": user.Username}
    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.BAD_REQUEST)


def test_tu_addvote_post_invalid_agenda(client: TestClient, tu_user: User, user: User):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    data = {"user": user.Username, "type": "add_tu"}
    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.BAD_REQUEST)


def test_tu_addvote_post_bylaws(client: TestClient, tu_user: User):
    # Bylaws votes do not need a user specified.
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    data = {"type": "bylaws", "agenda": "Blah blah!"}
    with client as request:
        response = request.post("/addvote", cookies=cookies, data=data)
    assert response.status_code == int(HTTPStatus.SEE_OTHER)
