import os

import requests

API_BASE = 'https://iot.okosengineering.com'
HEARTBEAT_PATH = '/api/heartbeat/'
DEVICE_PATH = '/api/devices/'
DATA_PATH = '/api/data/'

API_KEY = os.environ.get('DEVICE_API_KEY')

class APILogger:

    def __init__(self):
        self.device_token = API_KEY
        self.payload = {}

    def log_heartbeat(self, dev_name):
        try:
            url = f"{API_BASE}{HEARTBEAT_PATH}"
            response = requests.post(
                url,
                json={
                    "mac": dev_name
                },
                headers={
                    'Device': self.device_token
                }
            )
            if response.status_code not in [200, 201]:
                print("Failed to post heartbeat data to IoT-E", response.status_code, response.text)
        except Exception as ex:
            print("Failed to post heartbeat data", ex)

    def log(self, data, push_to_server=True):
        """
            Following keys are expected in the data dict:
                key
                register
                value
        """
        if not push_to_server:
            key_name = data.get("key")
            key_val = data.get("value")
            if key_name is not None:
                self.payload[key_name] = key_val
        else:
            try:
                url = f"{API_BASE}{DATA_PATH}"
                response = requests.post(
                    url,
                    json=self.payload,
                    headers={
                        'Device': self.device_token
                    }
                )
                if response.status_code not in [200, 201]:
                    self.payload = {}
                    # print("Failed to post device data", response.status_code, response.text)
                    print("Failed to post device data to IoT-E", response.status_code)
            except Exception as ex:
                print("Failed to post device data", ex)


if __name__ == "__main__":
    logger = APILogger()
    # logger.log_heartbeat("htbt-statcon-hbd")
    logger.log({"asctime": "2022-10-27 11:33:18,695", "msg": "key: vfd_master_switch_state, Register: 1000, Value: 0"})
