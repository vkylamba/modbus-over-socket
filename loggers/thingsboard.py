import os

import requests

API_KEY = os.environ.get('THINGS_BOARD_DEVICE_KEY')

API_BASE = 'https://demo.thingsboard.io/api/v1/'
DATA_PATH = f'{API_KEY}/telemetry'


class ThingsBoardAPILogger:

    def __init__(self):
        self.device_token = API_KEY

    def log_heartbeat(self, dev_name):
        try:
            url = f"{API_BASE}{DATA_PATH}"
            response = requests.post(
                url,
                json={
                    "type": "heartbeat",
                    "mac": dev_name
                }
            )
            if response.status_code not in [200, 201]:
                print("Failed to post heartbeat data", response.status_code, response.text)
        except Exception as ex:
            print("Failed to post heartbeat data", ex)

    def log(self, data):
        try:
            data["type"] = "data"
            url = f"{API_BASE}{DATA_PATH}"
            response = requests.post(
                url,
                json=data
            )
            if response.status_code not in [200, 201]:
                # print("Failed to post device data", response.status_code, response.text)
                print("Failed to post device data", response.status_code)
        except Exception as ex:
            print("Failed to post device data", ex)


if __name__ == "__main__":
    logger = ThingsBoardAPILogger()
    logger.log_heartbeat("htbt-statcon-hbd")
    # logger.log({"key": "vfd_master_switch_state", "Register": 1000, "Value": 0})
