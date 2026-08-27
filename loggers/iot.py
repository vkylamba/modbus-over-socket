import os

import requests

API_BASE = 'http://iot.okosengineering.com'
HEARTBEAT_PATH = '/api/heartbeat/'
DEVICE_PATH = '/api/devices/'
DATA_PATH = '/api/data/'
LOG_PREFIX = '[IoTLogger]'

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
            print(
                f"{LOG_PREFIX} Skipping IoT heartbeat post: device token is missing. "
                f"Expected env key '{self.api_key_env}' to be set."
            )
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
                print(f"{LOG_PREFIX} Failed to post heartbeat data to IoT-E", response.status_code, response.text)
        except Exception as ex:
            print(f"{LOG_PREFIX} Failed to post heartbeat data", ex)

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
                print(
                    f"{LOG_PREFIX} Skipping IoT data post: device token is missing. "
                    f"Expected env key '{self.api_key_env}' to be set."
                )
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
                    print(f"{LOG_PREFIX} Failed to post device data to IoT-E", response.status_code)
            except Exception as ex:
                print(f"{LOG_PREFIX} Failed to post device data", ex)

    def log_json(self, payload):
        if not self.device_token:
            print(
                f"{LOG_PREFIX} Skipping IoT JSON post: device token is missing. "
                f"Expected env key '{self.api_key_env}' to be set."
            )
            return
        if payload is None:
            print(
                f"{LOG_PREFIX} Skipping IoT JSON post: payload is null."
            )
            return
        if not payload:
            print(f"{LOG_PREFIX} Skipping IoT JSON post: payload is empty.")
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
                print(
                    f"{LOG_PREFIX} Failed to post json payload to IoT-E",
                    response.status_code,
                    response.text
                )
        except Exception as ex:
            print(f"{LOG_PREFIX} Failed to post json payload", ex)


if __name__ == "__main__":
    logger = APILogger()
    # logger.log_heartbeat("htbt-statcon-hbd")
    logger.log({"asctime": "2022-10-27 11:33:18,695", "msg": "key: vfd_master_switch_state, Register: 1000, Value: 0"})
