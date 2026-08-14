import json
import os
import socket
import threading
import time
from collections import deque
from datetime import datetime, timedelta

from constants import (DELTA_RPI, DELTA_RPI_INVERTER_HEARTBEAT, MODBUS_RTU,
                       SHAKTI_SOLAR_VFD_HEARTBEAT,
                       STATCON_HBD_INVERTER_HEARTBEAT, SELEC_3_PHASE_METER)
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
# things_board_api_logger = ThingsBoardAPILogger()

SOCKET_SERVER_ROOT_PATH = os.environ.get('SOCKET_SERVER_ROOT_PATH', '')
COMMANDS_DELAY_SECONDS = os.environ.get('COMMANDS_DELAY_SECONDS', '5')
COMMANDS_DELAY_SECONDS = int(COMMANDS_DELAY_SECONDS)
MONA_STATUS_DRIFT_SECONDS = int(os.environ.get('MONA_STATUS_DRIFT_SECONDS', '300'))
MONA_AUTO_HEARTBEAT_MIN_INTERVAL_SECONDS = int(
    os.environ.get('MONA_AUTO_HEARTBEAT_MIN_INTERVAL_SECONDS', '30')
)

CONF_FILES = {
    "SHAKTI_SOLAR_VFD_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/shakti_solar_vfd_conf.json"),
    "STATCON_HBD_INVERTER_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/statcon_hbd_conf_modbus.json"),
    "DELTA_RPI_INVERTER_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/device_conf_delta.json"),
    "SELEC_3_PHASE_METER_CONF": os.path.join(SOCKET_SERVER_ROOT_PATH, "config-files/selec_3p_meter_conf.json"),
}


class ClientHandler(object):
    """
        ClientHandler for socket connections.
    """

    def __init__(self, connection, client_address):
        self.connection = connection
        self.client_address = client_address
        self.data_buffer = b""
        self.io_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.connection.settimeout(1.0)
        self.last_update_at = None
        self.last_data_text = ""
        self.last_json_payload = None
        self.device_name = None
        self.device_type = "Other"
        self.mac_address = None
        self.last_topic = ""
        self.recent_received = deque(maxlen=100)
        self.recent_sent = deque(maxlen=100)
        self.last_auto_heartbeat_at = 0.0

    def _timestamp(self):
        return datetime.utcnow().isoformat() + "Z"

    def _coerce_text(self, payload):
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        return str(payload)

    def _update_device_metadata_from_json(self, payload):
        if not isinstance(payload, dict):
            return

        payload_device = payload.get("device")
        if isinstance(payload_device, str) and payload_device:
            self.device_name = payload_device

        topic = payload.get("topic")
        if isinstance(topic, str):
            self.last_topic = topic
            if topic.endswith("/status") or "/devices/" in topic:
                self.device_type = "Mona"

        top_level_device_id = payload.get("device_id")
        if isinstance(top_level_device_id, str) and top_level_device_id:
            self.device_name = top_level_device_id

        top_level_dev = payload.get("dev")
        if isinstance(top_level_dev, str) and top_level_dev:
            self.device_name = top_level_dev

        top_level_mac = payload.get("mac")
        if top_level_mac is not None:
            self.mac_address = str(top_level_mac)

        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_device = nested_payload.get("device")
            if isinstance(nested_device, str) and nested_device:
                self.device_name = nested_device

            nested_dev = nested_payload.get("dev")
            if isinstance(nested_dev, str) and nested_dev:
                self.device_name = nested_dev

            nested_mac = nested_payload.get("mac")
            if nested_mac is not None:
                self.mac_address = str(nested_mac)
        elif isinstance(nested_payload, str):
            try:
                decoded_nested_payload = json.loads(nested_payload)
            except json.JSONDecodeError:
                decoded_nested_payload = None

            if isinstance(decoded_nested_payload, dict):
                nested_dev = decoded_nested_payload.get("dev")
                if isinstance(nested_dev, str) and nested_dev:
                    self.device_name = nested_dev

                nested_mac = decoded_nested_payload.get("mac")
                if nested_mac is not None:
                    self.mac_address = str(nested_mac)

    def set_device_type(self, device_type):
        if device_type not in ["Mona", "Other"]:
            raise ValueError("invalid device type")
        with self.state_lock:
            self.device_type = device_type

    def _extract_mona_status_dict(self, payload):
        if not isinstance(payload, dict):
            return None

        topic = payload.get("topic")
        if not isinstance(topic, str) or not topic.endswith("/status"):
            return None

        status_payload = payload.get("payload")
        if isinstance(status_payload, dict):
            return status_payload
        if isinstance(status_payload, str):
            try:
                decoded_payload = json.loads(status_payload)
            except json.JSONDecodeError:
                return None
            if isinstance(decoded_payload, dict):
                return decoded_payload

        return None

    def _build_mona_heartbeat_payload(self):
        heartbeat_dict = {
            "topic": "/iotaapsys/services/heartbeat",
            "payload": f"epoch_ms {int(time.time() * 1000)}"
        }
        return (json.dumps(heartbeat_dict) + "\n").encode("utf-8")

    def _maybe_send_mona_heartbeat_for_bad_status_time(self, payload):
        status_dict = self._extract_mona_status_dict(payload)
        if status_dict is None:
            return

        uptime = status_dict.get("uptime")
        if uptime is None:
            return

        try:
            uptime_seconds = int(str(uptime))
        except (ValueError, TypeError):
            return

        now_seconds = int(time.time())
        is_bad_timestamp = abs(now_seconds - uptime_seconds) > MONA_STATUS_DRIFT_SECONDS
        if not is_bad_timestamp:
            return

        now_monotonic = time.monotonic()
        if now_monotonic - self.last_auto_heartbeat_at < MONA_AUTO_HEARTBEAT_MIN_INTERVAL_SECONDS:
            return

        heartbeat_payload = self._build_mona_heartbeat_payload()
        with self.io_lock:
            self.record_sent_payload(heartbeat_payload)
            self.connection.sendall(heartbeat_payload)

        self.last_auto_heartbeat_at = now_monotonic
        logger.warning(
            "Mona status uptime out of range; auto-sent heartbeat. client=%s uptime=%s now=%s drift_limit=%s",
            self.client_address,
            uptime_seconds,
            now_seconds,
            MONA_STATUS_DRIFT_SECONDS
        )

    def record_received_payload(self, payload, parsed_json=None):
        payload_text = self._coerce_text(payload)
        event = {
            "timestamp": self._timestamp(),
            "text": payload_text
        }

        with self.state_lock:
            self.last_update_at = event["timestamp"]
            self.last_data_text = payload_text
            self.recent_received.append(event)
            if parsed_json is not None:
                self.last_json_payload = parsed_json
                self._update_device_metadata_from_json(parsed_json)

    def record_sent_payload(self, payload):
        payload_text = self._coerce_text(payload)
        event = {
            "timestamp": self._timestamp(),
            "text": payload_text
        }
        try:
            parsed_json = json.loads(payload_text.strip())
        except json.JSONDecodeError:
            parsed_json = None

        with self.state_lock:
            self.recent_sent.append(event)
            if parsed_json is not None:
                self._update_device_metadata_from_json(parsed_json)

    def get_ui_snapshot(self):
        with self.state_lock:
            return {
                "client_address": self.client_address,
                "last_update_at": self.last_update_at,
                "last_data_text": self.last_data_text,
                "device_name": self.device_name,
                "device_type": self.device_type,
                "mac_address": self.mac_address,
                "last_topic": self.last_topic,
                "last_json_payload": self.last_json_payload,
                "recent_received": list(self.recent_received),
                "recent_sent": list(self.recent_sent)
            }

    def is_connected(self):
        return self.connection is not None

    def admin_exchange(self, payload, recv_timeout=3.0, max_bytes=4096, wait_for_response=True):
        """
            Send payload to connected device and wait for one response frame.
        """
        if not self.is_connected():
            raise ConnectionError("No connected device")

        if not isinstance(payload, (bytes, bytearray)):
            raise ValueError("Payload must be bytes")

        with self.io_lock:
            previous_timeout = self.connection.gettimeout()
            try:
                self.record_sent_payload(payload)
                self.connection.sendall(payload)
                if not wait_for_response:
                    return {
                        "timed_out": False,
                        "response": b""
                    }

                self.connection.settimeout(recv_timeout)
                try:
                    response = self.connection.recv(max_bytes)
                    if response:
                        self.record_received_payload(response)
                except socket.timeout:
                    return {
                        "timed_out": True,
                        "response": b""
                    }
            finally:
                self.connection.settimeout(previous_timeout)

        return {
            "timed_out": False,
            "response": response
        }

    def handle_json_payload(self):
        """
            If device sends JSON directly, store it as-is and skip
            heartbeat/config + command sequence flow.
        """
        if len(self.data_buffer) == 0:
            return False

        try:
            data_str = self.data_buffer.decode("utf-8").strip()
        except UnicodeDecodeError:
            return False

        if not data_str:
            return False

        if not data_str.startswith(("{", "[")):
            return False

        try:
            payload = json.loads(data_str)
        except json.JSONDecodeError:
            # Buffer likely contains an incomplete JSON fragment.
            return True

        self.record_received_payload(self.data_buffer, parsed_json=payload)
        self._maybe_send_mona_heartbeat_for_bad_status_time(payload)
        datalogger.info(payload)
        logger.info(f"Stored JSON payload from {self.client_address}")
        self.data_buffer = b""
        return True

    def serve(self):
        try:
            with self.io_lock:
                data = self.connection.recv(2048)
        except socket.timeout:
            return

        if data == b"":
            raise ConnectionAbortedError("Client disconnected")

        if len(data) > 0:
            logger.info(f"Received from {self.client_address}: {data}")
            data_hex = hexify(data)
            logger.info(f"HEX format: {data_hex}")
            self.record_received_payload(data)

            self.data_buffer += data
            if self.handle_json_payload():
                # Send acknowledgment for JSON payload
                # ack_payload = b'{"topic":"/dev-bln/devices/dev-bln/cmd-req","payload":{"command":"hello","device":"dev-bln","command_id":"abc-1"}}\n'
                # self.connection.sendall(ack_payload)
                # logger.info(f"Sent acknowledgment to {self.client_address}: {ack_payload}")
                return

            is_heartbeat = False
            data_str = ""
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
                elif SELEC_3_PHASE_METER in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["SELEC_3_PHASE_METER_CONF"])
                # Todo: remove this
                elif "123456789abcdef" in data_str:
                    is_heartbeat = True
                    self.load_configurations(CONF_FILES["SHAKTI_SOLAR_VFD_CONF"])
            except UnicodeDecodeError:
                is_heartbeat = False

            if is_heartbeat:
                self.start_communication()
                api_logger.log_heartbeat(data_str)
                # things_board_api_logger.log_heartbeat(data_str)
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
        
        logger.info(f"Handling command response: {data_from_socket}")

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
            self.data_buffer = b""
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
            
        if diff < timedelta(seconds=COMMANDS_DELAY_SECONDS):
            logger.info(f"Sleeping for {diff.seconds + 1} seconds")
            time.sleep(diff.seconds + 1)

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
            logger.info(f"key: {key_name}, Register: {register_address}, Value: {value}")
            datalogger.info(f"key: {key_name}, Register: {register_address}, Value: {value}")
            push_to_server = self.current_command_index == self.register_count
            api_logger.log({
                "key": key_name,
                "register": register_address,
                "value": value
            }, push_to_server)
            # things_board_api_logger.log({
            #     "key": key_name,
            #     "Register": register_address,
            #     "Value": value
            # })
