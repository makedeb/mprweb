from typing import Tuple

import pytest

from aurweb import config, db, time
from aurweb.models import TUVote, TUVoteInfo, User
from aurweb.models.account_type import TRUSTED_USER_ID

aur_location = config.get("options", "aur_location")


def create_vote(user: User, voteinfo: TUVoteInfo) -> TUVote:
    with db.begin():
        vote = db.create(TUVote, User=user, VoteID=voteinfo.ID)
    return vote


def create_user(username: str, type_id: int):
    with db.begin():
        user = db.create(
            User,
            AccountTypeID=type_id,
            Username=username,
            Email=f"{username}@makedeb.org",
            Passwd=str(),
        )
    return user


def email_pieces(voteinfo: TUVoteInfo) -> Tuple[str, str]:
    """
    Return a (subject, content) tuple based on voteinfo.ID

    :param voteinfo: TUVoteInfo instance
    :return: tuple(subject, content)
    """
    subject = f"TU Vote Reminder: Proposal {voteinfo.ID}"
    content = (
        f"Please remember to cast your vote on proposal {voteinfo.ID} "
        f"[1]. The voting period\nends in less than 48 hours.\n\n"
        f"[1] {aur_location}/tu/?id={voteinfo.ID}"
    )
    return (subject, content)


@pytest.fixture
def user(db_test) -> User:
    yield create_user("test", TRUSTED_USER_ID)


@pytest.fixture
def user2() -> User:
    yield create_user("test2", TRUSTED_USER_ID)


@pytest.fixture
def user3() -> User:
    yield create_user("test3", TRUSTED_USER_ID)


@pytest.fixture
def voteinfo(user: User) -> TUVoteInfo:
    now = time.utcnow()
    start = config.getint("tuvotereminder", "range_start")
    with db.begin():
        voteinfo = db.create(
            TUVoteInfo,
            Agenda="Lorem ipsum.",
            User=user.Username,
            End=(now + start + 1),
            Quorum=0.00,
            Submitter=user,
            Submitted=0,
        )
    yield voteinfo
