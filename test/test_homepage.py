from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from aurweb import db, time
from aurweb.asgi import app
from aurweb.models.account_type import USER_ID
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.user import User
from aurweb.redis import redis_connection

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup(db_test):
    return


@pytest.fixture
def user():
    with db.begin():
        user = db.create(
            User,
            Username="test",
            Email="test@example.org",
            Passwd="testPassword",
            AccountTypeID=USER_ID,
        )
    yield user


@pytest.fixture
def user2():
    with db.begin():
        user = db.create(
            User,
            Username="test2",
            Email="test2@example.org",
            Passwd="testPassword",
            AccountTypeID=USER_ID,
        )
    yield user


@pytest.fixture
def redis():
    redis = redis_connection()

    def delete_keys():
        # Cleanup keys if they exist.
        for key in (
            "package_count",
            "orphan_count",
            "user_count",
            "trusted_user_count",
            "seven_days_old_added",
            "seven_days_old_updated",
            "year_old_updated",
            "never_updated",
            "package_updates",
        ):
            if redis.get(key) is not None:
                redis.delete(key)

    delete_keys()
    yield redis
    delete_keys()


@pytest.fixture
def package(user: User) -> Package:
    now = time.utcnow()
    with db.begin():
        pkgbase = db.create(
            PackageBase,
            Name="test-pkg",
            Maintainer=user,
            Packager=user,
            SubmittedTS=now,
            ModifiedTS=now,
        )
        pkg = db.create(Package, PackageBase=pkgbase, Name=pkgbase.Name)
    yield pkg


@pytest.fixture
def packages(user):
    """Yield a list of num_packages Package objects maintained by user."""
    num_packages = 50  # Tunable

    # For i..num_packages, create a package named pkg_{i}.
    pkgs = []
    now = time.utcnow()
    with db.begin():
        for i in range(num_packages):
            pkgbase = db.create(
                PackageBase,
                Name=f"pkg_{i}",
                Maintainer=user,
                Packager=user,
                SubmittedTS=now,
                ModifiedTS=now,
            )
            pkg = db.create(Package, PackageBase=pkgbase, Name=pkgbase.Name)
            pkgs.append(pkg)
            now += 1

    yield pkgs


def test_homepage():
    with client as request:
        response = request.get("/")
    assert response.status_code == int(HTTPStatus.OK)
