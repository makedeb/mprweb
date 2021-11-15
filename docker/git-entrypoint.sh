#!/bin/bash
set -eou pipefail

SSHD_CONFIG=/etc/ssh/sshd_config
AUTH_SCRIPT=/app/git-auth.sh

GIT_REPO=/aurweb/aur.git
GIT_BRANCH=master # 'Master' branch.

if ! grep -q 'PYTHONPATH' /etc/environment; then
    echo "PYTHONPATH='/aurweb:/aurweb/app'" >> /etc/environment
else
    sed -ri "s|^(PYTHONPATH)=.*$|\1='/aurweb'|" /etc/environment
fi

if ! grep -q 'AUR_CONFIG' /etc/environment; then
    echo "AUR_CONFIG='/aurweb/conf/config'" >> /etc/environment
else
    sed -ri "s|^(AUR_CONFIG)=.*$|\1='/aurweb/conf/config'|" /etc/environment
fi

mkdir -p /app
chmod 755 /app

cat >> $AUTH_SCRIPT << EOF
#!/usr/bin/env bash
export AUR_CONFIG="$AUR_CONFIG"
exec /usr/bin/aurweb-git-auth "\$@"
EOF
chmod 755 $AUTH_SCRIPT

# Add AUR SSH config.
cat >> $SSHD_CONFIG << EOF
Match User mpr
    PasswordAuthentication no
    AuthorizedKeysCommand $AUTH_SCRIPT "%t" "%k"
    AuthorizedKeysCommandUser mpr
    AcceptEnv AUR_OVERWRITE
EOF

# Setup a config for our mysql db.
cp -vf "${CONFIG_FILE}" $AUR_CONFIG
sed -i "s;YOUR_AUR_ROOT;$(pwd);g" $AUR_CONFIG

# Set some defaults needed for pathing and ssh uris.
sed -ri "s|^(repo-path) = .+|\1 = /aurweb/aur.git/|" $AUR_CONFIG

# Setup SSH Keys.
if (( "${GENERATE_SSH_KEYS:-1}" )); then
    ssh-keygen -A
fi

# Taken from INSTALL.
mkdir -pv $GIT_REPO

# Initialize git repository.
if [ ! -f $GIT_REPO/config ]; then
    curdir="$(pwd)"
    cd $GIT_REPO
    git config --global init.defaultBranch $GIT_BRANCH
    git init --bare
    git config --local transfer.hideRefs '^refs/'
    git config --local --add transfer.hideRefs '!refs/'
    git config --local --add transfer.hideRefs '!HEAD'
    ln -sf /usr/bin/aurweb-git-update hooks/update
    cd $curdir
    chown -R mpr:mpr $GIT_REPO
fi

exec "$@"
