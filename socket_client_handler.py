import json
import os
from datetime import datetime, timedelta

from constants import (DELTA_RPI, DELTA_RPI_INVERTER_HEARTBEAT, MODBUS_RTU,
                       SHAKTI_SOLAR_VFD_HEARTBEAT,
                       STATCON_HBD_INVERTER_HEARTBEAT)
from delta.data_parser import DeltaDataParser
from delta.instrument import DeltaInstrument
from loggers.console_logger import logger
from loggers.data_logger import logger as datalogger
from loggers.iot import APILogger
from loggers.thingsboard import ThingsBoardAPILogger
from modbus.data_parser import DataParser as RTUDataParser
from modbus.socket_minimal_modebus import Instrument as RTUInstrument
from modbus.socket_minimal_modebus import _hexlify as hexify

api_logger = APILogger()
things_board_api_logger = ThingsBoardAPILogger()

SOCKET_SERVER_ROOT_PATH = os.environ.get('SOCKET_SERVER_ROOT_PATH', '')

CONF_FILES = {
    "SHAKTI_SOLAR_VFD_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/shakti_solar_vfd_conf.json"),
    "STATCON_HBD_INVERTER_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/statcon_hbd_conf_modbus.json"),
    "DELTA_RPI_INVERTER_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/device_conf_delta.json")
}


class ClientHandler(object):
    """
        ClientHandler for socket connections.
    """

    def __init__(self, connection, client_address):
        self.connection = connection
        self.client_address = client_address
        self.data_buffer = b""

    def serve(self):
        data = self.connection.recv(20)
        if len(data) > 0:
            logger.info(f"Received from {self.client_address}: {data}")
            data_hex = hexify(data)
            logger.info(f"HEX format: {data_hex}")
            is_heartbeat = False
            try:
                if isinstance(data, str):
                    data_str = data
                else:
                    data_str = data.decode("utf-8")
                if SHAKTI_SOLAR_VFD_HEARTBEAT in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["SHAKTI_SOLAR_VFD_CONF"])
                elif STATCON_HBD_INVERTER_HEARTBEAT in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["STATCON_HBD_INVERTER_CONF"])
                elif DELTA_RPI_INVERTER_HEARTBEAT in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["DELTA_RPI_INVERTER_CONF"])
                # Todo: remove this
                elif "123456789abcdef" in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["SHAKTI_SOLAR_VFD_CONF"])
            except UnicodeDecodeError:
                is_heartbeat = False

            self.data_buffer += data
            if is_heartbeat:
                self.start_communication()
                api_logger.log_heartbeat(data_str)
                things_board_api_logger.log_heartbeat(data_str)
            else:
                self.handle_command_response()

    def start_communication(self):
        # Send commands
        if not hasattr(self, "current_command_index"):
            self.current_command_index = 0
        self.data_buffer = b""
        # self.send_data()
        self.check_and_send_next_command()

    def handle_command_response(self):
        data_from_socket = self.data_buffer
        if isinstance(self.data_buffer, str):
            data_from_socket = bytearray(self.data_buffer, "utf-8")

        command_response = b''

        if not hasattr(self, "instrument"):
            logger.info(f"Received data: {self.data_buffer}")
            self.data_buffer = b""
            return

        try:
            command_response = self.instrument.get_command_response(
                data_from_socket,
                self.current_func_code
            )
        except Exception as e:
            logger.error("Failed parsing client response")
            logger.error(e)
        else:
            logger.info(f"Command response from client: {command_response}")
            self.process_command_data(command_response)

        self.data_buffer = b""
        self.check_and_send_next_command()

    def load_configurations(self, conf_file):
        with open(conf_file, 'r') as fp:
            data_dict = json.load(fp)

        self.connection_type = data_dict.get('connection_type', 'socket')
        self.comm_protocol = data_dict.get('comm_protocol')
        self.target_address = data_dict.get("address")
        self.registers = data_dict.get("registers")
        self.register_count = len(self.registers)

        self.connection_device = "fake_serial"

        if self.comm_protocol == DELTA_RPI:
            logger.info("DELTA_RPI device detected.")
            self.instrument = DeltaInstrument(
                "fake_serial",
                self.target_address
            )
            self.parser = DeltaDataParser()
        elif self.comm_protocol == MODBUS_RTU:
            self.instrument = RTUInstrument(
                "fake_serial",
                self.target_address
            )
            self.parser = RTUDataParser()
        else:
            raise Exception(f"Invalid comm protocol {self.comm_protocol}")

    def check_and_send_next_command(self):

        this_time = datetime.now()
        if hasattr(self, 'sent_time'):
            diff = this_time - self.sent_time
        else:
            diff = timedelta(seconds=21)

        if diff > timedelta(seconds=20):
            if self.current_command_index < self.register_count - 1:
                self.current_command_index += 1
            else:
                self.current_command_index = 0
            self.send_data()
            self.sent_time = datetime.now()

    def send_data(self):
        command_conf = self.registers[self.current_command_index]
        register_address = command_conf.get("reg_address")
        number_of_registers = command_conf.get("reg_count")
        function_code = command_conf.get("functioncode", 3)
        data_to_send, func_code = self.instrument.read_registers(
            register_address,
            number_of_registers,
            functioncode=function_code
        )
        data_hex = hexify(data_to_send)
        logger.info(f"Sending to socket: {data_to_send}")
        logger.info(f"HEX format: {data_hex}")
        self.connection.sendall(data_to_send)
        self.current_func_code = func_code
        self.data_buffer = b""

    def process_command_data(self, command_response):
        if command_response:
            command_conf = self.registers[self.current_command_index]
            register_address = command_conf.get("reg_address")
            data_type = command_conf.get("data_type")
            key_name = command_conf.get("reg_description")
            value = self.parser.parse(command_response, data_type)
            datalogger.info(f"key: {key_name}, Register: {register_address}, Value: {value}")
            push_to_server = self.current_command_index == self.register_count - 1
            api_logger.log({
                "key": key_name,
                "register": register_address,
                "value": value
            }, push_to_server)
            things_board_api_logger.log({
                "key": key_name,
                "Register": register_address,
                "Value": value
            })
