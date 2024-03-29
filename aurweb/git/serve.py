#!/usr/bin/env python3

import os
import re
import shlex
import subprocess
import sys
import time

import sentry_sdk
from sentry_sdk import push_scope

import aurweb.config
import aurweb.exceptions
import aurweb.sentry
from aurweb import db
from aurweb.models.package_base import PackageBase
from aurweb.models.package_comaintainer import PackageComaintainer

git_shell_cmd = "/usr/bin/git-shell"
git_update_cmd = "/usr/bin/aurweb-git-update"

enable_maintenance = aurweb.config.getboolean("options", "enable-maintenance")
maintenance_exc = aurweb.config.get_with_fallback(
    "options", "maintenance-exceptions", ""
).split()


def log_ssh_login(user, remote_addr):
    conn = aurweb.db.Connection()

    now = int(time.time())
    conn.execute(
        "UPDATE Users SET LastSSHLogin = ?, "
        + "LastSSHLoginIPAddress = ? WHERE Username = ?",
        [now, remote_addr, user],
    )

    conn.commit()
    conn.close()


def bans_match(remote_addr):
    conn = aurweb.db.Connection()

    cur = conn.execute("SELECT COUNT(*) FROM Bans WHERE IPAddress = ?", [remote_addr])
    return cur.fetchone()[0] > 0


def die(msg):
    sys.stderr.write("remote: {:s}\n".format(msg))
    exit(1)


def die_unknown_error():
    die(
        "An unknown error has occurred. These incidents are automatically logged, and"
        + " will be reviewed by a makedeb team member shortly."
    )


def checkarg_atleast(cmdargv, *argdesc):
    if len(cmdargv) - 1 < len(argdesc):
        msg = "missing {:s}".format(argdesc[len(cmdargv) - 1])
        raise aurweb.exceptions.InvalidArgumentsException(msg)


def checkarg_atmost(cmdargv, *argdesc):
    if len(cmdargv) - 1 > len(argdesc):
        raise aurweb.exceptions.InvalidArgumentsException("too many arguments")


def checkarg(cmdargv, *argdesc):
    checkarg_atleast(cmdargv, *argdesc)
    checkarg_atmost(cmdargv, *argdesc)


def serve(action, cmdargv, username, privileged, remote_addr):  # noqa: C901
    if enable_maintenance:
        if remote_addr not in maintenance_exc:
            raise aurweb.exceptions.MaintenanceException

    if bans_match(remote_addr):
        raise aurweb.exceptions.BannedException

    log_ssh_login(username, remote_addr)

    # Convert Git pack commands into a single argument.
    if action == "git" and cmdargv[1] in ("upload-pack", "receive-pack"):
        action = action + "-" + cmdargv[1]
        del cmdargv[1]

    # Handle Git pack commands.
    if action == "git-upload-pack" or action == "git-receive-pack":
        checkarg(cmdargv, "path")

        # Parse Git path.
        path = cmdargv[1].rstrip("/")

        if not path.startswith("/"):
            path = "/" + path

        if not path.endswith(".git"):
            path = path + ".git"

        # Current Package Base details.
        pkgbase_name = path[1:-4]

        # Check if specified repository matches the repo regex.
        if not re.match(aurweb.config.git_repo_regex, pkgbase_name):
            raise aurweb.exceptions.InvalidRepositoryNameException(pkgbase_name)

        # Database entry for the pkgbase.
        with db.begin():
            pkgbase = (
                db.query(PackageBase).filter(PackageBase.Name == pkgbase_name).first()
            )

        # Check if we have write access to the current package (when said
        # package already exists).
        if action == "git-receive-pack" and pkgbase is not None:

            # Get the list of comaintainers for the current package.
            with db.begin():
                comaintainers = (
                    db.query(PackageComaintainer)
                    .filter(PackageComaintainer.PackageBaseID == pkgbase.ID)
                    .all()
                )
                comaintainer_names = [
                    comaintainer.User.Username for comaintainer in comaintainers
                ]
                write_users = comaintainer_names + [pkgbase.Maintainer.Username]

            if not privileged and username not in write_users:
                raise aurweb.exceptions.PermissionDeniedException(username)

        if not os.access(git_update_cmd, os.R_OK | os.X_OK):
            raise aurweb.exceptions.BrokenUpdateHookException(git_update_cmd)

        # If the Git repository doesn't exist, create it an initialize the Git hooks.
        os.environ["AUR_USER"] = username
        os.environ["AUR_PKGBASE"] = pkgbase_name
        git_repo_path = f"{aurweb.config.git_repo_path}/{pkgbase_name}"

        if os.path.exists(git_repo_path) is False:
            os.mkdir(git_repo_path)
            subprocess.run(
                ["git", "init", "-q", "--bare", git_repo_path],
                stdout=subprocess.DEVNULL,
            )
            os.symlink(git_update_cmd, f"{git_repo_path}/hooks/update")

        # If we're cloning and the pkgbase exists, update the clone counter for
        # the pkgbase.
        if action == "git-upload-pack" and pkgbase is not None:
            with db.begin():
                pkgbase.NumGitPulls += 1

        # Run the requested command.
        subprocess.run([git_shell_cmd, "-c", f"{action} '{git_repo_path}'"])

    # Show an error for anything else.
    else:
        msg = "invalid command: {:s}".format(action)
        raise aurweb.exceptions.InvalidArgumentsException(msg)


def _main():
    user = os.environ.get("AUR_USER")
    privileged = os.environ.get("AUR_PRIVILEGED", "0") == "1"
    ssh_cmd = os.environ.get("SSH_ORIGINAL_COMMAND")
    ssh_client = os.environ.get("SSH_CLIENT")

    if not ssh_cmd:
        die("Interactive shell is disabled.")

    cmdargv = shlex.split(ssh_cmd)
    action = cmdargv[0]
    remote_addr = ssh_client.split(" ")[0] if ssh_client else None

    try:
        serve(action, cmdargv, user, privileged, remote_addr)
    except aurweb.exceptions.MaintenanceException:
        die("The AUR is down due to maintenance. We will be back soon.")
    except aurweb.exceptions.BannedException:
        die("The SSH interface is disabled for your IP address.")
    except aurweb.exceptions.InvalidArgumentsException as e:
        die("{:s}: {}".format(action, e))
    except aurweb.exceptions.AurwebException as e:
        die("{:s}: {}".format(action, e))


def set_sentry_context():
    sentry_sdk.set_context(
        "Environment",
        {
            "AUR_USER": os.environ.get("AUR_USER"),
            "SSH_ORIGINAL_COMMAND": os.environ.get("SSH_ORIGINAL_COMMAND"),
        },
    )


def main():
    with push_scope() as scope:  # noqa: F841
        set_sentry_context()
        aurweb.sentry.run_fn(_main, die_unknown_error)


if __name__ == "__main__":
    main()
