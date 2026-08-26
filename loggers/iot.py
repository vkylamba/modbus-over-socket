import os

import requests

API_BASE = 'https://iot.okosengineering.com'
HEARTBEAT_PATH = '/api/heartbeat/'
DEVICE_PATH = '/api/devices/'
DATA_PATH = '/api/data/'

class APILogger:

    def __init__(self, api_key_env='DEVICE_API_KEY'):
        self.api_key_env = api_key_env
        self.device_token = os.environ.get(self.api_key_env)
        self.payload = {}

    def set_device_token(self, device_token):
        if self.device_token != device_token:
            self.payload = {}
        self.device_token = device_token

    def set_api_key_env(self, api_key_env):
        self.api_key_env = api_key_env
        self.set_device_token(os.environ.get(self.api_key_env))

    def log_heartbeat(self, dev_name):
        if not self.device_token:
            return
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
            if not self.device_token:
                self.payload = {}
                return
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

    def log_json(self, payload):
        if not self.device_token:
            return
        if not isinstance(payload, dict):
            return
        try:
            url = f"{API_BASE}{DATA_PATH}"
            response = requests.post(
                url,
                json=payload,
                headers={
                    'Device': self.device_token
                }
            )
            if response.status_code not in [200, 201]:
                print("Failed to post json payload to IoT-E", response.status_code)
        except Exception as ex:
            print("Failed to post json payload", ex)


if __name__ == "__main__":
    logger = APILogger()
    # logger.log_heartbeat("htbt-statcon-hbd")
    logger.log({"asctime": "2022-10-27 11:33:18,695", "msg": "key: vfd_master_switch_state, Register: 1000, Value: 0"})
