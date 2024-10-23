import logging
import os
import sys

SOCKET_SERVER_ROOT_PATH = os.environ.get('SOCKET_SERVER_ROOT_PATH', '')
LOG_FILE = os.path.join(SOCKET_SERVER_ROOT_PATH, "logs.txt")

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')

def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)
    return console_handler

def get_file_handler():
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    return file_handler


logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
logger.addHandler(get_console_handler())
logger.addHandler(get_file_handler())
