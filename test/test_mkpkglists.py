import gzip

import orjson
import pytest

from aurweb import config, db, models
from aurweb.scripts import mkpkglists
from aurweb.testing import setup_test_db

archivedir = config.get("mkpkglists", "archivedir")


@pytest.fixture(autouse=True)
def setup(db_test):
    return


def test_mkpkglists():
    setup_test_db(
        "Users", "Packages", "PackageBases", "PackageDepends", "PackageRelations"
    )

    # Setup users.
    with db.begin():
        user = db.create(
            models.User, Username="user", Email="test@example.com", Passwd="1234"
        )

    # Setup package bases.
    with db.begin():
        package_base = db.create(
            models.PackageBase,
            Name="pkgbase",
            MaintainerUID=user.ID,
            PackagerUID=user.ID,
        )

    # Setup packages.
    with db.begin():
        package1 = db.create(
            models.Package, PackageBaseID=package_base.ID, Name="package1"
        )

        package2 = db.create(
            models.Package, PackageBaseID=package_base.ID, Name="package2"
        )

    # Setup dependencies.
    with db.begin():
        db.create(
            models.PackageDependency,
            DepTypeID=models.dependency_type.DEPENDS_ID,
            PackageID=package1.ID,
            DepName="dep1",
        )

        db.create(
            models.PackageDependency,
            DepTypeID=models.dependency_type.DEPENDS_ID,
            PackageID=package1.ID,
            DepName="dep2",
        )

        db.create(
            models.PackageDependency,
            DepTypeID=models.dependency_type.DEPENDS_ID,
            PackageID=package2.ID,
            DepName="dep3",
        )

        db.create(
            models.PackageDependency,
            DepTypeID=models.dependency_type.DEPENDS_ID,
            PackageID=package2.ID,
            DepName="dep4",
            DepArch="amd64",
            DepDist="focal",
        )

    # Run mkpkglists.
    mkpkglists._main()

    # Check 'packages.gz'.
    expected = ["package1", "package2"]

    with open(f"{archivedir}/packages.gz", "br") as file:
        packages = gzip.decompress(file.read()).decode().splitlines()

    assert len(expected) == len(packages)

    for pkg in expected:
        assert pkg in packages

    # Check 'pkgbase.gz'.
    expected = ["pkgbase"]

    with open(f"{archivedir}/pkgbase.gz", "br") as file:
        packages = gzip.decompress(file.read()).decode().splitlines()

    assert len(expected) == len(packages)

    for pkg in expected:
        assert pkg in packages

    # Check 'users.gz'.
    expected = ["user"]

    with open(f"{archivedir}/users.gz", "br") as file:
        users = gzip.decompress(file.read()).decode().splitlines()

    assert len(expected) == len(users)

    for user in expected:
        assert user in users

    # Check 'packages-meta-v1.json.gz'.
    expected_keys = (
        "ID",
        "Name",
        "PackageBaseID",
        "PackageBase",
        "Version",
        "Description",
        "URL",
        "NumVotes",
        "Popularity",
        "OutOfDate",
        "Maintainer",
        "FirstSubmitted",
        "LastModified",
        "URLPath",
    )

    with open(f"{archivedir}/packages-meta-v1.json.gz", "br") as file:
        data = gzip.decompress(file.read()).decode()

    data = orjson.loads(data)

    for item in data:
        for key in expected_keys:
            assert key in item

    # Check 'packages-meta-ext-v2.json.gz'.
    expected_keys = (
        "ID",
        "Name",
        "PackageBaseID",
        "PackageBase",
        "Version",
        "Description",
        "URL",
        "NumVotes",
        "Popularity",
        "OutOfDate",
        "Maintainer",
        "FirstSubmitted",
        "LastModified",
        "URLPath",
        "Depends",
        "MakeDepends",
        "CheckDepends",
        "OptDepends",
        "Provides",
        "Replaces",
    )

    with open(f"{archivedir}/packages-meta-ext-v2.json.gz", "br") as file:
        data = gzip.decompress(file.read()).decode()

    data = orjson.loads(data)

    for item in data:
        for key in expected_keys:
            assert key in item
