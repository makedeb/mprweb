#!/usr/bin/env python3

import shlex
import sys

import aurweb.config
from aurweb import db
from aurweb.models.ssh_pub_key import SSHPubKey

git_serve_cmd = "/usr/bin/aurweb-git-serve"
ssh_opts = "restrict"

def format_command(env_vars, command, ssh_opts, ssh_key):
    environment = ""
    for key, var in env_vars.items():
        environment += "{}={} ".format(key, shlex.quote(var))

    command = shlex.quote(command)
    command = "{}{}".format(environment, command)

    # The command is being substituted into an authorized_keys line below,
    # so we need to escape the double quotes.
    command = command.replace('"', '\\"')
    msg = 'command="{}",{} {}'.format(command, ssh_opts, ssh_key)
    return msg


def main():
    keytype = sys.argv[1]
    keytext = sys.argv[2]
    if keytype not in aurweb.config.valid_keytypes:
        exit(1)

    pubkey = keytype + " " + keytext

    with db.begin():
        ssh_key = db.query(SSHPubKey).filter(SSHPubKey.PubKey == pubkey).first()

    # If we couldn't find the SSH key for the current user.
    if ssh_key is None:
        exit(1)

    # If the user is suspended or doesn't have a password set.
    user = ssh_key.User

    if user.Suspended or user.Passwd == "":
        exit(1)

    env_vars = {
        "AUR_USER": user.Username,
        "AUR_PRIVILEGED": "1" if user.AccountTypeID > 1 else "0",
    }

    print(format_command(env_vars, git_serve_cmd, ssh_opts, pubkey))


if __name__ == "__main__":
    main()
