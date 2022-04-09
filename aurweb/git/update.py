#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import time

import pygit2
from makedeb_srcinfo import SrcinfoParser

import aurweb.config
from aurweb import db
from aurweb.models.dependency_type import DependencyType
from aurweb.models.license import License
from aurweb.models.package import Package
from aurweb.models.package_base import PackageBase
from aurweb.models.package_blacklist import PackageBlacklist
from aurweb.models.package_dependency import PackageDependency
from aurweb.models.package_license import PackageLicense
from aurweb.models.package_notification import PackageNotification
from aurweb.models.package_relation import PackageRelation
from aurweb.models.package_source import PackageSource
from aurweb.models.relation_type import RelationType
from aurweb.models.user import User

notify_cmd = aurweb.config.get("notifications", "notify-cmd")

repo_path = aurweb.config.get("serve", "repo-path")
repo_regex = aurweb.config.get("serve", "repo-regex")

max_blob_size = aurweb.config.getint("update", "max-blob-size")


def get_version(pkgver, pkgrel, epoch):
    if epoch is not None:
        return f"{epoch}:{pkgver}-{pkgrel}"
    else:
        return f"{pkgver}-{pkgrel}"


def size_humanize(num):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]:
        if abs(num) < 2048.0:
            if isinstance(num, int):
                return "{}{}".format(num, unit)
            else:
                return "{:.2f}{}".format(num, unit)
        num /= 1024.0
    return "{:.2f}{}".format(num, "YiB")


def parse_dep(depstring):
    dep, _, desc = depstring.partition(": ")
    depname = re.sub(r"(<|=|>).*", "", dep)
    depcond = dep[len(depname) :]

    return (depname, desc, depcond)


def create_pkgbase(pkgbase_name, user):
    now = int(time.time())

    with db.begin():
        pkgbase = db.create(
            PackageBase,
            Name=pkgbase_name,
            SubmittedTS=now,
            ModifiedTS=now,
            SubmitterUID=user.ID,
            MaintainerUID=user.ID,
        )

    with db.begin():
        db.create(PackageNotification, PackageBaseID=pkgbase.ID, UserID=user.ID)

    return pkgbase


def save_metadata(srcinfo, user):  # noqa: C901
    pkgbase = srcinfo.get_variable("pkgbase")[0]
    pkgname = srcinfo.get_variable("pkgname")
    pkgver = srcinfo.get_variable("pkgver")[0]
    pkgrel = srcinfo.get_variable("pkgrel")[0]
    epoch = srcinfo.get_variable("epoch")
    pkgdesc = srcinfo.get_variable("pkgdesc")[0]
    url = srcinfo.get_variable("url")

    # Convert some variables if they weren't set to anything in the SRCINFO file.
    if len(epoch) == 1:
        epoch = epoch[0]
    else:
        epoch = None

    if len(url) == 1:
        url = url[0]
    else:
        url = None

    # Set up the DB for this package.
    with db.begin():
        db_pkgbase = db.query(PackageBase).filter(PackageBase.Name == pkgbase).first()

        was_orphan = db_pkgbase.MaintainerUID is None

        # Update package base details and delete current packages.
        now = int(time.time())

        db_pkgbase.ModifiedTS = now
        db_pkgbase.PackagerUID = user.ID
        db_pkgbase.OutOfDateTS = None
        db_pkgbase.FlaggerComment = ""
        db_pkgbase.FlaggerUID = None

        # If package is an orphan, set the maintainer to the pusher.
        if was_orphan:
            db_pkgbase.MaintainerUID = user.ID

        # Delete all current metadata associated with each pkgname belonging to
        # this pkgbase.
        for pkgname in db_pkgbase.packages:
            for table in (
                PackageSource,
                PackageDependency,
                PackageRelation,
                PackageLicense,
            ):
                matches = db.query(table).filter(table.PackageID == pkgname.ID).all()

                for match in matches:
                    db.delete(match)

        # Delete all pkgnames associated with the pkgbase.
        for pkgname in db_pkgbase.packages:
            db.delete(pkgname)

    # Create each specified pkgname.
    version = get_version(pkgver, pkgrel, epoch)

    for pkg in srcinfo.get_variable("pkgname"):
        with db.begin():
            db_pkgname = db.create(
                Package,
                PackageBaseID=db_pkgbase.ID,
                Name=pkg,
                Version=version,
                Description=pkgdesc,
                URL=url,
            )

        # Add package sources.
        with db.begin():
            for distro, arch in srcinfo.get_extended_variable("source"):
                source_var = srcinfo.construct_extended_variable_name(
                    distro, "source", arch
                )

                for source in srcinfo.get_variable(source_var):
                    db.create(
                        PackageSource,
                        PackageID=db_pkgname.ID,
                        Source=source,
                        SourceArch=arch,
                        SourceDist=distro,
                    )

        # Add package dependencies.
        with db.begin():
            for deptype in ("depends", "makedepends", "checkdepends", "optdepends"):
                dep_id = (
                    db.query(DependencyType)
                    .filter(DependencyType.Name == deptype)
                    .first()
                    .ID
                )

                for distro, arch in srcinfo.get_extended_variable(deptype):
                    dep_var = srcinfo.construct_extended_variable_name(
                        distro, deptype, arch
                    )

                    for dep in srcinfo.get_variable(dep_var):
                        depname, depdesc = srcinfo.split_dep_description(dep)
                        depname, depcond, depver = srcinfo.split_dep_condition(depname)

                        if depcond is not None and depver is not None:
                            depcondition = depcond + depver
                        else:
                            depcondition = None

                        db.create(
                            PackageDependency,
                            PackageID=db_pkgname.ID,
                            DepTypeID=dep_id,
                            DepName=depname,
                            DepDesc=depdesc,
                            DepCondition=depcondition,
                            DepArch=arch,
                            DepDist=distro,
                        )

        # Add package relations (conflicts, provides, replaces).
        with db.begin():
            for reltype in ("conflicts", "provides", "replaces"):
                rel_id = (
                    db.query(RelationType)
                    .filter(RelationType.Name == reltype)
                    .first()
                    .ID
                )

                for distro, arch in srcinfo.get_extended_variable(reltype):
                    rel_var = srcinfo.construct_extended_variable_name(
                        distro, reltype, arch
                    )

                    for rel in srcinfo.get_variable(rel_var):
                        relname, reldesc = srcinfo.split_dep_description(rel)
                        relname, relcond, relver = srcinfo.split_dep_condition(relname)

                        if relcond is not None and relver is not None:
                            relcondition = relcond + relver
                        else:
                            relcondition = None

                    db.create(
                        PackageRelation,
                        PackageID=db_pkgname.ID,
                        RelTypeID=rel_id,
                        RelName=relname,
                        RelCondition=relcondition,
                        RelArch=arch,
                        RelDist=distro,
                    )

            # Add package licenses.
            for license_name in srcinfo.get_variable("license"):
                db_license = (
                    db.query(License).filter(License.Name == license_name).first()
                )

                # If the current license name hasn't been recorded in the
                # Licenses table yet.
                if not db_license:
                    with db.begin():
                        db_license = db.create(License, Name=license_name)

                # Create the package license rows.
                with db.begin():
                    db.create(
                        PackageLicense, PackageID=pkgname.ID, LicenseID=db_license.ID
                    )

    # Add user to notification list on adoption (if they aren't already).
    if was_orphan:
        with db.begin():
            current_notification_length = len(
                db.query(PackageNotification)
                .filter(PackageNotification.PackageBaseID == db_pkgbase.ID)
                .filter(PackageNotification.UserID == user.id)
                .all()
            )

            is_notified = current_notification_length == 1

            if not is_notified:
                db.create(
                    PackageNotification, PackageBaseID=db_pkgbase.ID, UserID=user.ID
                )


def update_notify(user, pkgbase):
    # Execute the notification script.
    subprocess.Popen((notify_cmd, "update", str(user.ID), str(pkgbase.ID)))


def die(msg):
    sys.stderr.write("error: {:s}\n".format(msg))
    exit(1)


def warn(msg):
    sys.stderr.write("warning: {:s}\n".format(msg))


def die_commit(msg, commit):
    sys.stderr.write("error: The following error " + "occurred when parsing commit\n")
    sys.stderr.write("error: {:s}:\n".format(commit))
    sys.stderr.write("error: {:s}\n".format(msg))
    exit(1)


def main():  # noqa: C901
    with db.begin():
        user = (
            db.query(User).filter(User.Username == os.environ.get("AUR_USER")).first()
        )
        env_pkgbase = os.environ.get("AUR_PKGBASE")
        privileged = os.environ.get("AUR_PRIVILEGED", "0") == "1"
        allow_overwrite = (os.environ.get("AUR_OVERWRITE", "0") == "1") and privileged
        repo = pygit2.Repository(f"{repo_path}/{env_pkgbase}")

        warn_or_die = warn if privileged else die

    if len(sys.argv) == 2 and sys.argv[1] == "restore":
        if "refs/heads/master" not in repo.listall_references():
            die("{:s}: repository not found: {:s}".format(sys.argv[1], env_pkgbase))
        refname = "refs/heads/master"
        branchref = "refs/heads/master"
        sha1_old = sha1_new = repo.lookup_reference(branchref).target
    elif len(sys.argv) == 4:
        refname, sha1_old, sha1_new = sys.argv[1:4]
    else:
        die("invalid arguments")

    if refname != "refs/heads/master":
        die("pushing to a branch other than master is restricted")

    # Detect and deny non-fast-forwards.
    if sha1_old != "0" * 40 and not allow_overwrite:
        walker = repo.walk(sha1_old, pygit2.GIT_SORT_TOPOLOGICAL)
        walker.hide(sha1_new)
        if next(walker, None) is not None:
            die("denying non-fast-forward (you should pull first)")

    # Prepare the walker that validates new commits.
    walker = repo.walk(sha1_new, pygit2.GIT_SORT_TOPOLOGICAL)
    if sha1_old != "0" * 40:
        walker.hide(sha1_old)

    # Validate all new commits.
    for commit in walker:
        for fname in (".SRCINFO", "PKGBUILD"):
            if fname not in commit.tree:
                die_commit("missing {:s}".format(fname), str(commit.id))

        for treeobj in commit.tree:
            blob = repo[treeobj.id]

            if isinstance(blob, pygit2.Tree):
                die_commit(
                    "the repository must not contain subdirectories", str(commit.id)
                )

            if not isinstance(blob, pygit2.Blob):
                die_commit("not a blob object: {:s}".format(treeobj), str(commit.id))

            if blob.size > max_blob_size:
                die_commit(
                    "maximum blob size ({:s}) exceeded".format(
                        size_humanize(max_blob_size)
                    ),
                    str(commit.id),
                )

        # Read the SRCINFO file.
        metadata_raw = repo[commit.tree[".SRCINFO"].id].data.decode()
        srcinfo = SrcinfoParser(metadata_raw)

        pkgbase = srcinfo.get_variable("pkgbase")[0]
        pkgname = srcinfo.get_variable("pkgname")
        pkgver = srcinfo.get_variable("pkgver")[0]
        pkgrel = srcinfo.get_variable("pkgrel")[0]
        epoch = srcinfo.get_variable("epoch")
        arch = srcinfo.get_variable("arch")

        if len(epoch) == 1:
            epoch = epoch[0]
        else:
            epoch = None

        # Now lint the SRCINFO file.
        # pkgbase.
        if not re.match(repo_regex, pkgbase):
            die_commit(
                "Invalid .SRCINFO, invalid pkgbase: {:s}".format(pkgbase),
                str(commit.id),
            )

        # pkgname.
        for pkg in pkgname:
            if not re.match(r"[a-z0-9][a-z0-9\.+_-]*$", pkg):
                die_commit(f"Invalid pkgname {pkg}.", str(commit.id))

        # epoch.
        if epoch is not None and not epoch.isdigit():
            die_commit("invalid epoch: {:s}".format(epoch), str(commit.id))

        # Check for the presence of maintainer scripts.
        maintainer_scripts = ("preinst", "postinst", "prerm", "postrm")

        for script_type in maintainer_scripts:
            scripts = srcinfo.get_extended_variable(script_type)

            for distro, arch in scripts:
                script_name = srcinfo.construct_extended_variable_name(
                    distro, script_type, arch
                )
                script = srcinfo.get_variable(script_name)[0]

                if script not in commit.tree:
                    die_commit(f"Missing {script_name} file {script}.", str(commit.id))

        # Check sources.
        source_vars = srcinfo.get_extended_variable("source")

        for distro, arch in source_vars:
            source_name = srcinfo.construct_extended_variable_name(
                distro, "source", arch
            )

            for source in srcinfo.get_variable(source_name):
                if len(source) > 8000:
                    die_commit(
                        f"Source entry for {source_name} is too long.", str(commit.id)
                    )

                if "://" not in source and "lp:" not in source:
                    if source not in commit.tree:
                        die_commit(
                            f"Missing {source_name} file {source}.", str(commit.id)
                        )

    # Display a warning if .SRCINFO is unchanged.
    if sha1_old not in ("0000000000000000000000000000000000000000", sha1_new):
        srcinfo_id_old = repo[sha1_old].tree[".SRCINFO"].id
        srcinfo_id_new = repo[sha1_new].tree[".SRCINFO"].id
        if srcinfo_id_old == srcinfo_id_new:
            warn(".SRCINFO unchanged. " "The package database will not be updated!")

    # Get the pkgbase (from the 'AUR_PKGBASE' environment variable at the top
    # of this function) in the db if it exists.
    db_pkgbase = db.query(PackageBase).filter(PackageBase.Name == env_pkgbase).first()

    # Display a warning if version hasn't been updated.
    version = get_version(pkgver, pkgrel, epoch)

    if db_pkgbase is not None and db_pkgbase.packages[0].Version == version:
        version_updated = False
        warn_or_die(
            "Package version wasn't updated. The database won't be updated with"
            " the new package data."
        )
    else:
        version_updated = True

    # Read .SRCINFO from the HEAD commit.
    metadata_raw = repo[repo[sha1_new].tree[".SRCINFO"].id].data.decode()
    srcinfo = SrcinfoParser(metadata_raw)

    pkgbase = srcinfo.get_variable("pkgbase")[0]
    pkgname = srcinfo.get_variable("pkgname")

    # Ensure that the package base name matches the repository name.
    if pkgbase != env_pkgbase:
        die("invalid pkgbase: {:s}, expected {:s}".format(pkgbase, env_pkgbase))

    # Ensure that packages are neither blacklisted nor overwritten.
    with db.begin():
        blacklist = db.query(PackageBlacklist)

        for pkg in pkgname:
            if blacklist.filter(PackageBlacklist.Name == pkg).first() is not None:
                warn_or_die("Package is blacklisted: {:s}".format(pkg))

            # Overwritten packages would occur in the following scenario:
            # 1. pkgbase 'a' contains pkgnames 'hugo' and 'terraform'.
            # 2. pkgbase 'b' pushes a package with pkgnames 'zebra' and 'terraform'.
            # 3. Likewise, we should block this push of 'b' since it tries to edit
            #    data of the 'terraform' pkgname from the 'a' package.
            overwritten_package = (
                db.query(Package)
                .join(PackageBase)
                .filter(Package.Name == pkg)
                .filter(PackageBase.Name != env_pkgbase)
                .first()
            )

            if overwritten_package is not None:
                die(
                    f"Cannot overwrite package '{overwritten_package.Name}', as"
                    " it's owned by package base "
                    f"'{overwritten_package.PackageBase.Name}'."
                )

    # Create a new package base if it does not exist yet.
    if db_pkgbase is None:
        db_pkgbase = create_pkgbase(pkgbase, user)

    # Update package info if the version was updated.
    if version_updated:
        save_metadata(srcinfo, user)

        # Create a tag for the current package's version if it doesn't currently exist.
        tag_name = f"refs/tags/ver/{version}"

        if not repo.references.get(tag_name):
            repo.references.create(tag_name, sha1_new)

    # Send package update notifications.
    update_notify(user, db_pkgbase)


if __name__ == "__main__":
    main()
