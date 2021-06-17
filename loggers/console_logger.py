import sys
import logging


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    return console_handler

def get_file_handler():
    file_handler = logging.FileHandler("logs.txt")
    return file_handler


logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)
logger.addHandler(get_console_handler())
logger.addHandler(get_file_handler())
