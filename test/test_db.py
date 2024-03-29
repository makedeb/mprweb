import os
import re
import tempfile
from unittest import mock

import pytest

import aurweb.config
import aurweb.initdb
from aurweb import db
from aurweb.models.account_type import AccountType


class Args:
    """Stub arguments used for running aurweb.initdb."""

    use_alembic = True
    verbose = True


class DBCursor:
    """A fake database cursor object used in tests."""

    items = []

    def execute(self, *args, **kwargs):
        self.items = list(args)
        return self

    def fetchall(self):
        return self.items


class DBConnection:
    """A fake database connection object used in tests."""

    @staticmethod
    def cursor():
        return DBCursor()

    @staticmethod
    def create_function(name, num_args, func):
        pass


def make_temp_config(*replacements):
    """Generate a temporary config file with a set of replacements.

    :param *replacements: A variable number of tuple regex replacement pairs
    :return: A tuple containing (temp directory, temp config file)
    """
    db_name = aurweb.config.get("database", "name")
    db_host = aurweb.config.get_with_fallback("database", "host", "localhost")
    db_port = aurweb.config.get_with_fallback("database", "port", "3306")
    db_user = aurweb.config.get_with_fallback("database", "user", "root")
    db_password = aurweb.config.get_with_fallback("database", "password", None)

    # Replacements to perform before *replacements.
    # These serve as generic replacements in config.dev
    perform = (
        (r"name = .+", f"name = {db_name}"),
        (r"host = .+", f"host = {db_host}"),
        (r";port = .+", f";port = {db_port}"),
        (r"user = .+", f"user = {db_user}"),
        (r"password = .+", f"password = {db_password}"),
        ("YOUR_AUR_ROOT", aurweb.config.mprweb_dir),
    )

    tmpdir = tempfile.TemporaryDirectory()
    tmp = os.path.join(tmpdir.name, "config.tmp")
    with open(aurweb.config._mpr_config) as f:
        config = f.read()
        for repl in tuple(perform + replacements):
            config = re.sub(repl[0], repl[1], config)
        with open(tmp, "w") as o:
            o.write(config)
    return tmpdir, tmp


def make_temp_sqlite_config():
    return make_temp_config(
        (r"backend = .*", "backend = sqlite"),
        (r"name = .*", "name = /tmp/aurweb.sqlite3"),
    )


def make_temp_mysql_config():
    return make_temp_config(
        (r"backend = .*", "backend = mysql"), (r"name = .*", "name = aurweb_test")
    )


@pytest.fixture(autouse=True)
def setup(db_test):
    if os.path.exists("/tmp/aurweb.sqlite3"):
        os.remove("/tmp/aurweb.sqlite3")


def test_sqlalchemy_sqlite_url():
    tmpctx, tmp = make_temp_sqlite_config()
    with tmpctx:
        with mock.patch.dict(os.environ, {"MPR_CONFIG": tmp}):
            aurweb.config.rehash()
            assert db.get_sqlalchemy_url()
    aurweb.config.rehash()


def test_sqlalchemy_mysql_url():
    tmpctx, tmp = make_temp_mysql_config()
    with tmpctx:
        with mock.patch.dict(os.environ, {"MPR_CONFIG": tmp}):
            aurweb.config.rehash()
            assert db.get_sqlalchemy_url()
    aurweb.config.rehash()


def test_sqlalchemy_mysql_port_url():
    tmpctx, tmp = make_temp_config((r";port = 3306", "port = 3306"))

    with tmpctx:
        with mock.patch.dict(os.environ, {"MPR_CONFIG": tmp}):
            aurweb.config.rehash()
            assert db.get_sqlalchemy_url()
        aurweb.config.rehash()


def test_sqlalchemy_mysql_socket_url():
    tmpctx, tmp = make_temp_config()

    with tmpctx:
        with mock.patch.dict(os.environ, {"MPR_CONFIG": tmp}):
            aurweb.config.rehash()
            assert db.get_sqlalchemy_url()
        aurweb.config.rehash()


def test_db_connects_without_fail():
    """This only tests the actual config supplied to pytest."""
    db.connect()


@mock.patch("MySQLdb.connect", mock.MagicMock(return_value=True))
def test_connection_mysql():
    tmpctx, tmp = make_temp_mysql_config()
    with tmpctx:
        with mock.patch.dict(os.environ, {"MPR_CONFIG": tmp}):
            aurweb.config.rehash()
            db.Connection()
        aurweb.config.rehash()


def test_create_delete():
    with db.begin():
        account_type = db.create(AccountType, AccountType="test")

    record = db.query(AccountType, AccountType.AccountType == "test").first()
    assert record is not None

    with db.begin():
        db.delete(account_type)

    record = db.query(AccountType, AccountType.AccountType == "test").first()
    assert record is None


def test_add_commit():
    # Use db.add and db.commit to add a temporary record.
    account_type = AccountType(AccountType="test")
    with db.begin():
        db.add(account_type)

    # Assert it got created in the DB.
    assert bool(account_type.ID)

    # Query the DB for it and compare the record with our object.
    record = db.query(AccountType, AccountType.AccountType == "test").first()
    assert record == account_type

    # Remove the record.
    with db.begin():
        db.delete(account_type)


def test_connection_executor_mysql_paramstyle():
    executor = db.ConnectionExecutor(None)
    assert executor.paramstyle() == "format"


def test_name_without_pytest_current_test():
    with mock.patch.dict("os.environ", {}, clear=True):
        dbname = aurweb.db.name()
    assert dbname == aurweb.config.get("database", "name")
