import time
import json
import os
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
from modbus.socket_minimal_modebus import _hexlify as hexify

DEFAULT_LOGGER_CONFIG = [{"name": "json_store"}]
SUPPORTED_LOGGER_NAMES = {
    "json_store": "json_store",
    "data_logger": "json_store",
    "data_logger.py": "json_store",
    "iot": "iot",
    "iot.py": "iot",
    "thingsboard": "thingsboard",
    "thingsboard.py": "thingsboard",
}

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
        self.config_device_identifier = None
        self.configured_loggers = []
        self._configure_output_loggers(DEFAULT_LOGGER_CONFIG)
        self.load_configurations(config_file)
        self.comm_started = False

    def _normalize_logger_entries(self, logger_entries):
        if not isinstance(logger_entries, list) or len(logger_entries) == 0:
            return list(DEFAULT_LOGGER_CONFIG)

        normalized_entries = []
        for item in logger_entries:
            if isinstance(item, str):
                normalized_entries.append({"name": item})
            elif isinstance(item, dict):
                normalized_entries.append(item)

        if len(normalized_entries) == 0:
            return list(DEFAULT_LOGGER_CONFIG)
        return normalized_entries

    def _configure_output_loggers(self, logger_entries):
        normalized_entries = self._normalize_logger_entries(logger_entries)
        configured_loggers = []

        for logger_conf in normalized_entries:
            if logger_conf.get("enabled", True) is False:
                continue

            logger_name = str(logger_conf.get("name", "")).strip().lower()
            normalized_name = SUPPORTED_LOGGER_NAMES.get(logger_name)
            if normalized_name is None:
                logger.warning("Unknown logger '%s' in config; skipping", logger_name)
                continue

            if normalized_name == "json_store":
                configured_loggers.append({
                    "name": "json_store",
                    "kind": "json_store",
                    "instance": None,
                })
                continue

            options = logger_conf.get("options", {})
            if not isinstance(options, dict):
                options = {}

            if normalized_name == "iot":
                default_api_key_env = options.get(
                    "default_api_key_env",
                    options.get("api_key_env", "DEVICE_API_KEY")
                )
                configured_loggers.append({
                    "name": "iot.py",
                    "kind": "iot",
                    "options": {
                        "default_api_key_env": default_api_key_env,
                        "device_api_key_env_map": options.get("device_api_key_env_map", {}),
                        "device_key_fields": options.get("device_key_fields", ["dev", "device_id", "device"]),
                    },
                    "instance": APILogger(api_key_env=default_api_key_env),
                })
                continue

            if normalized_name == "thingsboard":
                device_key_env = options.get("device_key_env", "THINGS_BOARD_DEVICE_KEY")
                if not os.environ.get(device_key_env):
                    logger.warning(
                        "Skipping thingsboard logger because env var '%s' is not set",
                        device_key_env
                    )
                    continue
                configured_loggers.append({
                    "name": "thingsboard.py",
                    "kind": "thingsboard",
                    "instance": ThingsBoardAPILogger(device_key_env=device_key_env),
                })

        if len(configured_loggers) == 0:
            configured_loggers = [{
                "name": "json_store",
                "kind": "json_store",
                "instance": None,
            }]

        self.configured_loggers = configured_loggers
        logger.info(
            "Configured output loggers: %s",
            [entry["name"] for entry in self.configured_loggers]
        )

    def _extract_device_identifier(self, payload, preferred_fields=None):
        if not isinstance(payload, dict):
            return None

        fields = preferred_fields or ["dev", "device_id", "device"]
        for field_name in fields:
            field_val = payload.get(field_name)
            if isinstance(field_val, str) and field_val.strip():
                return field_val.strip()

        return None

    def _resolve_iot_device_token(self, logger_entry, payload):
        options = logger_entry.get("options", {})
        if not isinstance(options, dict):
            options = {}

        key_fields = options.get("device_key_fields", ["dev", "device_id", "device"])
        if not isinstance(key_fields, list) or len(key_fields) == 0:
            key_fields = ["dev", "device_id", "device"]

        device_identifier = self._extract_device_identifier(payload, preferred_fields=key_fields)
        if not device_identifier and isinstance(self.config_device_identifier, str):
            device_identifier = self.config_device_identifier

        per_device_env_map = options.get("device_api_key_env_map", {})
        if isinstance(per_device_env_map, dict) and device_identifier:
            env_name = per_device_env_map.get(device_identifier)
            if isinstance(env_name, str) and env_name:
                token = os.environ.get(env_name)
                if token:
                    return token

        default_env = options.get("default_api_key_env", "DEVICE_API_KEY")
        if not isinstance(default_env, str) or not default_env:
            default_env = "DEVICE_API_KEY"
        return os.environ.get(default_env)

    def _log_measurement_with_configured_loggers(self, measurement, push_to_server=False):
        for logger_entry in self.configured_loggers:
            logger_kind = logger_entry["kind"]
            logger_instance = logger_entry["instance"]

            try:
                if logger_kind == "json_store":
                    datalogger.info(measurement)
                elif logger_kind == "iot":
                    logger_instance.set_device_token(self._resolve_iot_device_token(logger_entry, measurement))
                    logger_instance.log(measurement, push_to_server=push_to_server)
                elif logger_kind == "thingsboard":
                    logger_instance.log(dict(measurement))
            except Exception as ex:
                logger.error("Failed logger '%s': %s", logger_entry["name"], ex)

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

        data_from_device = self.data_buffer
        # data_from_device = ''.join(chr(x) for x in data_from_device)       
        logger.info(f"Received from device: {data_from_device}")
        data_hex = hexify(data_from_device)
        logger.info(f"HEX format: {data_hex}")

        command_response = b''
        try:
            command_response = self.instrument.get_command_response(
                data_from_device,
                getattr(self, "current_func_code", 3)
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
        self.registers = data_dict.get("registers") or []
        self._configure_output_loggers(data_dict.get("loggers"))
        self.config_device_identifier = (
            data_dict.get("dev")
            or data_dict.get("device_id")
            or data_dict.get("device")
        )

        self.connection_device = data_dict.get('connection_device')
        self.baudrate = data_dict.get('baudrate', 9600)
        self.data_bits = data_dict.get('data_bits', 8)
        self.parity = data_dict.get('parity', 'N')
        self.stopbits = data_dict.get('stopbits', 1)

        if self.connection_type == "serial" and self.connection_device is not None:
            self.connection = serial.Serial(
                self.connection_device,
                timeout=2.5,
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
        data_hex = hexify(data_to_send)
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
            key_name = command_conf.get("reg_description") or command_conf.get("key_name")
            value = self.parser.parse(command_response, data_type)
            push_to_server = self.current_command_index >= len(self.registers) - 1
            self._log_measurement_with_configured_loggers({
                "key": key_name,
                "register": register_address,
                "value": value
            }, push_to_server=push_to_server)
