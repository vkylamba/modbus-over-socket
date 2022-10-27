import os

import requests

API_BASE = 'https://data.okosengineering.com'
HEARTBEAT_PATH = '/api/heartbeat/'
DEVICE_PATH = '/api/devices/'
DATA_PATH = '/api/data/'

API_KEY = os.environ.get('DEVICE_API_KEY')

class APILogger:

    def __init__(self):
        self.device_token = API_KEY

    def log_heartbeat(self, dev_name):
        try:
            url = f"{API_BASE}{HEARTBEAT_PATH}"
            response = requests.post(
                url,
                json={
                    "mac": dev_name
                }
            )
            if response.status_code not in [200, 201]:
                print("Failed to post heartbeat data", response.status_code, response.text)
        except Exception as ex:
            print("Failed to post heartbeat data", ex)

    def log(self, data):
        print("Input data is: ", data)
        try:
            url = f"{API_BASE}{DATA_PATH}"
            response = requests.post(
                url,
                json=data,
                headers={
                    'Device': self.device_token
                }
            )
            if response.status_code not in [200, 201]:
                # print("Failed to post device data", response.status_code, response.text)
                print("Failed to post device data", response.status_code)
        except Exception as ex:
            print("Failed to post device data", ex)


if __name__ == "__main__":
    logger = APILogger()
    # logger.log_heartbeat("htbt-statcon-hbd")
    logger.log({"asctime": "2022-10-27 11:33:18,695", "msg": "key: vfd_master_switch_state, Register: 1000, Value: 0"})
