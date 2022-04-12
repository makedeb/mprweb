import pytest
import os
import shutil

from aurweb import config, db, models
from aurweb.testing import setup_test_db
from test import util, exceptions

base_repo_path = config.get("serve", "repo-path")

class create_git_repo:
    def __init__(self, pkgbase):
        self.pkgbase = pkgbase
        self.repo_path = f"{base_repo_path}/{pkgbase}"
        self.target_repo_path = f"{base_repo_path}/tmp-{pkgbase}"
        self.env = os.environ
        self.env["AUR_PKGBASE"] = pkgbase
        self.env["AUR_USER"] = "user"

        shutil.rmtree(base_repo_path, ignore_errors=True)
        os.makedirs(self.target_repo_path)

        util.run_command(["git", "init", "--bare", self.target_repo_path])
        util.run_command(["git", "clone", self.target_repo_path, self.repo_path])

        # If we don't get out of the directory we just deleted in
        # 'shutil.rmtree', the below 'git config' commands seem to get
        # confused.
        #
        # This path shouldn't matter with how this class is set up - we just
        # need to chdir into somewhere.
        os.chdir(base_repo_path)

        util.run_command(["git", "config", "--global", "user.name", "Foo Bar"])
        util.run_command(["git", "config", "--global", "user.email", "test@example.com"])
        os.symlink("/usr/sbin/aurweb-git-update", f"{self.target_repo_path}/hooks/update")

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
        "Packages",
        "PackageBases"
    )

    with db.begin():
        db.create(
            models.User,
            Username="user",
            Email="test@example.com",
            Passwd="1234"
        )

def test_basic_push():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgbase = testpkg",
        "pkgname = testpkg",
        "pkgname = testpkg2",
        "pkgver = 1",
        "pkgrel = 1",
        "pkgdesc = pkg",
        "arch = any"
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
        "replaces_am64 = rel5",
        "replaces_amd64 = rel6"
    ])
    
    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()
    repo.push()

    # Inspect the db schema to make sure all the needed package info was created.
    pkgbase = db.query(models.PackageBase).filter(models.PackageBase.Name == "testpkg").first()
    assert pkgbase is not None

    pkgname = db.query(models.Package).filter(models.Package.PackageBaseID == pkgbase.ID).all()
    pkgnames = [pkg.Name for pkg in pkgname]
    assert len(pkgname) == 2

    for pkg in ["testpkg", "testpkg2"]:
        assert pkg in pkgnames

    pkg = pkgname[0]

    assert pkg.Version == "1-1"
    assert pkg.Description == "pkg"

    normal_deps = db.query(models.PackageDependency).filter(models.PackageDependency.DepArch == None).filter(models.PackageDependency.DepDist == None).all()
    distro_deps = db.query(models.PackageDependency).filter(models.PackageDependency.DepArch == None).filter(models.PackageDependency.DepDist != None).all()
    arch_deps = db.query(models.PackageDependency).filter(models.PackageDependency.DepArch != None).filter(models.PackageDependency.DepDist == None).all()
    distro_arch_deps = db.query(models.PackageDependency).filter(models.PackageDependency.DepArch != None).filter(models.PackageDependency.DepDist != None).all()

    normal_rels = db.query(models.PackageRelation).filter(models.PackageRelation.RelArch == None).filter(models.PackageRelation.RelDist == None).all()
    distro_rels = db.query(models.PackageRelation).filter(models.PackageRelation.RelArch == None).filter(models.PackageRelation.RelDist != None).all()
    arch_rels = db.query(models.PackageRelation).filter(models.PackageRelation.RelArch != None).filter(models.PackageRelation.RelDist == None).all()
    distro_arch_rels = db.query(models.PackageRelation).filter(models.PackageRelation.RelArch != None).filter(models.PackageRelation.RelDist != None).all()

    raise Exception("FINISH TOMMOROW!")

def test_push_no_pkgbase():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgname = testpkg",
        "pkgver = 1",
        "pkgrel = 1",
        "pkgdesc = pkg",
        "arch = any"
    ])

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(exceptions.BadExitCode, match="Couldn't find required 'pkgbase' variable."):
        repo.push()

def test_push_no_pkgname():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgbase = testpkg",
        "pkgver = 1",
        "pkgrel = 1",
        "pkgdesc = pkg",
        "arch = any"
    ])

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(exceptions.BadExitCode, match="Couldn't find required 'pkgname' variable."):
        repo.push()

def test_push_nonmaster():
    """
    The MPR checks for any refs that aren't to master. Likewise, we use a tag ref to check the needed functionality.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    repo.add(["PKGBUILD"])
    repo.commit()
    repo.run_command(["git", "tag", "new-tag"])

    with pytest.raises(exceptions.BadExitCode, match="pushing to a branch other than master is restricted"):
        repo.run_command(["git", "push", "origin", "new-tag"])

def test_push_fastfoward():
    """
    This tests for when commits exist on the MPR that still need to be pulled by the client, but the client still attempts to push anyway.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgbase = testpkg",
        "pkgname = testpkg",
        "pkgver = 1",
        "pkgrel = 1",
        "pkgdesc = testpkgdesc",
        "arch = any"
    ])
    
    # Do the normal commit and push.
    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()
    repo.push()

    # We have to make a second commit in order to go back a commit in the next step.
    write_file(".SRCINFO", [
        "pkgbase = testpkg",
        "pkgname = testpkg",
        "pkgver = 1",
        "pkgrel = 2",
        "pkgdesc = testpkgdesc",
        "arch = any"
    ])

    repo.add([".SRCINFO"])
    repo.commit()
    repo.push()
    
    # Undo the last commit locally, then create and push a new commit without pulling.
    repo.run_command(["git", "reset", "HEAD~"])
    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()
    
    with pytest.raises(exceptions.BadExitCode, match="Updates were rejected because the tip of your current branch is behind"):
        repo.push()

def test_push_with_directories():
    """
    Make sure we get an error if we try to push a commit with files that are in a directory.
    """
    repo = create_git_repo("testpkg")
    repo.chdir_repo()
    os.mkdir("hi")

    write_file("hi/testfile", [])
    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgbase = testpkg",
        "pkgname = testpkg",
        "pkgver = 1",
        "pkgrel = 2",
        "pkgdesc = testpkgdesc",
        "arch = any"
    ])

    repo.add(["hi/testfile", "PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(exceptions.BadExitCode, match="the repository must not contain subdirectories"):
        repo.push()

def test_push_invalid_pkgbase():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [])
    write_file(".SRCINFO", [
        "pkgbase = not_the_correct_pkgbase",
        "pkgname = testpkg",
        "pkgver = 1",
        "pkgrel = 1",
        "pkgdesc = testpkgdesc",
        "arch = any"
    ])

    repo.add(["PKGBUILD", ".SRCINFO"])
    repo.commit()

    with pytest.raises(exceptions.BadExitCode, match="invalid pkgbase: not_the_correct_pkgbase, expected testpkg"):
        repo.push()
