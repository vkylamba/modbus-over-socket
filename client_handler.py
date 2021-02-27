import json
from datetime import datetime, timedelta

from api_logger.logger import APILogger
from api_logger.thingsboard import ThingsBoardAPILogger
from console_logger import logger
from constants import (DELTA_RPI, DELTA_RPI_INVERTER_HEARTBEAT, MODBUS_RTU,
                       STATCON_HBD_INVERTER_HEARTBEAT)
from data_logger import logger as datalogger
from delta.data_parser import DeltaDataParser
from delta.instrument import DeltaInstrument
from modbus.data_parser import DataParser as RTUDataParser
from modbus.socket_minimal_modebus import Instrument as RTUInstrument

api_logger = APILogger()
things_board_api_logger = ThingsBoardAPILogger()

CONF_FILES = {
    "STATCON_HBD_INVERTER_CONF": "config-files/statcon_hbd_conf_modbus.json",
    "DELTA_RPI_INVERTER_CONF": "config-files/device_conf_delta.json"
}


class ClientHandler(object):
    """
        ClientHandler
    """

    def __init__(self, connection, client_address):
        self.connection = connection
        self.client_address = client_address
        self.data_buffer = b""

    def serve(self):
        data = self.connection.recv(20)
        if data:
            logger.info(f"received from {self.client_address}: {data}")
            is_heartbeat = False
            try:
                if isinstance(data, str):
                    data_str = data
                else:
                    data_str = data.decode("utf-8")
                if STATCON_HBD_INVERTER_HEARTBEAT in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["STATCON_HBD_INVERTER_CONF"])
                elif DELTA_RPI_INVERTER_HEARTBEAT in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["DELTA_RPI_INVERTER_CONF"])
                # Todo: remove this
                elif "123456789abcdef" in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["STATCON_HBD_INVERTER_CONF"])
            except UnicodeDecodeError:
                is_heartbeat = False

            self.data_buffer += data
            if is_heartbeat:
                self.start_communication()
            else:
                self.handle_command_response()

    def start_communication(self):
        # Send commands
        self.current_command_index = 0
        self.data_buffer = b""
        self.send_data()

    def handle_command_response(self):
        data_from_socket = self.data_buffer
        if isinstance(self.data_buffer, str):
            data_from_socket = bytearray(self.data_buffer, "utf-8")

        command_response = b''
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

        self.check_and_send_next_command()

    def load_configurations(self, conf_file):
        with open(conf_file, 'r') as fp:
            data_dict = json.load(fp)
        self.comm_protocol = data_dict.get('comm_protocol')
        self.target_address = data_dict.get("address")
        self.registers = data_dict.get("registers")

        if self.comm_protocol == DELTA_RPI:
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

        if diff > timedelta(seconds=20) and self.current_command_index < len(self.registers) - 1:
            self.current_command_index += 1
            self.send_data()
            self.sent_time = datetime.now()

    def send_data(self):
        command_conf = self.registers[self.current_command_index]
        register_address = command_conf.get("reg_address")
        number_of_registers = command_conf.get("reg_count")
        data_to_send, func_code = self.instrument.read_registers(
            register_address,
            number_of_registers
        )
        if isinstance(data_to_send, str):
            data_to_send = data_to_send.encode('utf-8')
        logger.info(f"Sending to socket: {data_to_send}")
        data_hex = {":".join("{:02x}".format(c) for c in data_to_send)}
        logger.info(f"HEX format: {data_hex}")
        self.connection.sendall(data_to_send)
        self.current_func_code = func_code
        self.data_buffer = b""

    def process_command_data(self, command_response):
        if command_response:
            command_conf = self.registers[self.current_command_index]
            register_address = command_conf.get("reg_address")
            data_type = command_conf.get("data_type")
            key_name = command_conf.get("key_name")
            value = self.parser.parse(command_response, data_type, key_name)
            datalogger.info(value)
            try:
                api_logger.log(value)
            except Exception as e:
                logger.error(e)
            try:
                things_board_api_logger.log(value)
            except Exception as e:
                logger.error(e)
