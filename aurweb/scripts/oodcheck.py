"""
Checks Repology to provide automatic out of date notifications for package maintainers.
"""
import asyncio

import aiohttp
import orjson

from aurweb import config, db, time
from aurweb.models.package_base import PackageBase
from aurweb.models.user import User
from aurweb.scripts.notify import FlagNotification


async def make_request(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()


async def oodcheck():
    repology_url = "repology.org"
    bot_user = config.get("options", "bot-user")
    packages = db.query(PackageBase).filter(PackageBase.RepologyCheck == 1).all()
    bot = db.query(User).filter(User.Username == bot_user).first()

    repology_packages = await make_request(
        f"https://{repology_url}/api/v1/projects/?inrepo=mpr"
    )
    repology_packages = orjson.loads(repology_packages)

    for pkgbase in packages:
        for pkg_key in repology_packages.keys():
            repology_pkg = repology_packages[pkg_key]

            for repo in repology_pkg:
                if repo["repo"] != "mpr":
                    continue
                elif repo["srcname"] != pkgbase.Name:
                    continue

                if repo["status"] == "outdated":
                    now = time.utcnow()

                    # Don't mark the package as out of date if it already is such.
                    if pkgbase.Flagger is not None:
                        continue

                    # Mark the package as out of date in the db.
                    with db.begin():
                        pkgbase.OutOfDateTS = now
                        pkgbase.Flagger = bot
                        pkgbase.FlaggerComment = (
                            "Package marked out of date on Repology - "
                            + f"https://{repology_url}/project/{pkgbase.Name}/versions"
                        )

                    # Send a notification to the maintainer and comaintainers if needed.
                    FlagNotification(pkgbase.Maintainer.ID, pkgbase.ID)


def main():
    asyncio.run(oodcheck())
