import pytest

import aurweb.filters  # noqa: F401
from aurweb import db, time
from aurweb.models import Package, PackageBase, User
from aurweb.models.account_type import USER_ID
from aurweb.models.license import License
from aurweb.models.package_license import PackageLicense
from aurweb.models.package_relation import PackageRelation
from aurweb.templates import register_filter, register_function

GIT_CLONE_URI_ANON = "anon_%s"
GIT_CLONE_URI_PRIV = "priv_%s"


@register_filter("func")
def func():
    pass


@register_function("function")
def function():
    pass


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


def create_pkgrel(package: Package, reltype_id: int, relname: str) -> PackageRelation:
    return db.create(
        PackageRelation, Package=package, RelTypeID=reltype_id, RelName=relname
    )


@pytest.fixture
def user(db_test) -> User:
    user = create_user("test")
    yield user


@pytest.fixture
def pkgbase(user: User) -> PackageBase:
    now = time.utcnow()
    with db.begin():
        pkgbase = db.create(
            PackageBase,
            Name="test-pkg",
            Maintainer=user,
            SubmittedTS=now,
            ModifiedTS=now,
        )
    yield pkgbase


@pytest.fixture
def package(user: User, pkgbase: PackageBase) -> Package:
    with db.begin():
        pkg = db.create(Package, PackageBase=pkgbase, Name=pkgbase.Name)
    yield pkg


def create_license(pkg: Package, license_name: str) -> PackageLicense:
    lic = db.create(License, Name=license_name)
    pkglic = db.create(PackageLicense, License=lic, Package=pkg)
    return pkglic


def test_register_function_exists_key_error():
    """Most instances of register_filter are tested through module
    imports or template renders, so we only test failures here."""
    with pytest.raises(KeyError):

        @register_function("function")
        def some_func():
            pass
