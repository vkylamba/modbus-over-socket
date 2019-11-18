import logging

import json

from socket_minimal_modebus import Instrument

from data_parser import DataParser
from data_logger import logger as datalogger


logger = logging.getLogger(__name__)
logger.setLevel('INFO')


class ClientHandler(object):
    """
    """

    def __init__(self, connection, client_address, conf_file):
        self.connection = connection
        self.client_address = client_address
        self.data_buffer = ""
        self.conf_file = conf_file
        self.load_configurations()
        self.instrument = Instrument(
            "fake_serial",
            self.target_address
        )
        self.parser = DataParser()

    def serve(self):
        data = self.connection.recv(16)
        logger.info(f"received from {self.client_address}: {data}")
        if isinstance(data, str):
            data_str = data
        else:
            data_str = data.decode("utf-8")
        self.data_buffer += data_str
        if "Heartbeat" in data_str:
            self.start_communication()
        elif self.current_command_index < len(self.registers) - 1:
            # Receive response
            self.handle_command_response()

    def start_communication(self):
        # Send commands
        self.current_command_index = 0
        self.data_buffer = ""
        self.send_data()

    def handle_command_response(self):
        data_from_socket = bytearray(self.data_buffer, "utf-8")
        command_response = b''
        try:
            command_response = self.instrument.get_command_response(
                data_from_socket,
                self.current_func_code
            )
        except Exception as e:
            logger.error(e)
        else:
            self.process_command_data(command_response)
        self.current_command_index += 1
        self.send_data()

    def load_configurations(self):
        with open(self.conf_file, 'r') as fp:
            data_dict = json.load(fp)
        self.target_address = data_dict.get("address")
        self.registers = data_dict.get("registers")

    def send_data(self):
        command_conf = self.registers[self.current_command_index]
        register_address = command_conf.get("reg_address")
        number_of_registers = command_conf.get("reg_count")
        data_to_send, func_code = self.instrument.read_registers(
            register_address,
            number_of_registers
        )
        self.connection.sendall(data_to_send)
        self.current_func_code = func_code

    def process_command_data(self, command_response):
        command_conf = self.registers[self.current_command_index]
        register_address = command_conf.get("reg_address")
        data_type = command_conf.get("data_type")
        value = self.parser.parse(command_response, data_type)
        datalogger.info(f"register: {register_address}, data: {value}")
