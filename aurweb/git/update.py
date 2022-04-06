#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import time

import pygit2
import srcinfo.parse
import srcinfo.utils

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


def size_humanize(num):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]:
        if abs(num) < 2048.0:
            if isinstance(num, int):
                return "{}{}".format(num, unit)
            else:
                return "{:.2f}{}".format(num, unit)
        num /= 1024.0
    return "{:.2f}{}".format(num, "YiB")


def extract_arch_fields(pkginfo, field):
    values = []

    if field in pkginfo:
        for val in pkginfo[field]:
            values.append({"value": val, "arch": None})

    for arch in pkginfo["arch"]:
        if field + "_" + arch in pkginfo:
            for val in pkginfo[field + "_" + arch]:
                values.append({"value": val, "arch": arch})

    return values


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


def save_metadata(metadata, user):  # noqa: C901
    with db.begin():
        pkgbase = (
            db.query(PackageBase)
            .filter(PackageBase.Name == metadata["pkgbase"])
            .first()
        )
        was_orphan = pkgbase.MaintainerUID is None

        # Update package base details and delete current packages.
        now = int(time.time())

        pkgbase.ModifiedTS = (now,)
        pkgbase.PackagerUID = (user.ID,)
        pkgbase.OutOfDateTS = (None,)
        pkgbase.FlaggerComment = ("",)
        pkgbase.FlaggerUID = None

        # If package is an orphan, set the maintainer to the pusher.
        if was_orphan:
            pkgbase.MaintainerUID = user.ID

        # Delete all current metadata associated with each pkgname belonging to
        # this pkgbase.
        for pkgname in pkgbase.packages:
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
        for pkgname in pkgbase.packages:
            db.delete(pkgname)

    # Create each specified pkgname.
    for pkgname in srcinfo.utils.get_package_names(metadata):
        pkginfo = srcinfo.utils.get_merged_package(pkgname, metadata)

        # Get version.
        if "epoch" in pkginfo and int(pkginfo["epoch"]) > 0:
            version = "{:d}:{:s}-{:s}".format(
                int(pkginfo["epoch"]), pkginfo["pkgver"], pkginfo["pkgrel"]
            )
        else:
            version = "{:s}-{:s}".format(pkginfo["pkgver"], pkginfo["pkgrel"])

        # Set pkgdesc and url if not set.
        for field in ("pkgdesc", "url"):
            if field not in pkginfo:
                pkginfo[field] = None

        # Create the pkgname.
        with db.begin():
            pkgname = db.create(
                Package,
                PackageBaseID=pkgbase.ID,
                Name=pkginfo["pkgname"],
                Version=version,
                Description=pkginfo["pkgdesc"],
                URL=pkginfo["url"],
            )

        # Add package sources.
        with db.begin():
            for source_info in extract_arch_fields(pkginfo, "source"):
                db.create(
                    PackageSource,
                    PackageID=pkgname.ID,
                    Source=source_info["value"],
                    SourceArch=source_info["arch"],
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

                for dep_info in extract_arch_fields(pkginfo, deptype):
                    depname, depdesc, depcond = parse_dep(dep_info["value"])
                    deparch = dep_info["arch"]

                    db.create(
                        PackageDependency,
                        PackageID=pkgname.ID,
                        DepTypeID=dep_id,
                        DepName=depname,
                        DepDesc=depdesc,
                        DepCondition=depcond,
                        DepArch=deparch,
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

                for rel_info in extract_arch_fields(pkginfo, reltype):
                    relname, _, relcond = parse_dep(rel_info["value"])
                    relarch = rel_info["arch"]

                    db.create(
                        PackageRelation,
                        PackageID=pkgname.ID,
                        RelTypeID=rel_id,
                        RelName=relname,
                        RelCondition=relcond,
                        RelArch=relarch,
                    )

        # Add package licenses.
        if "license" in pkginfo:
            for license_name in pkginfo["license"]:
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
                .filter(PackageNotification.PackageBaseID == pkgbase.ID)
                .filter(PackageNotification.UserID == user.id)
                .all()
            )

            is_notified = current_notification_length == 1

            if not is_notified:
                db.create(PackageNotification, PackageBaseID=pkgbase.ID, UserID=user.ID)


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
        pkgbase = os.environ.get("AUR_PKGBASE")
        privileged = os.environ.get("AUR_PRIVILEGED", "0") == "1"
        allow_overwrite = (os.environ.get("AUR_OVERWRITE", "0") == "1") and privileged
        repo = pygit2.Repository(f"{repo_path}/{pkgbase}")

        warn_or_die = warn if privileged else die

    if len(sys.argv) == 2 and sys.argv[1] == "restore":
        if "refs/heads/master" not in repo.listall_references():
            die("{:s}: repository not found: {:s}".format(sys.argv[1], pkgbase))
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

        metadata_raw = repo[commit.tree[".SRCINFO"].id].data.decode()
        (metadata, errors) = srcinfo.parse.parse_srcinfo(metadata_raw)
        if errors:
            sys.stderr.write(
                "error: The following errors occurred "
                "when parsing .SRCINFO in commit\n"
            )
            sys.stderr.write("error: {:s}:\n".format(str(commit.id)))
            for error in errors:
                for err in error["error"]:
                    sys.stderr.write(
                        "error: line {:d}: {:s}\n".format(error["line"], err)
                    )
            exit(1)

        try:
            metadata_pkgbase = metadata["pkgbase"]
        except KeyError:
            die_commit(
                "invalid .SRCINFO, does not contain a pkgbase (is the file empty?)",
                str(commit.id),
            )
        if not re.match(repo_regex, metadata_pkgbase):
            die_commit("invalid pkgbase: {:s}".format(metadata_pkgbase), str(commit.id))

        if not metadata["packages"]:
            die_commit("missing pkgname entry", str(commit.id))

        for pkgname in set(metadata["packages"].keys()):
            pkginfo = srcinfo.utils.get_merged_package(pkgname, metadata)

            for field in ("pkgver", "pkgrel", "pkgname"):
                if field not in pkginfo:
                    die_commit(
                        "missing mandatory field: {:s}".format(field), str(commit.id)
                    )

            if "epoch" in pkginfo and not pkginfo["epoch"].isdigit():
                die_commit(
                    "invalid epoch: {:s}".format(pkginfo["epoch"]), str(commit.id)
                )

            if not re.match(r"[a-z0-9][a-z0-9\.+_-]*$", pkginfo["pkgname"]):
                die_commit(
                    "invalid package name: {:s}".format(pkginfo["pkgname"]),
                    str(commit.id),
                )

            max_len = {"pkgname": 255, "pkgdesc": 255, "url": 8000}
            for field in max_len.keys():
                if field in pkginfo and len(pkginfo[field]) > max_len[field]:
                    die_commit(
                        "{:s} field too long: {:s}".format(field, pkginfo[field]),
                        str(commit.id),
                    )

            for field in ("install", "changelog"):
                if field in pkginfo and not pkginfo[field] in commit.tree:
                    die_commit(
                        "missing {:s} file: {:s}".format(field, pkginfo[field]),
                        str(commit.id),
                    )

            for field in extract_arch_fields(pkginfo, "source"):
                fname = field["value"]
                if len(fname) > 8000:
                    die_commit(
                        "source entry too long: {:s}".format(fname), str(commit.id)
                    )
                if "://" in fname or "lp:" in fname:
                    continue
                if fname not in commit.tree:
                    die_commit(
                        "missing source file: {:s}".format(fname), str(commit.id)
                    )

    # Display a warning if .SRCINFO is unchanged.
    if sha1_old not in ("0000000000000000000000000000000000000000", sha1_new):
        srcinfo_id_old = repo[sha1_old].tree[".SRCINFO"].id
        srcinfo_id_new = repo[sha1_new].tree[".SRCINFO"].id
        if srcinfo_id_old == srcinfo_id_new:
            warn(".SRCINFO unchanged. " "The package database will not be updated!")

    # Read .SRCINFO from the HEAD commit.
    metadata_raw = repo[repo[sha1_new].tree[".SRCINFO"].id].data.decode()
    (metadata, errors) = srcinfo.parse.parse_srcinfo(metadata_raw)

    # Ensure that the package base name matches the repository name.
    metadata_pkgbase = metadata["pkgbase"]
    if metadata_pkgbase != pkgbase:
        die("invalid pkgbase: {:s}, expected {:s}".format(metadata_pkgbase, pkgbase))

    # Ensure that packages are neither blacklisted nor overwritten.
    with db.begin():
        # Some of these functions require some kind of pkgbase to be given,
        # which wont work with the pkgbase function below when the pkgbase
        # doesn't exist yet.
        pkgbase_name = metadata["pkgbase"]
        pkgbase = db.query(PackageBase).filter(PackageBase.Name == pkgbase_name).first()
        blacklist = db.query(PackageBlacklist)

        for pkgname in srcinfo.utils.get_package_names(metadata):
            pkginfo = srcinfo.utils.get_merged_package(pkgname, metadata)
            pkgname = pkginfo["pkgname"]

            if blacklist.filter(PackageBlacklist.Name == pkgname).first() is not None:
                warn_or_die("package is blacklisted: {:s}".format(pkgname))

        # Overwritten packages would occur in the following scenario:
        # 1. pkgbase 'a' contains pkgnames 'hugo' and 'terraform'.
        # 2. pkgbase 'b' pushes a package with pkgnames 'zebra' and 'terraform'.
        # 3. Likewise, we should block this push of 'b' since it tries to edit
        #    data of the 'terraform' pkgname from the 'a' package.
        overwritten_packages = (
            db.query(Package)
            .join(PackageBase)
            .filter(Package.Name == pkgname)
            .filter(PackageBase.Name != pkgbase_name)
            .all()
        )

        if len(overwritten_packages) > 0:
            die("cannot overwrite package: {:s}".format(pkgname))

    # Create a new package base if it does not exist yet.
    if pkgbase is None:
        pkgbase = create_pkgbase(pkgbase_name, user)

    # Store package base details in the database.
    save_metadata(metadata, user)

    # Create (or update) a branch with the name of the package base for better
    # accessibility.
    branchref = "refs/heads/master"
    repo.create_reference(branchref, sha1_new, True)

    # Create a tag for the current package's version if it doesn't currently exist.
    if "epoch" in metadata and int(pkginfo["epoch"]) > 0:
        version = "{:d}!{:s}-{:s}".format(
            int(metadata["epoch"]), metadata["pkgver"], metadata["pkgrel"]
        )
    else:
        version = "{:s}-{:s}".format(metadata["pkgver"], metadata["pkgrel"])

    tag_name = f"refs/tags/ver/{version}"

    if not repo.references.get(tag_name):
        repo.references.create(tag_name, sha1_new)

    # Send package update notifications.
    update_notify(user, pkgbase)


if __name__ == "__main__":
    main()
