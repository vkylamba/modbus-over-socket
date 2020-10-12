import sys
import logging


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    return console_handler


logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)
logger.addHandler(get_console_handler())
