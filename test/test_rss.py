import pytest
from fastapi.testclient import TestClient

from aurweb import db, logging, time
from aurweb.asgi import app
from aurweb.models.account_type import AccountType
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.user import User

logger = logging.get_logger(__name__)


@pytest.fixture(autouse=True)
def setup(db_test):
    return


@pytest.fixture
def client():
    yield TestClient(app=app)


@pytest.fixture
def user():
    account_type = db.query(AccountType, AccountType.AccountType == "User").first()
    yield db.create(
        User,
        Username="test",
        Email="test@makedeb.org",
        RealName="Test User",
        Passwd="testPassword",
        AccountType=account_type,
    )


@pytest.fixture
def packages(user):
    pkgs = []
    now = time.utcnow()

    # Create 101 packages; we limit 100 on RSS feeds.
    with db.begin():
        for i in range(101):
            pkgbase = db.create(
                PackageBase,
                Maintainer=user,
                Name=f"test-package-{i}",
                SubmittedTS=(now + i),
                ModifiedTS=(now + i),
            )
            pkg = db.create(Package, Name=pkgbase.Name, PackageBase=pkgbase)
            pkgs.append(pkg)
    yield pkgs
