import logging
import logging.config
import os

config_path = os.environ.get("LOG_CONFIG", "/aurweb/logging.conf")

logging.config.fileConfig(config_path, disable_existing_loggers=False)
logging.getLogger("root").addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """A logging.getLogger wrapper. Importing this function and
    using it to get a module-local logger ensures that logging.conf
    initialization is performed wherever loggers are used.

    :param name: Logger name; typically `__name__`
    :returns: name's logging.Logger
    """

    return logging.getLogger(name)
