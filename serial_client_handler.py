import time
import json
from datetime import datetime, timedelta

import serial

from constants import (DELTA_RPI, DELTA_RPI_INVERTER_HEARTBEAT, MODBUS_RTU,
                       STATCON_HBD_INVERTER_HEARTBEAT)
from delta.data_parser import DeltaDataParser
from delta.instrument import DeltaInstrument
from loggers.console_logger import logger
from loggers.data_logger import logger as datalogger
from loggers.iot import APILogger
from loggers.thingsboard import ThingsBoardAPILogger
from modbus.data_parser import DataParser as RTUDataParser
from modbus.socket_minimal_modebus import Instrument as RTUInstrument

api_logger = APILogger()
things_board_api_logger = ThingsBoardAPILogger()

CONF_FILES = {
    "SHAKTI_SOLAR_VFD_CONF": "shakti_solar_vfd_conf.json",
    "STATCON_HBD_INVERTER_CONF": "config-files/statcon_hbd_conf_modbus.json",
    "DELTA_RPI_INVERTER_CONF": "config-files/device_conf_delta.json"
}


class ClientHandler(object):
    """
        ClientHandler for socket connections.
    """

    def __init__(self, config_file):
        self.data_buffer = b""
        self.load_configurations(config_file)
        self.comm_started = False

    def serve(self):
        if not self.comm_started:
            self.start_communication()
        self.handle_command_response()
        time.sleep(1)

    def start_communication(self):
        # Send commands
        self.comm_started = True
        self.current_command_index = 0
        self.data_buffer = b""
        self.send_data()
        self.receive_data()

    def receive_data(self):
        for chance in range(0, 5):
            bytes_to_read = self.connection.inWaiting()
            while bytes_to_read > 0:
                bytes_read = self.connection.read(bytes_to_read)
                for byte in bytes_read:
                    self.data_buffer += bytes([byte])
                time.sleep(0.1)
                bytes_to_read = self.connection.inWaiting()
            time.sleep(0.1)
        return self.data_buffer

    def handle_command_response(self):
        if len(self.data_buffer) < 4:
            return

        data_from_socket = self.data_buffer

        data_from_socket = ''.join(chr(x) for x in data_from_socket)

        logger.info(f"Received from device: {data_from_socket}")
        # print(data_from_socket.decode("utf-16"))
        data_hex = {":".join("{:02x}".format(ord(c)) for c in data_from_socket)}
        logger.info(f"HEX format: {data_hex}")

        command_response = b''
        try:
            command_response = self.instrument.get_command_response(
                data_from_socket,
                self.current_func_code
            )
        except Exception as e:
            logger.error("Failed parsing client response")
            logger.error(e)
            self.data_buffer = b''
        else:
            logger.info(f"Command response from client: {command_response}")
            self.process_command_data(command_response)

        self.check_and_send_next_command()

    def load_configurations(self, conf_file):
        with open(conf_file, 'r') as fp:
            data_dict = json.load(fp)

        self.connection_type = data_dict.get('connection_type', 'socket')
        self.comm_protocol = data_dict.get('comm_protocol')
        self.target_address = data_dict.get("address")
        self.registers = data_dict.get("registers")

        self.connection_device = data_dict.get('connection_device')
        self.baudrate = data_dict.get('baudrate', 9600)
        self.data_bits = data_dict.get('data_bits', 8)
        self.parity = data_dict.get('parity', 'N')
        self.stopbits = data_dict.get('stopbits', 1)

        if self.connection_type == "serial" and self.connection_device is not None:
            self.connection = serial.Serial(
                self.connection_device,
                timeout=0.5,
                baudrate=self.baudrate,
                bytesize=self.data_bits,
                parity=self.parity,
                stopbits=self.stopbits
            )
        else:
            self.connection = "fake_serial"

        if self.comm_protocol == DELTA_RPI:
            logger.info("DELTA_RPI device detected.")
            self.instrument = DeltaInstrument(
                self.connection,
                self.target_address
            )
            self.parser = DeltaDataParser()
        elif self.comm_protocol == MODBUS_RTU:
            self.instrument = RTUInstrument(
                self.connection,
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
        functioncode = command_conf.get("functioncode", 4)
        data_to_send, func_code = self.instrument.read_registers(
            register_address,
            number_of_registers,
            functioncode=functioncode
        )
        if isinstance(data_to_send, str):
            data_hex = {":".join("{:02x}".format(ord(c)) for c in data_to_send)}
            data_to_send = bytearray(data_to_send, "utf-8")
        else:
            data_hex = {":".join("{:02x}".format(ord(c)) for c in data_to_send.decode("utf-8"))}
        logger.info(f"Sending to serial: {data_to_send}")
        logger.info(f"HEX format: {data_hex}")
        self.connection.flush()
        time.sleep(0.5)
        self.connection.write(data_to_send)
        time.sleep(0.5)
        self.current_func_code = func_code
        self.data_buffer = b""

    def process_command_data(self, command_response):
        if command_response:
            command_conf = self.registers[self.current_command_index]
            register_address = command_conf.get("reg_address")
            data_type = command_conf.get("data_type")
            key_name = command_conf.get("key_name")
            value = self.parser.parse(command_response, data_type)
            datalogger.info(value)
            try:
                api_logger.log(value)
            except Exception as e:
                logger.error(e)
            try:
                things_board_api_logger.log(value)
            except Exception as e:
                logger.error(e)
