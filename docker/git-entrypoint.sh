#!/bin/bash
set -eou pipefail

SSHD_CONFIG=/etc/ssh/sshd_config
AUTH_SCRIPT=/app/git-auth.sh

mkdir -p /app
chmod 755 /app

cat >> $AUTH_SCRIPT << EOF
#!/usr/bin/env bash
export PYTHONPATH='/aurweb'
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

# Make sure the Git directory is writable by the 'mpr' user.
chown mpr /aurweb/aur.git -R

# Setup SSH Keys.
ssh-keygen -A

# Star the SSH server.
/docker/scripts/run-sshd.sh
