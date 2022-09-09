import configparser
import os
from typing import Any

mprweb_dir = "/aurweb"
_mpr_config = os.environ.get("MPR_CONFIG", "/mprweb.cfg")
_parser = None
valid_keytypes = ["ssh-rsa" "ssh-dss" "ecdsa-sha2-nistp256" "ecdsa-sha2-nistp384" "ecdsa-sha2-nistp521" "ssh-ed25519" "sk-ecdsa-sha2-nistp256@openssh.com" "sk-ecdsa-sha2-nistp256-cert-v01@openssh.com" "sk-ssh-ed25519@openssh.com" "sk-ssh-ed25519-cert-v01@openssh.com"]
git_repo_path = "/aurweb/aur.git"
git_repo_regex = "[a-z0-9][a-z0-9.+_-]*$"

def _get_parser():
    global _parser

    if not _parser:
        _parser = configparser.RawConfigParser()
        _parser.optionxform = lambda option: option
        _parser.read(_mpr_config)

    return _parser


def rehash():
    """Globally rehash the configuration parser."""
    global _parser
    _parser = None
    _get_parser()


def get_with_fallback(section, option, fallback):
    return _get_parser().get(section, option, fallback=fallback)


def get(section, option):
    return _get_parser().get(section, option)


def getboolean(section, option):
    return _get_parser().getboolean(section, option)


def getint(section, option, fallback=None):
    return _get_parser().getint(section, option, fallback=fallback)


def get_section(section):
    if section in _get_parser().sections():
        return _get_parser()[section]


def unset_option(section: str, option: str) -> None:
    _get_parser().remove_option(section, option)


def set_option(section: str, option: str, value: Any) -> None:
    _get_parser().set(section, option, value)
    return value


def save() -> None:
    with open(_mpr_config, "w") as fp:
        _get_parser().write(fp)
