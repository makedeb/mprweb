import re

from http import HTTPStatus
from logging import DEBUG
from typing import List

import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from aurweb import asgi, config, db, defaults, time
from aurweb.models import Package, PackageBase, PackageRequest, User
from aurweb.models.account_type import TRUSTED_USER_ID, USER_ID
from aurweb.models.package_notification import PackageNotification
from aurweb.models.package_request import ACCEPTED_ID, PENDING_ID, REJECTED_ID
from aurweb.models.request_type import DELETION_ID, MERGE_ID, ORPHAN_ID
from aurweb.packages.requests import ClosureFactory
from aurweb.requests.util import get_pkgreq_by_id
from aurweb.testing.email import Email
from aurweb.testing.html import get_errors, parse_root
from aurweb.testing.requests import Request


@pytest.fixture(autouse=True)
def setup(db_test) -> None:
    """ Setup the database. """
    return


@pytest.fixture
def client() -> TestClient:
    """ Yield a TestClient. """
    yield TestClient(app=asgi.app)


def create_user(username: str, email: str) -> User:
    """
    Create a user based on `username` and `email`.

    :param username: User.Username
    :param email: User.Email
    :return: User instance
    """
    with db.begin():
        user = db.create(User, Username=username, Email=email,
                         Passwd="testPassword", AccountTypeID=USER_ID)
    return user


@pytest.fixture
def user() -> User:
    """ Yield a User instance. """
    user = create_user("test", "test@example.org")
    yield user


@pytest.fixture
def auser(user: User) -> User:
    """ Yield an authenticated User instance. """
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    user.cookies = cookies
    yield user


@pytest.fixture
def user2() -> User:
    """ Yield a secondary non-maintainer User instance. """
    user = create_user("test2", "test2@example.org")
    yield user


@pytest.fixture
def auser2(user2: User) -> User:
    """ Yield an authenticated secondary non-maintainer User instance. """
    cookies = {"AURSID": user2.login(Request(), "testPassword")}
    user2.cookies = cookies
    yield user2


@pytest.fixture
def maintainer() -> User:
    """ Yield a specific User used to maintain packages. """
    with db.begin():
        maintainer = db.create(User, Username="test_maintainer",
                               Email="test_maintainer@example.org",
                               Passwd="testPassword",
                               AccountTypeID=USER_ID)
    yield maintainer


@pytest.fixture
def packages(maintainer: User) -> List[Package]:
    """ Yield 55 packages named pkg_0 .. pkg_54. """
    packages_ = []
    now = time.utcnow()
    with db.begin():
        for i in range(55):
            pkgbase = db.create(PackageBase,
                                Name=f"pkg_{i}",
                                Maintainer=maintainer,
                                Packager=maintainer,
                                Submitter=maintainer,
                                ModifiedTS=now)
            package = db.create(Package,
                                PackageBase=pkgbase,
                                Name=f"pkg_{i}")
            packages_.append(package)

    yield packages_


@pytest.fixture
def requests(user: User, packages: List[Package]) -> List[PackageRequest]:
    pkgreqs = []
    with db.begin():
        for i in range(55):
            pkgreq = db.create(PackageRequest,
                               ReqTypeID=DELETION_ID,
                               User=user,
                               PackageBase=packages[i].PackageBase,
                               PackageBaseName=packages[i].Name,
                               Comments=f"Deletion request for pkg_{i}",
                               ClosureComment=str())
            pkgreqs.append(pkgreq)
    yield pkgreqs


@pytest.fixture
def tu_user() -> User:
    """ Yield an authenticated Trusted User instance. """
    user = create_user("test_tu", "test_tu@example.org")
    with db.begin():
        user.AccountTypeID = TRUSTED_USER_ID
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    user.cookies = cookies
    yield user


def create_pkgbase(user: User, name: str) -> PackageBase:
    """
    Create a package base based on `user` and `name`.

    This function also creates a matching Package record.

    :param user: User instance
    :param name: PackageBase.Name
    :return: PackageBase instance
    """
    now = time.utcnow()
    with db.begin():
        pkgbase = db.create(PackageBase, Name=name,
                            Maintainer=user, Packager=user,
                            SubmittedTS=now, ModifiedTS=now)
        db.create(Package, Name=pkgbase.Name, PackageBase=pkgbase)
    return pkgbase


@pytest.fixture
def pkgbase(user: User) -> PackageBase:
    """ Yield a package base. """
    pkgbase = create_pkgbase(user, "test-package")
    yield pkgbase


@pytest.fixture
def target(user: User) -> PackageBase:
    """ Yield a merge target (package base). """
    with db.begin():
        target = db.create(PackageBase, Name="target-package",
                           Maintainer=user, Packager=user)
    yield target


def create_request(reqtype_id: int, user: User, pkgbase: PackageBase,
                   comments: str) -> PackageRequest:
    """
    Create a package request based on `reqtype_id`, `user`,
    `pkgbase` and `comments`.

    :param reqtype_id: RequestType.ID
    :param user: User instance
    :param pkgbase: PackageBase instance
    :param comments: PackageRequest.Comments
    :return: PackageRequest instance
    """
    now = time.utcnow()
    with db.begin():
        pkgreq = db.create(PackageRequest, ReqTypeID=reqtype_id,
                           User=user, PackageBase=pkgbase,
                           PackageBaseName=pkgbase.Name,
                           RequestTS=now,
                           Comments=comments,
                           ClosureComment=str())
    return pkgreq


@pytest.fixture
def pkgreq(user: User, pkgbase: PackageBase):
    """ Yield a package request. """
    pkgreq = create_request(DELETION_ID, user, pkgbase, "Test request.")
    yield pkgreq


def create_notification(user: User, pkgbase: PackageBase):
    """ Create a notification for a `user` on `pkgbase`. """
    with db.begin():
        notif = db.create(PackageNotification, User=user, PackageBase=pkgbase)
    return notif


def test_request(client: TestClient, auser: User, pkgbase: PackageBase):
    """ Test the standard pkgbase request route GET method. """
    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    with client as request:
        resp = request.get(endpoint, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.OK)


def test_request_post_deletion(client: TestClient, auser2: User,
                               pkgbase: PackageBase):
    """ Test the POST route for creating a deletion request works. """
    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {"comments": "Test request.", "type": "deletion"}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser2.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    pkgreq = pkgbase.requests.first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == DELETION_ID
    assert pkgreq.Status == PENDING_ID

    # A RequestOpenNotification should've been sent out.
    assert Email.count() == 1
    email = Email(1)
    expr = r"^\[PRQ#%d\] Deletion Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))


def test_request_post_deletion_as_maintainer(client: TestClient, auser: User,
                                             pkgbase: PackageBase):
    """ Test the POST route for creating a deletion request as maint works. """
    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {"comments": "Test request.", "type": "deletion"}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    # Check the pkgreq record got created and accepted.
    pkgreq = db.query(PackageRequest).first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == DELETION_ID
    assert pkgreq.Status == ACCEPTED_ID

    # Should've gotten two emails.
    assert Email.count() == 2

    # A RequestOpenNotification should've been sent out.
    email = Email(1)
    expr = r"^\[PRQ#%d\] Deletion Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))

    # Check the content of the close notification.
    email = Email(2)
    expr = r"^\[PRQ#%d\] Deletion Request for [^ ]+ Accepted$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))


def test_request_post_deletion_autoaccept(client: TestClient, auser: User,
                                          pkgbase: PackageBase,
                                          caplog: pytest.LogCaptureFixture):
    """ Test the request route for deletion as maintainer. """
    caplog.set_level(DEBUG)

    now = time.utcnow()
    auto_delete_age = config.getint("options", "auto_delete_age")
    with db.begin():
        pkgbase.ModifiedTS = now - auto_delete_age + 100

    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {"comments": "Test request.", "type": "deletion"}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    pkgreq = db.query(PackageRequest).filter(
        PackageRequest.PackageBaseName == pkgbase.Name
    ).first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == DELETION_ID
    assert pkgreq.Status == ACCEPTED_ID

    # A RequestOpenNotification should've been sent out.
    assert Email.count() == 2
    Email.dump()

    # Check the content of the open notification.
    email = Email(1)
    expr = r"^\[PRQ#%d\] Deletion Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))

    # Check the content of the close notification.
    email = Email(2)
    expr = r"^\[PRQ#%d\] Deletion Request for [^ ]+ Accepted$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))

    # Check logs.
    expr = r"New request #\d+ is marked for auto-deletion."
    assert re.search(expr, caplog.text)


def test_request_post_merge(client: TestClient, auser: User,
                            pkgbase: PackageBase, target: PackageBase):
    """ Test the request route for merge as maintainer. """
    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {
        "type": "merge",
        "merge_into": target.Name,
        "comments": "Test request.",
    }
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    pkgreq = pkgbase.requests.first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == MERGE_ID
    assert pkgreq.Status == PENDING_ID
    assert pkgreq.MergeBaseName == target.Name

    # A RequestOpenNotification should've been sent out.
    assert Email.count() == 1
    email = Email(1)
    expr = r"^\[PRQ#%d\] Merge Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))


def test_request_post_orphan(client: TestClient, auser: User,
                             pkgbase: PackageBase):
    """ Test the POST route for creating an orphan request works. """
    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {
        "type": "orphan",
        "comments": "Test request.",
    }
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    pkgreq = pkgbase.requests.first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == ORPHAN_ID
    assert pkgreq.Status == PENDING_ID

    # A RequestOpenNotification should've been sent out.
    assert Email.count() == 1

    email = Email(1)
    expr = r"^\[PRQ#%d\] Orphan Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))


def test_deletion_request(client: TestClient, user: User, tu_user: User,
                          pkgbase: PackageBase, pkgreq: PackageRequest):
    """ Test deleting a package with a preexisting request. """
    # `pkgreq`.ReqTypeID is already DELETION_ID.
    create_request(DELETION_ID, user, pkgbase, "Other request.")

    # Create a notification record for another user. They should then
    # also receive a DeleteNotification.
    user2 = create_user("test2", "test2@example.org")
    create_notification(user2, pkgbase)

    endpoint = f"/pkgbase/{pkgbase.Name}/delete"
    comments = "Test closure."
    data = {"comments": comments, "confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == "/packages"

    # Ensure that `pkgreq`.ClosureComment was left alone when specified.
    assert pkgreq.ClosureComment == comments

    # We should've gotten three emails. Two accepted requests and
    # a DeleteNotification.
    assert Email.count() == 3

    # Both requests should have gotten accepted and had a notification
    # sent out for them.
    for i in range(Email.count() - 1):
        email = Email(i + 1).parse()
        expr = r"^\[PRQ#\d+\] Deletion Request for [^ ]+ Accepted$"
        assert re.match(expr, email.headers.get("Subject"))

    # We should've also had a DeleteNotification sent out.
    email = Email(3).parse()
    subject = r"^MPR Package deleted: [^ ]+$"
    assert re.match(subject, email.headers.get("Subject"))
    body = r"%s [1] deleted %s [2]." % (tu_user.Username, pkgbase.Name)
    assert body in email.body


def test_deletion_autorequest(client: TestClient, tu_user: User,
                              pkgbase: PackageBase):
    """ Test deleting a package without a request. """
    # `pkgreq`.ReqTypeID is already DELETION_ID.
    endpoint = f"/pkgbase/{pkgbase.Name}/delete"
    data = {"confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    assert resp.headers.get("location") == "/packages"
    assert Email.count() == 1

    email = Email(1).parse()
    subject = r"^\[PRQ#\d+\] Deletion Request for [^ ]+ Accepted$"
    assert re.match(subject, email.headers.get("Subject"))
    assert "[Autogenerated]" in email.body


def test_merge_request(client: TestClient, user: User, tu_user: User,
                       pkgbase: PackageBase, target: PackageBase,
                       pkgreq: PackageRequest):
    """ Test merging a package with a pre - existing request. """
    with db.begin():
        pkgreq.ReqTypeID = MERGE_ID
        pkgreq.MergeBaseName = target.Name

    other_target = create_pkgbase(user, "other-target")
    other_request = create_request(MERGE_ID, user, pkgbase, "Other request.")
    other_target2 = create_pkgbase(user, "other-target2")
    other_request2 = create_request(MERGE_ID, user, pkgbase, "Other request2.")
    with db.begin():
        other_request.MergeBaseName = other_target.Name
        other_request2.MergeBaseName = other_target2.Name

    # `pkgreq`.ReqTypeID is already DELETION_ID.
    endpoint = f"/pkgbase/{pkgbase.Name}/merge"
    comments = "Test merge closure."
    data = {"into": target.Name, "comments": comments, "confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == f"/pkgbase/{target.Name}"

    # Ensure that `pkgreq`.ClosureComment was left alone when specified.
    assert pkgreq.ClosureComment == comments

    # We should've gotten 3 emails: an accepting and two rejections.
    assert Email.count() == 3

    # Assert specific IDs match up in the subjects.
    accepted = Email(1).parse()
    subj = r"^\[PRQ#%d\] Merge Request for [^ ]+ Accepted$" % pkgreq.ID
    assert re.match(subj, accepted.headers.get("Subject"))

    # In the accepted case, we already supplied a closure comment,
    # which stops one from being autogenerated by the algorithm.
    assert "[Autogenerated]" not in accepted.body

    # Test rejection emails, which do have autogenerated closures.
    rejected = Email(2).parse()
    subj = r"^\[PRQ#%d\] Merge Request for [^ ]+ Rejected$" % other_request.ID
    assert re.match(subj, rejected.headers.get("Subject"))
    assert "[Autogenerated]" in rejected.body

    rejected = Email(3).parse()
    subj = r"^\[PRQ#%d\] Merge Request for [^ ]+ Rejected$" % other_request2.ID
    assert re.match(subj, rejected.headers.get("Subject"))
    assert "[Autogenerated]" in rejected.body


def test_merge_autorequest(client: TestClient, user: User, tu_user: User,
                           pkgbase: PackageBase, target: PackageBase):
    """ Test merging a package without a request. """
    with db.begin():
        pkgreq.ReqTypeID = MERGE_ID
        pkgreq.MergeBaseName = target.Name

    # `pkgreq`.ReqTypeID is already DELETION_ID.
    endpoint = f"/pkgbase/{pkgbase.Name}/merge"
    data = {"into": target.Name, "confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == f"/pkgbase/{target.Name}"

    # Should've gotten one email; an [Autogenerated] one.
    assert Email.count() == 1

    # Test accepted merge request notification.
    email = Email(1).parse()
    subj = r"^\[PRQ#\d+\] Merge Request for [^ ]+ Accepted$"
    assert re.match(subj, email.headers.get("Subject"))
    assert "[Autogenerated]" in email.body


def test_orphan_request(client: TestClient, user: User, tu_user: User,
                        pkgbase: PackageBase, pkgreq: PackageRequest):
    """ Test the standard orphan request route. """
    idle_time = config.getint("options", "request_idle_time")
    now = time.utcnow()
    with db.begin():
        pkgreq.ReqTypeID = ORPHAN_ID
        # Set the request time so it's seen as due (idle_time has passed).
        pkgreq.RequestTS = now - idle_time - 10

    endpoint = f"/pkgbase/{pkgbase.Name}/disown"
    comments = "Test orphan closure."
    data = {"comments": comments, "confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == f"/pkgbase/{pkgbase.Name}"

    # Ensure that `pkgreq`.ClosureComment was left alone when specified.
    assert pkgreq.ClosureComment == comments

    # Check the email we expect.
    assert Email.count() == 1
    email = Email(1).parse()
    subj = r"^\[PRQ#%d\] Orphan Request for [^ ]+ Accepted$" % pkgreq.ID
    assert re.match(subj, email.headers.get("Subject"))


def test_request_post_orphan_autogenerated_closure(client: TestClient,
                                                   tu_user: User,
                                                   pkgbase: PackageBase,
                                                   pkgreq: PackageRequest):
    idle_time = config.getint("options", "request_idle_time")
    now = time.utcnow()
    with db.begin():
        pkgreq.ReqTypeID = ORPHAN_ID
        # Set the request time so it's seen as due (idle_time has passed).
        pkgreq.RequestTS = now - idle_time - 10

    endpoint = f"/pkgbase/{pkgbase.Name}/disown"
    data = {"confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == f"/pkgbase/{pkgbase.Name}"

    assert Email.count() == 1
    email = Email(1)
    expr = r"^\[PRQ#\d+\] Orphan Request for .+ Accepted$"
    assert re.match(expr, email.headers.get("Subject"))

    expr = r"\[Autogenerated\] Accepted orphan for .+\."
    assert re.search(expr, email.body)


def test_request_post_orphan_autoaccept(client: TestClient, auser: User,
                                        pkgbase: PackageBase,
                                        caplog: pytest.LogCaptureFixture):
    """ Test the standard pkgbase request route GET method. """
    caplog.set_level(DEBUG)
    now = time.utcnow()
    auto_orphan_age = config.getint("options", "auto_orphan_age")
    with db.begin():
        pkgbase.OutOfDateTS = now - auto_orphan_age - 100

    endpoint = f"/pkgbase/{pkgbase.Name}/request"
    data = {
        "type": "orphan",
        "comments": "Test request.",
    }
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    pkgreq = pkgbase.requests.first()
    assert pkgreq is not None
    assert pkgreq.ReqTypeID == ORPHAN_ID

    # A Request(Open|Close)Notification should've been sent out.
    assert Email.count() == 2

    # Check the first email; should be our open request.
    email = Email(1)
    expr = r"^\[PRQ#%d\] Orphan Request for [^ ]+$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))

    # And the second should be the automated closure.
    email = Email(2)
    expr = r"^\[PRQ#%d\] Orphan Request for [^ ]+ Accepted$" % pkgreq.ID
    assert re.match(expr, email.headers.get("Subject"))

    # Check logs.
    expr = r"New request #\d+ is marked for auto-orphan."
    assert re.search(expr, caplog.text)


def test_orphan_as_maintainer(client: TestClient, auser: User,
                              pkgbase: PackageBase):
    endpoint = f"/pkgbase/{pkgbase.Name}/disown"
    data = {"confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=auser.cookies)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == f"/pkgbase/{pkgbase.Name}"

    # As the pkgbase maintainer, disowning the package just ends up
    # either promoting the lowest priority comaintainer or removing
    # the associated maintainer relationship altogether.
    assert pkgbase.Maintainer is None


def test_orphan_without_requests(client: TestClient, tu_user: User,
                                 pkgbase: PackageBase):
    """ Test orphans are automatically accepted past a certain date. """
    endpoint = f"/pkgbase/{pkgbase.Name}/disown"
    data = {"confirm": True}
    with client as request:
        resp = request.post(endpoint, data=data, cookies=tu_user.cookies)
    assert resp.status_code == int(HTTPStatus.BAD_REQUEST)

    errors = get_errors(resp.text)
    expected = r"^No due existing orphan requests to accept for .+\.$"
    assert re.match(expected, errors[0].text.strip())

    assert Email.count() == 0


def test_closure_factory_invalid_reqtype_id():
    """ Test providing an invalid reqtype_id raises NotImplementedError. """
    automated = ClosureFactory()
    match = r"^Unsupported '.+' value\.$"
    with pytest.raises(NotImplementedError, match=match):
        automated.get_closure(666, None, None, None, ACCEPTED_ID)
    with pytest.raises(NotImplementedError, match=match):
        automated.get_closure(666, None, None, None, REJECTED_ID)


def test_pkgreq_by_id_not_found():
    with pytest.raises(HTTPException):
        get_pkgreq_by_id(0)


def test_requests_unauthorized(client: TestClient):
    with client as request:
        resp = request.get("/requests", allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)


def test_requests(client: TestClient,
                  tu_user: User,
                  packages: List[Package],
                  requests: List[PackageRequest]):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        resp = request.get("/requests", params={
            # Pass in url query parameters O, SeB and SB to exercise
            # their paths inside of the pager_nav used in this request.
            "O": 0,  # Page 1
            "SeB": "nd",
            "SB": "n"
        }, cookies=cookies)
    assert resp.status_code == int(HTTPStatus.OK)

    assert "Next ›" in resp.text
    assert "Last »" in resp.text

    root = parse_root(resp.text)
    # We have 55 requests, our defaults.PP is 50, so expect we have 50 rows.
    rows = root.xpath('//table[@class="results"]/tbody/tr')
    assert len(rows) == defaults.PP

    # Request page 2 of the requests page.
    with client as request:
        resp = request.get("/requests", params={
            "O": 50  # Page 2
        }, cookies=cookies)
    assert resp.status_code == int(HTTPStatus.OK)

    assert "‹ Previous" in resp.text
    assert "« First" in resp.text

    root = parse_root(resp.text)
    rows = root.xpath('//table[@class="results"]/tbody/tr')
    assert len(rows) == 5  # There are five records left on the second page.


def test_requests_selfmade(client: TestClient, user: User,
                           requests: List[PackageRequest]):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        resp = request.get("/requests", cookies=cookies)
    assert resp.status_code == int(HTTPStatus.OK)

    # As the user who creates all of the requests, we should see all of them.
    # However, we are not allowed to accept any of them ourselves.
    root = parse_root(resp.text)
    rows = root.xpath('//table[@class="results"]/tbody/tr')
    assert len(rows) == defaults.PP

    # Our first and only link in the last row should be "Close".
    for row in rows:
        last_row = row.xpath('./td')[-1].xpath('./a')[0]
        assert last_row.text.strip() == "Close"


def test_requests_close(client: TestClient, user: User,
                        pkgreq: PackageRequest):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        resp = request.get(f"/requests/{pkgreq.ID}/close", cookies=cookies,
                           allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.OK)


def test_requests_close_unauthorized(client: TestClient, maintainer: User,
                                     pkgreq: PackageRequest):
    cookies = {"AURSID": maintainer.login(Request(), "testPassword")}
    with client as request:
        resp = request.get(f"/requests/{pkgreq.ID}/close", cookies=cookies,
                           allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == "/"


def test_requests_close_post_unauthorized(client: TestClient, maintainer: User,
                                          pkgreq: PackageRequest):
    cookies = {"AURSID": maintainer.login(Request(), "testPassword")}
    with client as request:
        resp = request.post(f"/requests/{pkgreq.ID}/close", data={
            "reason": ACCEPTED_ID
        }, cookies=cookies, allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location") == "/"


def test_requests_close_post(client: TestClient, user: User,
                             pkgreq: PackageRequest):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        resp = request.post(f"/requests/{pkgreq.ID}/close",
                            cookies=cookies, allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    assert pkgreq.Status == REJECTED_ID
    assert pkgreq.Closer == user
    assert pkgreq.ClosureComment == str()


def test_requests_close_post_rejected(client: TestClient, user: User,
                                      pkgreq: PackageRequest):
    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        resp = request.post(f"/requests/{pkgreq.ID}/close",
                            cookies=cookies, allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)

    assert pkgreq.Status == REJECTED_ID
    assert pkgreq.Closer == user
    assert pkgreq.ClosureComment == str()
