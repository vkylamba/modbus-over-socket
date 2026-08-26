import os

import requests

API_BASE = 'https://demo.thingsboard.io/api/v1/'


class ThingsBoardAPILogger:

    def __init__(self, device_key_env='THINGS_BOARD_DEVICE_KEY'):
        self.device_key_env = device_key_env
        self.device_token = os.environ.get(self.device_key_env)

    def _data_path(self):
        return f'{self.device_token}/telemetry'

    def log_heartbeat(self, dev_name):
        if not self.device_token:
            return
        try:
            url = f"{API_BASE}{self._data_path()}"
            response = requests.post(
                url,
                json={
                    "type": "heartbeat",
                    "mac": dev_name
                }
            )
            if response.status_code not in [200, 201]:
                print("Failed to post heartbeat data to things board", response.status_code, response.text)
        except Exception as ex:
            print("Failed to post heartbeat data", ex)

    def log(self, data):
        if not self.device_token:
            return
        try:
            data["type"] = "data"
            url = f"{API_BASE}{self._data_path()}"
            response = requests.post(
                url,
                json=data
            )
            if response.status_code not in [200, 201]:
                # print("Failed to post device data", response.status_code, response.text)
                print("Failed to post device data to things board", response.status_code)
        except Exception as ex:
            print("Failed to post device data", ex)


if __name__ == "__main__":
    logger = ThingsBoardAPILogger()
    logger.log_heartbeat("htbt-statcon-hbd")
    # logger.log({"key": "vfd_master_switch_state", "Register": 1000, "Value": 0})
