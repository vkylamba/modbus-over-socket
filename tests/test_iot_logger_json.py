import os
import unittest
from unittest.mock import patch

from loggers.iot import APILogger


class APILoggerJsonTest(unittest.TestCase):
    def test_log_json_accepts_quoted_json_payload(self):
        os.environ['DEVICE_API_KEY'] = 'token-123'
        logger = APILogger()
        captured = {}

        class DummyResponse:
            status_code = 200
            text = 'ok'

        def fake_post(url, json, headers):
            captured['payload'] = json
            return DummyResponse()

        with patch('requests.post', side_effect=fake_post):
            logger.log_json('"{\\"sensor\\":\\"temp\\",\\"value\\":42}"')
            logger.log_json('{"sensor": "temp", "value": 42}')

        self.assertEqual(captured['payload'], {'sensor': 'temp', 'value': 42})


if __name__ == '__main__':
    unittest.main()
