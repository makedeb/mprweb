#!/usr/bin/env python3
"""
Produces package, package base and user archives for the MPR
database.

See '/mpr-archives' in the web interface for a list of available archives.
"""

import gzip
import os

import orjson

import aurweb.config
from aurweb import db, logging, models
from aurweb.models import Package, PackageBase, User

logger = logging.get_logger("aurweb.scripts.mkpkglists")

archivedir = aurweb.config.get("mkpkglists", "archivedir")
os.makedirs(archivedir, exist_ok=True)

PACKAGES = aurweb.config.get("mkpkglists", "packagesfile")
META = aurweb.config.get("mkpkglists", "packagesmetafile")
META_EXT = aurweb.config.get("mkpkglists", "packagesmetaextfile")
PKGBASE = aurweb.config.get("mkpkglists", "pkgbasefile")
USERS = aurweb.config.get("mkpkglists", "userfile")


TYPE_MAP = {
    "depends": "Depends",
    "makedepends": "MakeDepends",
    "checkdepends": "CheckDepends",
    "optdepends": "OptDepends",
    "conflicts": "Conflicts",
    "provides": "Provides",
    "replaces": "Replaces",
}


def get_packages_v1():
    query = db.query(Package).all()
    pkglist = []

    for pkg in query:
        current_pkg = {}
        current_pkg["ID"] = pkg.ID
        current_pkg["Name"] = pkg.Name
        current_pkg["PackageBaseID"] = pkg.PackageBaseID
        current_pkg["PackageBase"] = pkg.PackageBase.Name
        current_pkg["Version"] = pkg.Version
        current_pkg["Description"] = pkg.Description
        current_pkg["URL"] = pkg.URL
        current_pkg["NumVotes"] = pkg.PackageBase.NumVotes
        current_pkg["Popularity"] = pkg.PackageBase.Popularity
        current_pkg["OutOfDate"] = pkg.PackageBase.OutOfDateTS
        current_pkg["Maintainer"] = (
            pkg.PackageBase.Maintainer
            if pkg.PackageBase.Maintainer is None
            else pkg.PackageBase.Maintainer.Username
        )
        current_pkg["FirstSubmitted"] = pkg.PackageBase.SubmittedTS
        current_pkg["LastModified"] = pkg.PackageBase.ModifiedTS
        current_pkg["URLPath"] = None

        pkglist += [current_pkg]

    return pkglist


def get_dependencies(pkg_id):
    results = {}

    # Base queries so we aren't repeating stuff a lot.
    base_dep_query = (
        db.query(models.PackageDependency)
        .join(models.DependencyType)
        .filter(models.PackageDependency.PackageID == pkg_id)
    )

    base_rel_query = (
        db.query(models.PackageRelation)
        .join(models.RelationType)
        .filter(models.PackageRelation.PackageID == pkg_id)
    )

    # Actual results.
    results["depends"] = base_dep_query.filter(models.DependencyType.Name == "depends")

    results["makedepends"] = base_dep_query.filter(
        models.DependencyType.Name == "makedepends"
    )

    results["checkdepends"] = base_dep_query.filter(
        models.DependencyType.Name == "checkdepends"
    )

    results["optdepends"] = base_dep_query.filter(
        models.DependencyType.Name == "optdepends"
    )

    results["conflicts"] = base_rel_query.filter(
        models.RelationType.Name == "conflicts"
    )

    results["provides"] = base_rel_query.filter(models.RelationType.Name == "provides")

    results["replaces"] = base_rel_query.filter(models.RelationType.Name == "replaces")

    return results


def _main():
    # Produce packages.gz.
    logger.info("Creating 'packages.gz'...")
    query = db.query(Package.Name).all()
    pkglist = "\n".join([pkg[0] for pkg in query]) + "\n"
    archive = gzip.compress(pkglist.encode())

    with open(f"{archivedir}/packages.gz", "bw") as file:
        file.write(archive)

    # Produce pkgbase.gz.
    logger.info("Creating 'pkgbase.gz'...")
    query = db.query(PackageBase.Name).filter(PackageBase.PackagerUID.isnot(None)).all()
    pkglist = "\n".join([pkg[0] for pkg in query]) + "\n"
    archive = gzip.compress(pkglist.encode())

    with open(f"{archivedir}/pkgbase.gz", "bw") as file:
        file.write(archive)

    # Produce users.gz.
    logger.info("Creating 'users.gz'...")
    query = db.query(User.Username).all()
    userlist = "\n".join([user[0] for user in query]) + "\n"
    archive = gzip.compress(userlist.encode())

    with open(f"{archivedir}/pkgbase.gz", "bw") as file:
        file.write(archive)

    # Produce packages-meta-v1.json.gz.
    logger.info("Creating 'packages-meta-v1.json.gz'...")
    pkglist = get_packages_v1()
    archive = gzip.compress(orjson.dumps(pkglist))

    with open(f"{archivedir}/packages-meta-v1.json.gz", "bw") as file:
        file.write(archive)

    # Produce packages-meta-ext-v1.json.gz.
    logger.info("Creating 'packages-meta-ext-v1.json.gz'...")
    pkglist = get_packages_v1()

    for num in range(len(pkglist)):
        pkg = pkglist[num]
        pkg_id = pkg["ID"]
        dependencies = get_dependencies(pkg_id)

        depends = (
            dependencies["depends"]
            # We don't have any dependency variables with extensions in the v1 archives.
            .filter(models.PackageDependency.DepArch == None)  # noqa: E711
            .filter(models.PackageDependency.DepDist == None)  # noqa: E711
            .all()
        )
        makedepends = (
            dependencies["makedepends"]
            .filter(models.PackageDependency.DepArch == None)  # noqa: E711
            .filter(models.PackageDependency.DepDist == None)  # noqa: E711
            .all()
        )
        checkdepends = (
            dependencies["checkdepends"]
            .filter(models.PackageDependency.DepArch == None)  # noqa: E711
            .filter(models.PackageDependency.DepDist == None)  # noqa: E711
            .all()
        )
        optdepends = (
            dependencies["optdepends"]
            .filter(models.PackageDependency.DepArch == None)  # noqa: E711
            .filter(models.PackageDependency.DepDist == None)  # noqa: E711
            .all()
        )
        conflicts = (
            dependencies["conflicts"]
            .filter(models.PackageRelation.RelArch == None)  # noqa: E711
            .filter(models.PackageRelation.RelDist == None)  # noqa: E711
            .all()
        )
        provides = (
            dependencies["provides"]
            .filter(models.PackageRelation.RelArch == None)  # noqa: E711
            .filter(models.PackageRelation.RelDist == None)  # noqa: E711
            .all()
        )
        replaces = (
            dependencies["replaces"]
            .filter(models.PackageRelation.RelArch == None)  # noqa: E711
            .filter(models.PackageRelation.RelDist == None)  # noqa: E711
            .all()
        )

        dependency_mappings = {
            "Depends": depends,
            "MakeDepends": makedepends,
            "CheckDepends": checkdepends,
            "OptDepends": optdepends,
        }

        relationship_mappings = {
            "Conflicts": conflicts,
            "Provides": provides,
            "Replaces": replaces,
        }

        # Add dependencies.
        for dependency, values in dependency_mappings.items():
            if len(values) != 0:
                pkg[dependency] = []

                for dep in values:
                    if dep.DepCondition:
                        pkg[dependency] += [dep.DepName + dep.DepCondition]
                    else:
                        pkg[dependency] += [dep.DepName]

        # Add relationships.
        for relation, values in relationship_mappings.items():
            if len(values) != 0:
                pkg[relation] = []

                for rel in values:
                    if rel.RelCondition:
                        pkg[relation] += [rel.RelName + rel.RelCondition]
                    else:
                        pkg[relation] += [rel.RelName]

    archive = gzip.compress(orjson.dumps(pkglist))

    with open(f"{archivedir}/packages-meta-ext-v1.json.gz", "bw") as file:
        file.write(archive)

    # Produce packages-meta-ext-v2.json.gz.
    logger.info("Creating 'packages-meta-ext-v2.json.gz'...")
    pkglist = get_packages_v1()

    for num in range(len(pkglist)):
        pkg = pkglist[num]
        pkg_id = pkg["ID"]
        dependencies = get_dependencies(pkg_id)

        depends = dependencies["depends"].all()
        makedepends = dependencies["makedepends"].all()
        checkdepends = dependencies["checkdepends"].all()
        optdepends = dependencies["optdepends"].all()
        conflicts = dependencies["optdepends"].all()
        provides = dependencies["provides"].all()
        replaces = dependencies["replaces"].all()

        dependency_mappings = {
            "Depends": depends,
            "MakeDepends": makedepends,
            "CheckDepends": checkdepends,
            "OptDepends": optdepends,
        }

        relationship_mappings = {
            "Conflicts": conflicts,
            "Provides": provides,
            "Replaces": replaces,
        }

        for dependency in dependency_mappings:
            pkg[dependency] = []

        for relation in relationship_mappings:
            pkg[relation] = []

        # Dependencies.
        for dependency, values in dependency_mappings.items():
            dep_mappings = {}

            for dep in values:
                distro = dep.DepDist
                arch = dep.DepArch

                if dep.DepCondition:
                    depname = dep.DepName + dep.DepCondition
                else:
                    depname = dep.DepName

                if (distro, arch) in dep_mappings:
                    dep_mappings[distro, arch] += [depname]
                else:
                    dep_mappings[distro, arch] = [depname]

            for distro, arch in dep_mappings:
                pkg[dependency] += [
                    {
                        "Distro": distro,
                        "Arch": arch,
                        "Packages": dep_mappings[distro, arch],
                    }
                ]

        # Relationships.
        for relationship, values in relationship_mappings.items():
            rel_mappings = {}

            for rel in values:
                distro = rel.RelDist
                arch = rel.RelArch

                if rel.RelCondition:
                    relname = rel.RelName + rel.RelCondition
                else:
                    relname = rel.RelName

                if (distro, arch) in rel_mappings:
                    rel_mappings[distro, arch] += [relname]
                else:
                    rel_mappings[distro, arch] = [relname]

            for distro, arch in rel_mappings:
                pkg[relationship] += [
                    {
                        "Distro": distro,
                        "Arch": arch,
                        "Packages": rel_mappings[distro, arch],
                    }
                ]

    archive = gzip.compress(orjson.dumps(pkglist))

    with open(f"{archivedir}/packages-meta-ext-v2.json.gz", "bw") as file:
        file.write(archive)


def main():
    db.get_engine()
    with db.begin():
        _main()


if __name__ == "__main__":
    main()
