# License: BSD 3 clause
"""
Functions related to logging in SKLL.

:author: Nitin Madnani (nmadnani@ets.org)
:organization: ETS
"""
import logging
import warnings
from functools import wraps
from logging import FileHandler

orig_showwarning = warnings.showwarning


def get_skll_logger(name, filepath=None, log_level=logging.INFO):
    """
    Create and return logger instances that are appropriate for use
    in SKLL code, e.g., that they can log to both STDERR as well
    as a file. This function will try to reuse any previously created
    logger based on the given name and filepath.

    Parameters
    ----------
    name : str
        The name to be used for the logger.
    filepath : str, optional
        The file to be used for the logger via a FileHandler.
        Default: None in which case no file is attached to the
        logger.
        Defaults to ``None``.
    log_level : str, optional
        The level for logging messages
        Defaults to ``logging.INFO``.

    Returns
    -------
    logger: logging.Logger
        A ``Logger`` instance.
    """

    # first get the logger instance associated with the
    # given name if one already exists
    logger = logging.getLogger(name)

    # if we are given a file path and this existing logger doesn't already
    # have a file handler for this file, then add one.
    if filepath:
        is_file_handler = lambda handler: isinstance(handler, FileHandler) \
                                                and handler.stream.name == filepath
        need_file_handler = not any([is_file_handler(handler) for handler in logger.handlers])
        if need_file_handler:
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler = logging.FileHandler(filepath, mode='w')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            logger.addHandler(file_handler)

    # Make method for sending warnings to the logger
    # and replace warnings.showwarning
    def send_warnings_to_log(message, category, filename, lineno,
                             file=None, line=None):
        logger.warning('{}:{}: {}:{}'.format(filename,
                                             lineno,
                                             category.__name__,
                                             message))
    warnings.showwarning = send_warnings_to_log

    # return the logger instance
    return logger


def close_and_remove_logger_handlers(logger):
    """
    Close and remove any handlers attached to a logger instance.

    Parameters
    ----------
    logger : logging.Logger
        Logger instance

    Returns
    -------
    NoneType
    """

    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)


def warn_once(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("once")
            return func(*args, **kwargs)
    return wrapper
