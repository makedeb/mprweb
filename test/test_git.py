import os
import shutil
from test import exceptions, util

import pytest

from aurweb import config, db, models
from aurweb.models.dependency_type import (
    CHECKDEPENDS_ID,
    DEPENDS_ID,
    MAKEDEPENDS_ID,
    OPTDEPENDS_ID,
)
from aurweb.models.relation_type import CONFLICTS_ID, PROVIDES_ID, REPLACES_ID
from aurweb.testing import setup_test_db

start_dir = os.getcwd()


class create_git_repo:
    """
    Helper class to create and manage an MPR Git repository to test packages
    with.
    """

    def __init__(self, pkgbase):
        self.pkgbase = pkgbase
        self.repo_path = f"{config.git_repo_path}/{pkgbase}"
        self.target_repo_path = f"{config.git_repo_path}/tmp-{pkgbase}"
        self.env = os.environ
        self.env["AUR_PKGBASE"] = pkgbase
        self.env["AUR_USER"] = "user"

        shutil.rmtree(config.git_repo_path, ignore_errors=True)
        os.makedirs(self.target_repo_path)

        util.run_command(["git", "init", "--bare", self.target_repo_path])
        util.run_command(["git", "clone", self.target_repo_path, self.repo_path])

        # If we don't get out of the directory we just deleted in
        # 'shutil.rmtree', the below 'git config' commands seem to get
        # confused.
        #
        # This path shouldn't matter with how this class is set up - we just
        # need to chdir into somewhere.
        os.chdir(config.git_repo_path)

        util.run_command(["git", "config", "--global", "user.name", "Foo Bar"])
        util.run_command(
            ["git", "config", "--global", "user.email", "test@example.com"]
        )
        os.symlink(
            "/usr/sbin/aurweb-git-update", f"{self.target_repo_path}/hooks/update"
        )

    def run_command(self, *args, **kwargs):
        os.chdir(self.repo_path)
        return util.run_command(*args, **kwargs, env=self.env)

    def chdir_repo(self):
        os.chdir(self.repo_path)

    def add(self, files):
        results = []
        for file in files:
            results += [self.run_command(["git", "add", file])]
        return results

    def commit(self, *args):
        if len(args) == 0:
            msg = "Made a commit"
        else:
            msg = args[0]
        return self.run_command(["git", "commit", "-m", msg])

    def push(self):
        return self.run_command(["git", "push"])


def write_file(filename, lines):
    with open(filename, "w") as file:
        file.write("\n".join(lines))


@pytest.fixture(autouse=True)
def setup(db_test):
    setup_test_db(
        "Users",
        "PackageDepends",
        "PackageRelations",
        "PackageSources",
        "Packages",
        "PackageBases",
    )

    with db.begin():
        db.create(models.User, Username="user", Email="test@example.com", Passwd="1234")


@pytest.fixture(autouse=True)
def chdir_to_start_dir():
    yield
    os.chdir(start_dir)


def test_basic_push():
    source_url_prefix = "https://example.com"
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgname = testpkg",
            "pkgname = testpkg2",
            "pkgver = 1",
            "pkgrel = 1",
            "pkgdesc = pkg",
            "arch = any",
            "depends = dep1",
            "depends = dep2",
            "focal_makedepends = dep3",
            "focal_makedepends = dep4",
            "checkdepends_amd64 = dep5",
            "checkdepends_amd64 = dep6",
            "focal_optdepends_amd64 = dep7",
            "focal_optdepends_amd64 = dep8",
            "conflicts = rel1",
            "conflicts = rel2",
            "focal_provides = rel3",
            "focal_provides = rel4",
            "replaces_amd64 = rel5",
            "replaces_amd64 = rel6",
            "focal_replaces_amd64 = rel7",
            "focal_replaces_amd64 = rel8",
            f"source = {source_url_prefix}/source1",
            f"source = {source_url_prefix}/source2",
            f"focal_source = {source_url_prefix}/source3",
            f"focal_source = {source_url_prefix}/source4",
            f"source_amd64 = {source_url_prefix}/source5",
            f"source_amd64 = {source_url_prefix}/source6",
            f"focal_source_amd64 = {source_url_prefix}/source7",
            f"focal_source_amd64 = {source_url_prefix}/source8",
            "postinst = ./testfile",
        ],
    )

    write_file("testfile", [])

    repo.add(["PKGBUILD", ".SRCINFO", "testfile"])
    repo.commit()
    repo.push()

    # Inspect the db schema to make sure all the needed package info was created.
    pkgbase = (
        db.query(models.PackageBase)
        .filter(models.PackageBase.Name == "testpkg")
        .first()
    )
    assert pkgbase is not None

    pkgname = (
        db.query(models.Package)
        .filter(models.Package.PackageBaseID == pkgbase.ID)
        .all()
    )
    pkgnames = [pkg.Name for pkg in pkgname]
    assert len(pkgname) == 2

    for pkg in ["testpkg", "testpkg2"]:
        assert pkg in pkgnames

    pkg = pkgname[0]

    assert pkg.Version == "1-1"
    assert pkg.Description == "pkg"

    # Get dependencies, relations, and sources.
    normal_deps = (
        db.query(models.PackageDependency)
        .filter(models.PackageDependency.DepArch == None)  # noqa: E711
        .filter(models.PackageDependency.DepDist == None)  # noqa: E711
        .all()
    )
    distro_deps = (
        db.query(models.PackageDependency)
        .filter(models.PackageDependency.DepArch == None)  # noqa: E711
        .filter(models.PackageDependency.DepDist != None)  # noqa: E711
        .all()
    )
    arch_deps = (
        db.query(models.PackageDependency)
        .filter(models.PackageDependency.DepArch != None)  # noqa: E711
        .filter(models.PackageDependency.DepDist == None)  # noqa: E711
        .all()
    )
    distro_arch_deps = (
        db.query(models.PackageDependency)
        .filter(models.PackageDependency.DepArch != None)  # noqa: E711
        .filter(models.PackageDependency.DepDist != None)  # noqa: E711
        .all()
    )

    normal_rels = (
        db.query(models.PackageRelation)
        .filter(models.PackageRelation.RelArch == None)  # noqa: E711
        .filter(models.PackageRelation.RelDist == None)  # noqa: E711
        .all()
    )
    distro_rels = (
        db.query(models.PackageRelation)
        .filter(models.PackageRelation.RelArch == None)  # noqa: E711
        .filter(models.PackageRelation.RelDist != None)  # noqa: E711
        .all()
    )
    arch_rels = (
        db.query(models.PackageRelation)
        .filter(models.PackageRelation.RelArch != None)  # noqa: E711
        .filter(models.PackageRelation.RelDist == None)  # noqa: E711
        .all()
    )
    distro_arch_rels = (
        db.query(models.PackageRelation)
        .filter(models.PackageRelation.RelArch != None)  # noqa: E711
        .filter(models.PackageRelation.RelDist != None)  # noqa: E711
        .all()
    )

    normal_sources = (
        db.query(models.PackageSource)
        .filter(models.PackageSource.SourceArch == None)  # noqa: E711
        .filter(models.PackageSource.SourceDist == None)  # noqa: E711
        .all()
    )
    distro_sources = (
        db.query(models.PackageSource)
        .filter(models.PackageSource.SourceArch == None)  # noqa: E711
        .filter(models.PackageSource.SourceDist != None)  # noqa: E711
        .all()
    )
    arch_sources = (
        db.query(models.PackageSource)
        .filter(models.PackageSource.SourceArch != None)  # noqa: E711
        .filter(models.PackageSource.SourceDist == None)  # noqa: E711
        .all()
    )
    distro_arch_sources = (
        db.query(models.PackageSource)
        .filter(models.PackageSource.SourceArch != None)  # noqa: E711
        .filter(models.PackageSource.SourceDist != None)  # noqa: E711
        .all()
    )

    # Test that we have the right amount of items for each.
    # We set up two of each, and each 'pkgname' gets its own copies, so
    # 2 * 2 -> 4 for each type total.
    for item in (
        normal_deps,
        distro_deps,
        arch_deps,
        distro_arch_deps,
        normal_rels,
        distro_rels,
        arch_rels,
        distro_arch_rels,
        normal_sources,
        distro_sources,
        arch_sources,
        distro_arch_sources,
    ):
        assert len(item) == 4

    # Test dependencies.
    expected_names = ["dep1", "dep2"]
    for dep in normal_deps:
        assert dep.DepTypeID == DEPENDS_ID
        assert dep.DepArch is None
        assert dep.DepDist is None
        assert dep.DepName in expected_names

    expected_names = ["dep3", "dep4"]
    for dep in distro_deps:
        assert dep.DepTypeID == MAKEDEPENDS_ID
        assert dep.DepArch is None
        assert dep.DepDist == "focal"
        assert dep.DepName in expected_names

    expected_names = ["dep5", "dep6"]
    for dep in arch_deps:
        assert dep.DepTypeID == CHECKDEPENDS_ID
        assert dep.DepArch == "amd64"
        assert dep.DepDist is None
        assert dep.DepName in expected_names

    expected_names = ["dep7", "dep8"]
    for dep in distro_arch_deps:
        assert dep.DepTypeID == OPTDEPENDS_ID
        assert dep.DepArch == "amd64"
        assert dep.DepDist == "focal"
        assert dep.DepName in expected_names

    # Test relations.
    expected_names = ["rel1", "rel2"]
    for rel in normal_rels:
        assert rel.RelTypeID == CONFLICTS_ID
        assert rel.RelArch is None
        assert rel.RelDist is None
        assert rel.RelName in expected_names

    expected_names = ["rel3", "rel4"]
    for rel in distro_rels:
        assert rel.RelTypeID == PROVIDES_ID
        assert rel.RelArch is None
        assert rel.RelDist == "focal"
        assert rel.RelName in expected_names

    expected_names = ["rel5", "rel6"]
    for rel in arch_rels:
        assert rel.RelTypeID == REPLACES_ID
        assert rel.RelArch == "amd64"
        assert rel.RelDist is None
        assert rel.RelName in expected_names

    expected_names = ["rel7", "rel8"]
    for rel in distro_arch_rels:
        assert rel.RelTypeID == REPLACES_ID
        assert rel.RelArch == "amd64"
        assert rel.RelDist == "focal"
        assert rel.RelName in expected_names

    # Test sources.
    expected_names = ["source1", "source2"]
    for source in normal_sources:
        assert source.SourceArch is None
        assert source.SourceDist is None
        assert source.Source.removeprefix(f"{source_url_prefix}/") in expected_names

    expected_names = ["source3", "source4"]
    for source in distro_sources:
        assert source.SourceArch is None
        assert source.SourceDist == "focal"
        assert source.Source.removeprefix(f"{source_url_prefix}/") in expected_names

    expected_names = ["source5", "source6"]
    for source in arch_sources:
        assert source.SourceArch == "amd64"
        assert source.SourceDist is None
        assert source.Source.removeprefix(f"{source_url_prefix}/") in expected_names

    expected_names = ["source7", "source8"]
    for source in distro_arch_sources:
        assert source.SourceArch == "amd64"
        assert source.SourceDist == "focal"
        assert source.Source.removeprefix(f"{source_url_prefix}/") in expected_names


def test_push_no_pkgbase():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 1",
            "pkgdesc = pkg",
            "arch = any",
        ],
    )

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(
        exceptions.BadExitCode, match="Couldn't find required 'pkgbase' variable."
    ):
        repo.push()


def test_push_no_pkgname():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgver = 1",
            "pkgrel = 1",
            "pkgdesc = pkg",
            "arch = any",
        ],
    )

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(
        exceptions.BadExitCode, match="Couldn't find required 'pkgname' variable."
    ):
        repo.push()


def test_push_nonmaster():
    """
    The MPR checks for any refs that aren't to master. Likewise, we use a tag
    ref to check the needed functionality.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    repo.add(["PKGBUILD"])
    repo.commit()
    repo.run_command(["git", "tag", "new-tag"])

    with pytest.raises(
        exceptions.BadExitCode,
        match="pushing to a branch other than master is restricted",
    ):
        repo.run_command(["git", "push", "origin", "new-tag"])


def test_push_fastfoward():
    """
    This tests for when commits exist on the MPR that still need to be pulled by
    the client, but the client still attempts to push anyway.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 1",
            "pkgdesc = testpkgdesc",
            "arch = any",
        ],
    )

    # Do the normal commit and push.
    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()
    repo.push()

    # We have to make a second commit in order to go back a commit in the next step.
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 2",
            "pkgdesc = testpkgdesc",
            "arch = any",
        ],
    )

    repo.add([".SRCINFO"])
    repo.commit()
    repo.push()

    # Undo the last commit locally, then create and push a new commit without pulling.
    repo.run_command(["git", "reset", "HEAD~"])
    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(
        exceptions.BadExitCode,
        match="Updates were rejected because the tip of your current branch is behind",
    ):
        repo.push()


def test_push_with_directories():
    """
    Make sure we get an error if we try to push a commit with files that are in
    a directory.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()
    os.mkdir("hi")

    write_file("hi/testfile", [])
    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 2",
            "pkgdesc = testpkgdesc",
            "arch = any",
        ],
    )

    repo.add(["hi/testfile", "PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(
        exceptions.BadExitCode, match="the repository must not contain subdirectories"
    ):
        repo.push()


def test_push_invalid_pkgbase():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = not_the_correct_pkgbase",
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 1",
            "pkgdesc = testpkgdesc",
            "arch = any",
        ],
    )

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(
        exceptions.BadExitCode,
        match="invalid pkgbase: not_the_correct_pkgbase, expected testpkg",
    ):
        repo.push()


def test_push_with_epoch():
    """
    Ensure that the update script creates a tag with the ':' in the epoch
    replaced with a '!'.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(
        ".SRCINFO",
        [
            "pkgbase = testpkg",
            "pkgname = testpkg",
            "pkgver = 1",
            "pkgrel = 1",
            "epoch = 1",
            "pkgdesc = testpkgdesc",
            "arch = any",
        ],
    )

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()
    repo.push()

    assert repo.run_command(["git", "tag"]).stdout == "ver/1!1-1\n"
