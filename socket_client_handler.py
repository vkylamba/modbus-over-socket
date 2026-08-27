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
        self.connected_at = self._timestamp()
        self.data_flow = {
            "rx_messages": 0,
            "tx_messages": 0,
            "rx_bytes": 0,
            "tx_bytes": 0,
            "last_rx_at": None,
            "last_tx_at": None,
        }
        self._persisted_config_resolver = None
        self._last_persisted_config_identifier = None
        self._last_persisted_config_signature = None
        self._iot_resolution_cache = {}
        self.configured_loggers = []
        self._configure_output_loggers(DEFAULT_LOGGER_CONFIG)

    def set_persisted_config_resolver(self, resolver):
        self._persisted_config_resolver = resolver

    def _config_signature(self, config_dict):
        try:
            return json.dumps(config_dict, sort_keys=True)
        except Exception:
            return str(config_dict)

    def _known_device_identifiers(self):
        identifiers = []

        if isinstance(self.client_address, tuple) and len(self.client_address) >= 1:
            host = self.client_address[0]
            if isinstance(host, str) and host.strip():
                identifiers.append(host.strip())

        if isinstance(self.device_name, str) and self.device_name.strip():
            identifiers.append(self.device_name.strip())

        if isinstance(self.mac_address, str) and self.mac_address.strip():
            identifiers.append(self.mac_address.strip())

        payload = self.last_json_payload
        if isinstance(payload, dict):
            for key in ["device_id", "dev", "device", "mac"]:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    identifiers.append(value.strip())

            nested_payload = payload.get("payload")
            if isinstance(nested_payload, dict):
                for key in ["device_id", "dev", "device", "mac"]:
                    value = nested_payload.get(key)
                    if isinstance(value, str) and value.strip():
                        identifiers.append(value.strip())

        deduped = []
        seen = set()
        for item in identifiers:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _maybe_apply_persisted_configuration(self):
        if self._persisted_config_resolver is None:
            return

        identifiers = self._known_device_identifiers()
        for identifier in identifiers:
            try:
                persisted_config = self._persisted_config_resolver(identifier)
            except Exception as ex:
                logger.error("Failed resolving persisted config for '%s': %s", identifier, ex)
                continue

            if not isinstance(persisted_config, dict):
                continue

            config_signature = self._config_signature(persisted_config)
            if (
                self._last_persisted_config_identifier == identifier and
                self._last_persisted_config_signature == config_signature
            ):
                return

            try:
                self.apply_configuration_dict(persisted_config)
                self._last_persisted_config_identifier = identifier
                self._last_persisted_config_signature = config_signature
                logger.info(
                    "Applied persisted configuration for identifier '%s' on client %s",
                    identifier,
                    self.client_address
                )
                return
            except Exception as ex:
                logger.error("Failed applying persisted config for '%s': %s", identifier, ex)

    def _payload_size_bytes(self, payload, payload_text=None):
        if isinstance(payload, (bytes, bytearray)):
            return len(payload)
        if payload_text is None:
            payload_text = self._coerce_text(payload)
        return len(payload_text.encode("utf-8", errors="replace"))

    def _active_logger_names(self):
        return [entry.get("name") for entry in self.configured_loggers if entry.get("name")]

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
                device_key_map = options.get("device_api_key_env_map", {})
                if not isinstance(device_key_map, dict):
                    device_key_map = {}
                configured_loggers.append({
                    "name": "iot.py",
                    "kind": "iot",
                    "options": {
                        "default_api_key_env": default_api_key_env,
                        "device_api_key_env_map": device_key_map,
                        "device_key_fields": options.get("device_key_fields", ["dev", "device_id", "device"]),
                    },
                    "instance": APILogger(api_key_env=default_api_key_env),
                })
                logger.info(
                    "Enabled iot logger with %s per-device key mappings",
                    len(device_key_map)
                )
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

    def _safe_json_loads(self, value):
        if not isinstance(value, str):
            return None
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    def _extract_device_identifier(self, payload, preferred_fields=None):
        if not isinstance(payload, dict):
            return None

        fields = preferred_fields or ["dev", "device_id", "device"]
        for field_name in fields:
            field_val = payload.get(field_name)
            if isinstance(field_val, str) and field_val.strip():
                return field_val.strip()

        nested_payload = payload.get("payload")
        nested_dict = nested_payload if isinstance(nested_payload, dict) else self._safe_json_loads(nested_payload)
        if isinstance(nested_dict, dict):
            for field_name in fields:
                field_val = nested_dict.get(field_name)
                if isinstance(field_val, str) and field_val.strip():
                    return field_val.strip()

        return None

    def _resolve_iot_device_token(self, logger_entry, payload):
        def _resolve_secret_value(raw_value):
            if not isinstance(raw_value, str):
                return None, "none"
            value = raw_value.strip()
            if not value:
                return None, "none"

            env_token = os.environ.get(value)
            if env_token:
                return env_token, "env"

            # Backward-compatible: allow direct token literals in config maps.
            return value, "literal"

        def _record_resolution(identifier, source):
            cache_key = identifier or "default"
            if self._iot_resolution_cache.get(cache_key) == source:
                return
            self._iot_resolution_cache[cache_key] = source
            logger.info(
                "IoT token resolved for '%s' using source '%s'",
                cache_key,
                source
            )

        options = logger_entry.get("options", {})
        if not isinstance(options, dict):
            options = {}

        key_fields = options.get("device_key_fields", ["dev", "device_id", "device"])
        if not isinstance(key_fields, list) or len(key_fields) == 0:
            key_fields = ["dev", "device_id", "device"]

        device_identifier = self._extract_device_identifier(payload, preferred_fields=key_fields)
        per_device_env_map = options.get("device_api_key_env_map", {})
        if isinstance(per_device_env_map, dict) and device_identifier:
            configured_value = per_device_env_map.get(device_identifier)
            token, source = _resolve_secret_value(configured_value)
            if token:
                _record_resolution(device_identifier, f"per_device_{source}")
                return token

        default_env = options.get("default_api_key_env", "DEVICE_API_KEY")
        if not isinstance(default_env, str) or not default_env:
            default_env = "DEVICE_API_KEY"
        token, source = _resolve_secret_value(default_env)
        if token:
            _record_resolution(device_identifier, f"default_{source}")
            return token

        _record_resolution(device_identifier, "missing")
        return None

    def _is_modbus_topic_payload(self, payload):
        if not isinstance(payload, dict):
            return False

        topic = payload.get("topic")
        if not isinstance(topic, str):
            return False

        return "modbus" in topic.lower()

    def _extract_iot_json_payload(self, payload):
        if not isinstance(payload, dict):
            return payload

        topic = payload.get("topic")
        nested_payload = payload.get("payload")
        if isinstance(topic, str) and isinstance(nested_payload, dict):
            return dict(nested_payload)

        return dict(payload)

    def _log_payload_with_configured_loggers(self, payload):
        for logger_entry in self.configured_loggers:
            logger_kind = logger_entry["kind"]
            logger_instance = logger_entry["instance"]

            try:
                if logger_kind == "json_store":
                    datalogger.info(payload)
                elif logger_kind == "thingsboard" and isinstance(payload, dict):
                    logger_instance.log(dict(payload))
                elif logger_kind == "iot" and isinstance(payload, dict):
                    logger_instance.set_device_token(self._resolve_iot_device_token(logger_entry, payload))
                    if self._is_modbus_topic_payload(payload):
                        for key_name, key_value in payload.items():
                            if isinstance(key_value, (dict, list, tuple)):
                                continue
                            logger_instance.log({
                                "key": key_name,
                                "register": key_name,
                                "value": key_value,
                            }, push_to_server=False)
                        logger_instance.log({}, push_to_server=True)
                    else:
                        logger_instance.log_json(self._extract_iot_json_payload(payload))
            except Exception as ex:
                logger.error("Failed logger '%s': %s", logger_entry["name"], ex)

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

    def _log_heartbeat_with_configured_loggers(self, dev_name):
        for logger_entry in self.configured_loggers:
            logger_kind = logger_entry["kind"]
            logger_instance = logger_entry["instance"]
            if logger_kind not in ["iot", "thingsboard"]:
                continue

            try:
                logger_instance.log_heartbeat(dev_name)
            except Exception as ex:
                logger.error("Failed logger heartbeat '%s': %s", logger_entry["name"], ex)

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
        payload_size = self._payload_size_bytes(payload, payload_text)
        event = {
            "timestamp": self._timestamp(),
            "text": payload_text
        }

        with self.state_lock:
            self.last_update_at = event["timestamp"]
            self.last_data_text = payload_text
            self.recent_received.append(event)
            self.data_flow["rx_messages"] += 1
            self.data_flow["rx_bytes"] += payload_size
            self.data_flow["last_rx_at"] = event["timestamp"]
            if parsed_json is not None:
                self.last_json_payload = parsed_json
                self._update_device_metadata_from_json(parsed_json)

    def record_sent_payload(self, payload):
        payload_text = self._coerce_text(payload)
        payload_size = self._payload_size_bytes(payload, payload_text)
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
            self.data_flow["tx_messages"] += 1
            self.data_flow["tx_bytes"] += payload_size
            self.data_flow["last_tx_at"] = event["timestamp"]
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
                "connected_at": self.connected_at,
                "active_loggers": self._active_logger_names(),
                "data_flow": dict(self.data_flow),
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
        self._maybe_apply_persisted_configuration()
        self._maybe_send_mona_heartbeat_for_bad_status_time(payload)
        self._log_payload_with_configured_loggers(payload)
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
            self._maybe_apply_persisted_configuration()

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
                self._log_heartbeat_with_configured_loggers(data_str)
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

        self.apply_configuration_dict(data_dict)

    def apply_configuration_dict(self, data_dict):
        if not isinstance(data_dict, dict):
            raise ValueError("Invalid configuration payload")

        self.connection_type = data_dict.get('connection_type', 'socket')
        self.comm_protocol = data_dict.get('comm_protocol')
        self.target_address = data_dict.get("address")
        self.registers = data_dict.get("registers") or []
        self.register_count = len(self.registers)
        self._configure_output_loggers(data_dict.get("loggers"))

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
        elif self.comm_protocol in [None, "", "json"]:
            self.instrument = None
            self.parser = None
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
            push_to_server = self.current_command_index >= self.register_count - 1
            self._log_measurement_with_configured_loggers({
                "key": key_name,
                "register": register_address,
                "value": value
            }, push_to_server=push_to_server)
            # things_board_api_logger.log({
            #     "key": key_name,
            #     "Register": register_address,
            #     "Value": value
            # })
