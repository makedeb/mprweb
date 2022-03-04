from http import HTTPStatus
from typing import List

import pytest
from fastapi.testclient import TestClient

from aurweb import asgi, db, time
from aurweb.models.account_type import USER_ID, AccountType
from aurweb.models.dependency_type import DependencyType
from aurweb.models.official_provider import OfficialProvider
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.package_comment import PackageComment
from aurweb.models.package_dependency import PackageDependency
from aurweb.models.package_relation import PackageRelation
from aurweb.models.package_request import PackageRequest
from aurweb.models.relation_type import PROVIDES_ID, RelationType
from aurweb.models.request_type import DELETION_ID
from aurweb.models.user import User
from aurweb.testing.requests import Request


def package_endpoint(package: Package) -> str:
    return f"/packages/{package.Name}"


def create_package(pkgname: str, maintainer: User) -> Package:
    pkgbase = db.create(PackageBase, Name=pkgname, Maintainer=maintainer)
    return db.create(Package, Name=pkgbase.Name, PackageBase=pkgbase)


def create_package_dep(
    package: Package, depname: str, dep_type_name: str = "depends"
) -> PackageDependency:
    dep_type = db.query(DependencyType, DependencyType.Name == dep_type_name).first()
    return db.create(
        PackageDependency, DependencyType=dep_type, Package=package, DepName=depname
    )


def create_package_rel(package: Package, relname: str) -> PackageRelation:
    rel_type = db.query(RelationType, RelationType.ID == PROVIDES_ID).first()
    return db.create(
        PackageRelation, RelationType=rel_type, Package=package, RelName=relname
    )


@pytest.fixture(autouse=True)
def setup(db_test):
    return


@pytest.fixture
def client() -> TestClient:
    """Yield a FastAPI TestClient."""
    yield TestClient(app=asgi.app)


def create_user(username: str) -> User:
    with db.begin():
        user = db.create(
            User,
            Username=username,
            Email=f"{username}@example.org",
            Passwd="testPassword",
            AccountTypeID=USER_ID,
        )
    return user


@pytest.fixture
def user() -> User:
    """Yield a user."""
    user = create_user("test")
    yield user


@pytest.fixture
def maintainer() -> User:
    """Yield a specific User used to maintain packages."""
    account_type = db.query(AccountType, AccountType.ID == USER_ID).first()
    with db.begin():
        maintainer = db.create(
            User,
            Username="test_maintainer",
            Email="test_maintainer@example.org",
            Passwd="testPassword",
            AccountType=account_type,
        )
    yield maintainer


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
def package(maintainer: User) -> Package:
    """Yield a Package created by user."""
    now = time.utcnow()
    with db.begin():
        pkgbase = db.create(
            PackageBase,
            Name="test-package",
            Maintainer=maintainer,
            Packager=maintainer,
            Submitter=maintainer,
            ModifiedTS=now,
        )
        package = db.create(Package, PackageBase=pkgbase, Name=pkgbase.Name)
    yield package


@pytest.fixture
def pkgbase(package: Package) -> PackageBase:
    yield package.PackageBase


@pytest.fixture
def target(maintainer: User) -> PackageBase:
    """Merge target."""
    now = time.utcnow()
    with db.begin():
        pkgbase = db.create(
            PackageBase,
            Name="target-package",
            Maintainer=maintainer,
            Packager=maintainer,
            Submitter=maintainer,
            ModifiedTS=now,
        )
        db.create(Package, PackageBase=pkgbase, Name=pkgbase.Name)
    yield pkgbase


@pytest.fixture
def pkgreq(user: User, pkgbase: PackageBase) -> PackageRequest:
    """Yield a PackageRequest related to `pkgbase`."""
    with db.begin():
        pkgreq = db.create(
            PackageRequest,
            ReqTypeID=DELETION_ID,
            User=user,
            PackageBase=pkgbase,
            PackageBaseName=pkgbase.Name,
            Comments=f"Deletion request for {pkgbase.Name}",
            ClosureComment=str(),
        )
    yield pkgreq


@pytest.fixture
def comment(user: User, package: Package) -> PackageComment:
    pkgbase = package.PackageBase
    now = time.utcnow()
    with db.begin():
        comment = db.create(
            PackageComment,
            User=user,
            PackageBase=pkgbase,
            Comments="Test comment.",
            RenderedComment=str(),
            CommentTS=now,
        )
    yield comment


@pytest.fixture
def packages(maintainer: User) -> List[Package]:
    """Yield 55 packages named pkg_0 .. pkg_54."""
    packages_ = []
    now = time.utcnow()
    with db.begin():
        for i in range(55):
            pkgbase = db.create(
                PackageBase,
                Name=f"pkg_{i}",
                Maintainer=maintainer,
                Packager=maintainer,
                Submitter=maintainer,
                ModifiedTS=now,
            )
            package = db.create(Package, PackageBase=pkgbase, Name=f"pkg_{i}")
            packages_.append(package)

    yield packages_


def test_package_not_found(client: TestClient):
    with client as request:
        resp = request.get("/packages/not_found")
    assert resp.status_code == int(HTTPStatus.NOT_FOUND)


def test_package_official_not_found(client: TestClient, package: Package):
    """When a Package has a matching OfficialProvider record, it is not
    hosted on AUR, but in the official repositories. Getting a package
    with this kind of record should return a status code 404."""
    with db.begin():
        db.create(
            OfficialProvider, Name=package.Name, Repo="core", Provides=package.Name
        )

    with client as request:
        resp = request.get(package_endpoint(package))
    assert resp.status_code == int(HTTPStatus.NOT_FOUND)


def test_package_authenticated_maintainer(
    client: TestClient, maintainer: User, package: Package
):
    cookies = {"AURSID": maintainer.login(Request(), "testPassword")}
    with client as request:
        resp = request.get(package_endpoint(package), cookies=cookies)
    assert resp.status_code == int(HTTPStatus.OK)

    expected = [
        "View PKGBUILD",
        "View Changes",
        "Search ArchWiki",
        "Flag package out-of-date",
        "Vote for this package",
        "Enable notifications",
        "Manage Co-Maintainers",
        "Submit Request",
        "Disown Package",
    ]
    for expected_text in expected:
        assert expected_text in resp.text


def test_package_authenticated_tu(client: TestClient, tu_user: User, package: Package):
    cookies = {"AURSID": tu_user.login(Request(), "testPassword")}
    with client as request:
        resp = request.get(package_endpoint(package), cookies=cookies)
    assert resp.status_code == int(HTTPStatus.OK)

    expected = [
        "View PKGBUILD",
        "View Changes",
        "Search ArchWiki",
        "Flag package out-of-date",
        "Vote for this package",
        "Enable notifications",
        "Manage Co-Maintainers",
        "Submit Request",
        "Delete Package",
        "Merge Package",
        "Disown Package",
    ]
    for expected_text in expected:
        assert expected_text in resp.text


def test_packages_post_unknown_action(client: TestClient, user: User, package: Package):

    cookies = {"AURSID": user.login(Request(), "testPassword")}
    with client as request:
        resp = request.post(
            "/packages",
            data={"action": "unknown"},
            cookies=cookies,
            allow_redirects=False,
        )
    assert resp.status_code == int(HTTPStatus.BAD_REQUEST)


def test_account_comments_unauthorized(client: TestClient, user: User):
    """This test may seem out of place, but it requires packages,
    so its being included in the packages routes test suite to
    leverage existing fixtures."""
    endpoint = f"/account/{user.Username}/comments"
    with client as request:
        resp = request.get(endpoint, allow_redirects=False)
    assert resp.status_code == int(HTTPStatus.SEE_OTHER)
    assert resp.headers.get("location").startswith("/login")
