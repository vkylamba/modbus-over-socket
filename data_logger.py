import sys
import logging
from json import dumps
from collections import OrderedDict
from logging import Formatter
from logging.handlers import TimedRotatingFileHandler

FORMAT = '%(asctime)-15s %(message)s'
FORMATTER = logging.Formatter(FORMAT)
LOG_FILE = "data.json"


class JSONFormatter(Formatter):
    """
        JSONFormatter
    """

    def __init__(self, recordfields=[], datefmt=None, customjson=None):
        Formatter.__init__(self, None, datefmt)
        self.recordfields = recordfields
        self.customjson = customjson

    def usesTime(self):
        return 'asctime' in self.recordfields

    def _formattime(self, record):
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)

    def _getjsondata(self, record):
        if (len(self.recordfields) > 0):
            fields = []
            for x in self.recordfields:
                fields.append((x, getattr(record, x)))
            fields.append(('msg', record.msg))
            return OrderedDict(fields)
        else:
            return record.msg

    def format(self, record):
        self._formattime(record)
        jsondata = self._getjsondata(record)
        try:
            formattedjson = dumps(jsondata, cls=self.customjson)
        except Exception as e:
            return ''
        return formattedjson


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    return console_handler


def get_file_handler():
    file_handler = TimedRotatingFileHandler(LOG_FILE, when='midnight')
    file_handler.setFormatter(JSONFormatter(['asctime', 'message']))
    return file_handler


logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)
logger.addHandler(get_console_handler())
logger.addHandler(get_file_handler())
