#!/bin/bash
# Install Arch Linux dependencies. This is centralized here
# for CI and Docker usage and should always reflect the most
# robust development ecosystem.
set -eou pipefail

# Update and rollout archlinux-keyring keys.
pacman-key --init
pacman-key --updatedb
pacman-key --populate

pacman -Sy --noconfirm --noprogressbar archlinux-keyring

# Install other OS dependencies.
pacman -Syu --noconfirm --noprogressbar \
    --cachedir .pkg-cache git gpgme nginx redis openssh \
    mariadb mariadb-libs cgit-aurweb uwsgi uwsgi-plugin-cgi \
    memcached python-pip pyalpm python-srcinfo curl libeatmydata \
    cronie step-cli step-ca words fortune-mod asciidoc npm

# Install needed npm packages.
npm install -g sass

exec "$@"

# vim: set sw=4 expandtab:
