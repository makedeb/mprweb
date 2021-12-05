from datetime import datetime
from typing import List
from unittest import mock

import pytest

from aurweb import config, db, models
from aurweb.models import Package, PackageBase, PackageRequest, User
from aurweb.models.account_type import TRUSTED_USER_ID, USER_ID
from aurweb.models.request_type import ORPHAN_ID
from aurweb.scripts import notify, rendercomment
from aurweb.testing.email import Email
from aurweb.testing.smtp import FakeSMTP, FakeSMTP_SSL

aur_location = config.get("options", "aur_location")
aur_request_ml = config.get("options", "aur_request_ml")


@pytest.fixture(autouse=True)
def setup(db_test):
    return


@pytest.fixture
def user() -> User:
    with db.begin():
        user = db.create(User, Username="test", Email="test@example.org",
                         Passwd=str(), AccountTypeID=USER_ID)
    yield user


@pytest.fixture
def user1() -> User:
    with db.begin():
        user1 = db.create(User, Username="user1", Email="user1@example.org",
                          Passwd=str(), AccountTypeID=USER_ID)
    yield user1


@pytest.fixture
def user2() -> User:
    with db.begin():
        user2 = db.create(User, Username="user2", Email="user2@example.org",
                          Passwd=str(), AccountTypeID=USER_ID)
    yield user2


@pytest.fixture
def pkgbases(user: User) -> List[PackageBase]:
    now = int(datetime.utcnow().timestamp())

    output = []
    with db.begin():
        for i in range(5):
            output.append(
                db.create(PackageBase, Name=f"pkgbase_{i}",
                          Maintainer=user, SubmittedTS=now,
                          ModifiedTS=now))
            db.create(models.PackageNotification, PackageBase=output[-1],
                      User=user)
    yield output


@pytest.fixture
def pkgreq(user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    with db.begin():
        pkgreq_ = db.create(PackageRequest, PackageBase=pkgbase,
                            PackageBaseName=pkgbase.Name, User=user2,
                            ReqTypeID=ORPHAN_ID,
                            Comments="This is a request test comment.",
                            ClosureComment=str())
    yield pkgreq_


@pytest.fixture
def packages(pkgbases: List[PackageBase]) -> List[Package]:
    output = []
    with db.begin():
        for i, pkgbase in enumerate(pkgbases):
            output.append(
                db.create(Package, PackageBase=pkgbase,
                          Name=f"pkg_{i}", Version=f"{i}.0"))
    yield output


def test_out_of_date(user: User, user1: User, user2: User,
                     pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    # Create two comaintainers. We'll pass the maintainer uid to
    # FlagNotification, so we should expect to get two emails.
    with db.begin():
        db.create(models.PackageComaintainer,
                  PackageBase=pkgbase, User=user1, Priority=1)
        db.create(models.PackageComaintainer,
                  PackageBase=pkgbase, User=user2, Priority=2)

    # Send the notification for pkgbases[0].
    notif = notify.FlagNotification(user.ID, pkgbases[0].ID)
    notif.send()

    # Should've gotten three emails: maintainer + the two comaintainers.
    assert Email.count() == 3

    # Comaintainer 1.
    first = Email(1).parse()
    assert first.headers.get("To") == user1.Email

    expected = f"MPR Out-of-date Notification for {pkgbase.Name}"
    assert first.headers.get("Subject") == expected

    # Comaintainer 2.
    second = Email(2).parse()
    assert second.headers.get("To") == user2.Email

    # Maintainer.
    third = Email(3).parse()
    assert third.headers.get("To") == user.Email


def test_reset(user: User):
    with db.begin():
        user.ResetKey = "12345678901234567890123456789012"

    notif = notify.ResetKeyNotification(user.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    expected = "MPR Password Reset"
    assert email.headers.get("Subject") == expected

    expected = f"""\
A password reset request was submitted for the account test associated
with your email address. If you wish to reset your password follow the
link [1] below, otherwise ignore this message and nothing will happen.

[1] {aur_location}/passreset/?resetkey=12345678901234567890123456789012\
"""
    assert email.body == expected


def test_welcome(user: User):
    with db.begin():
        user.ResetKey = "12345678901234567890123456789012"

    notif = notify.WelcomeNotification(user.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    expected = "Welcome to the makedeb Package Repository"
    assert email.headers.get("Subject") == expected

    expected = f"""\
Welcome to the makedeb Package Repository! In order to set an initial
password for your new account, please click the link [1] below. If the
link does not work, try copying and pasting it into your browser.

[1] {aur_location}/passreset/?resetkey=12345678901234567890123456789012\
"""
    assert email.body == expected


def test_comment(user: User, user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]

    with db.begin():
        comment = db.create(models.PackageComment, PackageBase=pkgbase,
                            User=user2, Comments="This is a test comment.")
    rendercomment.update_comment_render_fastapi(comment)

    notif = notify.CommentNotification(user2.ID, pkgbase.ID, comment.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Comment for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
{user2.Username} [1] added the following comment to {pkgbase.Name} [2]:

This is a test comment.

--
If you no longer wish to receive notifications about this package,
please go to the package page [2] and select "Disable notifications".

[1] {aur_location}/account/{user2.Username}/
[2] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert expected == email.body


def test_update(user: User, user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    with db.begin():
        user.UpdateNotify = 1

    notif = notify.UpdateNotification(user2.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Package Update: {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
{user2.Username} [1] pushed a new commit to {pkgbase.Name} [2].

--
If you no longer wish to receive notifications about this package,
please go to the package page [2] and select "Disable notifications".

[1] {aur_location}/account/{user2.Username}/
[2] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert expected == email.body


def test_adopt(user: User, user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    notif = notify.AdoptNotification(user2.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Ownership Notification for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
The package {pkgbase.Name} [1] was adopted by {user2.Username} [2].

[1] {aur_location}/pkgbase/{pkgbase.Name}/
[2] {aur_location}/account/{user2.Username}/\
"""
    assert email.body == expected


def test_disown(user: User, user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    notif = notify.DisownNotification(user2.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Ownership Notification for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
The package {pkgbase.Name} [1] was disowned by {user2.Username} [2].

[1] {aur_location}/pkgbase/{pkgbase.Name}/
[2] {aur_location}/account/{user2.Username}/\
"""
    assert email.body == expected


def test_comaintainer_addition(user: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    notif = notify.ComaintainerAddNotification(user.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Co-Maintainer Notification for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
You were added to the co-maintainer list of {pkgbase.Name} [1].

[1] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert email.body == expected


def test_comaintainer_removal(user: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    notif = notify.ComaintainerRemoveNotification(user.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Co-Maintainer Notification for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
You were removed from the co-maintainer list of {pkgbase.Name} [1].

[1] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert email.body == expected


def test_delete(user: User, user2: User, pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    notif = notify.DeleteNotification(user2.ID, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Package deleted: {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
{user2.Username} [1] deleted {pkgbase.Name} [2].

You will no longer receive notifications about this package.

[1] {aur_location}/account/{user2.Username}/
[2] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert email.body == expected


def test_merge(user: User, user2: User, pkgbases: List[PackageBase]):
    source, target = pkgbases[:2]
    notif = notify.DeleteNotification(user2.ID, source.ID, target.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"MPR Package deleted: {source.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
{user2.Username} [1] merged {source.Name} [2] into {target.Name} [3].

--
If you no longer wish receive notifications about the new package,
please go to [3] and click "Disable notifications".

[1] {aur_location}/account/{user2.Username}/
[2] {aur_location}/pkgbase/{source.Name}/
[3] {aur_location}/pkgbase/{target.Name}/\
"""
    assert email.body == expected


def set_tu(users: List[User]) -> User:
    with db.begin():
        for user in users:
            user.AccountTypeID = TRUSTED_USER_ID


def test_open_close_request(user: User, user2: User,
                            pkgreq: PackageRequest,
                            pkgbases: List[PackageBase]):
    set_tu([user])
    pkgbase = pkgbases[0]

    # Send an open request notification.
    notif = notify.RequestOpenNotification(
        user2.ID, pkgreq.ID, pkgreq.RequestType.Name, pkgbase.ID)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == aur_request_ml
    assert email.headers.get("Cc") == ", ".join([user.Email, user2.Email])
    expected = f"[PRQ#{pkgreq.ID}] Orphan Request for {pkgbase.Name}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
{user2.Username} [1] filed an orphan request for {pkgbase.Name} [2]:

This is a request test comment.

[1] {aur_location}/account/{user2.Username}/
[2] {aur_location}/pkgbase/{pkgbase.Name}/\
"""
    assert email.body == expected

    # Now send a closure notification on the pkgbase we just opened.
    notif = notify.RequestCloseNotification(user2.ID, pkgreq.ID, "rejected")
    notif.send()
    assert Email.count() == 2

    email = Email(2).parse()
    assert email.headers.get("To") == aur_request_ml
    assert email.headers.get("Cc") == ", ".join([user.Email, user2.Email])
    expected = f"[PRQ#{pkgreq.ID}] Orphan Request for {pkgbase.Name} Rejected"
    assert email.headers.get("Subject") == expected

    expected = f"""\
Request #{pkgreq.ID} has been rejected by {user2.Username} [1].

[1] {aur_location}/account/{user2.Username}/\
"""
    assert email.body == expected

    # Test auto-accept.
    notif = notify.RequestCloseNotification(0, pkgreq.ID, "accepted")
    notif.send()
    assert Email.count() == 3

    email = Email(3).parse()
    assert email.headers.get("To") == aur_request_ml
    assert email.headers.get("Cc") == ", ".join([user.Email, user2.Email])
    expected = (f"[PRQ#{pkgreq.ID}] Orphan Request for "
                f"{pkgbase.Name} Accepted")
    assert email.headers.get("Subject") == expected

    expected = (f"Request #{pkgreq.ID} has been accepted automatically "
                "by the makedeb Package\nRepository package request system.")
    assert email.body == expected


def test_close_request_comaintainer_cc(user: User, user2: User,
                                       pkgreq: PackageRequest,
                                       pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    with db.begin():
        db.create(models.PackageComaintainer, PackageBase=pkgbase,
                  User=user2, Priority=1)

    notif = notify.RequestCloseNotification(0, pkgreq.ID, "accepted")
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == aur_request_ml
    assert email.headers.get("Cc") == ", ".join([user.Email, user2.Email])


def test_close_request_closure_comment(user: User, user2: User,
                                       pkgreq: PackageRequest,
                                       pkgbases: List[PackageBase]):
    pkgbase = pkgbases[0]
    with db.begin():
        pkgreq.ClosureComment = "This is a test closure comment."

    notif = notify.RequestCloseNotification(user2.ID, pkgreq.ID, "accepted")
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == aur_request_ml
    assert email.headers.get("Cc") == ", ".join([user.Email, user2.Email])
    expected = f"[PRQ#{pkgreq.ID}] Orphan Request for {pkgbase.Name} Accepted"
    assert email.headers.get("Subject") == expected

    expected = f"""\
Request #{pkgreq.ID} has been accepted by {user2.Username} [1]:

This is a test closure comment.

[1] {aur_location}/account/{user2.Username}/\
"""
    assert email.body == expected


def test_tu_vote_reminders(user: User):
    set_tu([user])

    vote_id = 1
    notif = notify.TUVoteReminderNotification(vote_id)
    notif.send()
    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"TU Vote Reminder: Proposal {vote_id}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
Please remember to cast your vote on proposal {vote_id} [1]. The voting period
ends in less than 48 hours.

[1] {aur_location}/tu/?id={vote_id}\
"""
    assert email.body == expected


def test_notify_main(user: User):
    """ Test TU vote reminder through aurweb.notify.main(). """
    set_tu([user])

    vote_id = 1
    args = ["aurweb-notify", "tu-vote-reminder", str(vote_id)]
    with mock.patch("sys.argv", args):
        notify.main()

    assert Email.count() == 1

    email = Email(1).parse()
    assert email.headers.get("To") == user.Email
    expected = f"TU Vote Reminder: Proposal {vote_id}"
    assert email.headers.get("Subject") == expected

    expected = f"""\
Please remember to cast your vote on proposal {vote_id} [1]. The voting period
ends in less than 48 hours.

[1] {aur_location}/tu/?id={vote_id}\
"""
    assert email.body == expected


# Save original config.get; we're going to mock it and need
# to be able to fallback when we are not overriding.
config_get = config.get


def mock_smtp_config(cls):
    def _mock_smtp_config(section: str, key: str):
        if section == "notifications":
            if key == "sendmail":
                return cls()
            elif key == "smtp-use-ssl":
                return cls(0)
            elif key == "smtp-use-starttls":
                return cls(0)
            elif key == "smtp-user":
                return cls()
            elif key == "smtp-password":
                return cls()
        return cls(config_get(section, key))
    return _mock_smtp_config


def test_smtp(user: User):
    with db.begin():
        user.ResetKey = "12345678901234567890123456789012"

    SMTP = FakeSMTP()

    get = "aurweb.config.get"
    getboolean = "aurweb.config.getboolean"
    with mock.patch(get, side_effect=mock_smtp_config(str)):
        with mock.patch(getboolean, side_effect=mock_smtp_config(bool)):
            with mock.patch("smtplib.SMTP", side_effect=lambda a, b: SMTP):
                config.rehash()
                notif = notify.WelcomeNotification(user.ID)
                notif.send()
    config.rehash()
    assert len(SMTP.emails) == 1


def mock_smtp_starttls_config(cls):
    def _mock_smtp_starttls_config(section: str, key: str):
        if section == "notifications":
            if key == "sendmail":
                return cls()
            elif key == "smtp-use-ssl":
                return cls(0)
            elif key == "smtp-use-starttls":
                return cls(1)
            elif key == "smtp-user":
                return cls("test")
            elif key == "smtp-password":
                return cls("password")
        return cls(config_get(section, key))
    return _mock_smtp_starttls_config


def test_smtp_starttls(user: User):
    # This test does two things: test starttls path and test
    # path where we have a backup email.

    with db.begin():
        user.ResetKey = "12345678901234567890123456789012"
        user.BackupEmail = "backup@example.org"

    SMTP = FakeSMTP()

    get = "aurweb.config.get"
    getboolean = "aurweb.config.getboolean"
    with mock.patch(get, side_effect=mock_smtp_starttls_config(str)):
        with mock.patch(
                getboolean, side_effect=mock_smtp_starttls_config(bool)):
            with mock.patch("smtplib.SMTP", side_effect=lambda a, b: SMTP):
                notif = notify.WelcomeNotification(user.ID)
                notif.send()
    assert SMTP.starttls_enabled
    assert SMTP.user
    assert SMTP.passwd

    assert len(SMTP.emails) == 2
    to = SMTP.emails[0][1]
    assert to == [user.Email]

    to = SMTP.emails[1][1]
    assert to == [user.BackupEmail]


def mock_smtp_ssl_config(cls):
    def _mock_smtp_ssl_config(section: str, key: str):
        if section == "notifications":
            if key == "sendmail":
                return cls()
            elif key == "smtp-use-ssl":
                return cls(1)
            elif key == "smtp-use-starttls":
                return cls(0)
            elif key == "smtp-user":
                return cls("test")
            elif key == "smtp-password":
                return cls("password")
        return cls(config_get(section, key))
    return _mock_smtp_ssl_config


def test_smtp_ssl(user: User):
    with db.begin():
        user.ResetKey = "12345678901234567890123456789012"

    SMTP = FakeSMTP_SSL()

    get = "aurweb.config.get"
    getboolean = "aurweb.config.getboolean"
    with mock.patch(get, side_effect=mock_smtp_ssl_config(str)):
        with mock.patch(getboolean, side_effect=mock_smtp_ssl_config(bool)):
            with mock.patch("smtplib.SMTP_SSL", side_effect=lambda a, b: SMTP):
                notif = notify.WelcomeNotification(user.ID)
                notif.send()
    assert len(SMTP.emails) == 1
    assert SMTP.use_ssl
    assert SMTP.user
    assert SMTP.passwd


def test_notification_defaults():
    notif = notify.Notification()
    assert notif.get_refs() == tuple()
    assert notif.get_headers() == dict()
    assert notif.get_cc() == list()