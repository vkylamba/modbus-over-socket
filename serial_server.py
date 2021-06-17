import sys

from serial_client_handler import ClientHandler

# Create a TCP/IP socket
# config_file = "config-files/statcon_hbd_conf_modbus.json"
config_file = "config-files/device_conf_modbus.json"


while True:
    try:
        client_handler = ClientHandler(
            config_file
        )
        client_handler.serve()
    except Exception as e:
        # print(e)
        raise e
