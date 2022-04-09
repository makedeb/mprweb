import pytest
import os
import shutil

from aurweb import config, db, models
from aurweb.testing import setup_test_db
from test import util

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
        util.run_command(["git", "config", "--global", "user.name", "Foo Bar"])
        util.run_command(["git", "config", "--global", "user.email", "test@example.com"])
        util.run_command(["git", "clone", self.target_repo_path, self.repo_path])

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

def test_push():
    repo = create_git_repo("testpkg")
    repo.chdir_repo()

    write_file("PKGBUILD", [
        "pkgname=1",
        "pkgver=1",
        "pkgrel=1",
        "pkgdesc=pkg"
        "arch=('any')"
    ])
    
    repo.add(["PKGBUILD"])
    repo.commit()
    repo.push()
