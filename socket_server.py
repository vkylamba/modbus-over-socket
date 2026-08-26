import json
import hmac
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from html import escape

from flask import Flask, Response, redirect, render_template, request, url_for
from loggers.console_logger import logger
from socket_client_handler import ClientHandler

SOCKET_PORT = os.environ.get('SOCKET_PORT', '8024')
SOCKET_PORT = int(SOCKET_PORT)
ADMIN_SOCKET_PORT = os.environ.get('ADMIN_SOCKET_PORT', '9024')
ADMIN_SOCKET_PORT = int(ADMIN_SOCKET_PORT)
WEB_UI_PORT = os.environ.get('WEB_UI_PORT', '8080')
WEB_UI_PORT = int(WEB_UI_PORT)
ADMIN_UI_USERNAME = os.environ.get('ADMIN_UI_USERNAME', 'admin')
ADMIN_UI_PASSWORD = os.environ.get('ADMIN_UI_PASSWORD', 'admin')
STALE_DEVICE_SECONDS = int(os.environ.get('STALE_DEVICE_SECONDS', '90'))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEVICE_TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "config-files", "templates")
DEPLOYED_CONFIGS_DIR = os.path.join(PROJECT_ROOT, "config-files", "deployed")
DEPLOYED_CONFIG_INDEX_FILE = os.path.join(DEPLOYED_CONFIGS_DIR, "index.json")

DEVICE_LIST_TEMPLATE = "device_list.html"
DEVICE_DETAIL_TEMPLATE = "device_detail.html"


class DeviceRegistry:

    def __init__(self):
        self._lock = threading.Lock()
        self._handlers = {}
        self._next_device_id = 1
        self._deployed_config_index = {}
        self._ensure_deployed_config_storage()
        self._load_deployed_config_index()

    def _ensure_deployed_config_storage(self):
        os.makedirs(DEPLOYED_CONFIGS_DIR, exist_ok=True)

    def _load_deployed_config_index(self):
        self._deployed_config_index = {}
        if not os.path.isfile(DEPLOYED_CONFIG_INDEX_FILE):
            return

        try:
            with open(DEPLOYED_CONFIG_INDEX_FILE, "r", encoding="utf-8") as fp:
                loaded = json.load(fp)
        except Exception as ex:
            logger.error("Failed loading deployed config index: %s", ex)
            return

        if not isinstance(loaded, dict):
            return

        for identifier, file_name in loaded.items():
            if not isinstance(identifier, str) or not identifier.strip():
                continue
            if not isinstance(file_name, str) or not file_name.strip():
                continue
            self._deployed_config_index[identifier.strip()] = os.path.basename(file_name.strip())

    def _save_deployed_config_index_locked(self):
        with open(DEPLOYED_CONFIG_INDEX_FILE, "w", encoding="utf-8") as fp:
            json.dump(self._deployed_config_index, fp, indent=2, sort_keys=True)

    def _safe_identifier(self, value):
        text = str(value or "").strip()
        if not text:
            return "device"
        safe = "".join(ch if (ch.isalnum() or ch in ["-", "_", "."]) else "_" for ch in text)
        safe = safe.strip("._")
        return safe or "device"

    def _identifiers_for_handler(self, handler, fallback_identifier):
        snapshot = handler.get_ui_snapshot()
        identifiers = [str(fallback_identifier).strip()]
        identifiers.extend(self._logical_identifiers_from_snapshot(snapshot))

        client_address = getattr(handler, "client_address", None)
        if isinstance(client_address, tuple) and len(client_address) >= 1:
            host = client_address[0]
            if isinstance(host, str) and host.strip():
                identifiers.append(host.strip())

        for key in ["device_name", "mac_address"]:
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                identifiers.append(value.strip())

        deduped = []
        seen = set()
        for item in identifiers:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def add_handler(self, handler):
        with self._lock:
            device_id = str(self._next_device_id)
            self._next_device_id += 1
            self._handlers[device_id] = handler
            if hasattr(handler, "set_persisted_config_resolver"):
                handler.set_persisted_config_resolver(self.get_persisted_configuration)
            return device_id

    def remove_handler(self, device_id):
        with self._lock:
            self._handlers.pop(str(device_id), None)

    def get_handler(self, device_id):
        with self._lock:
            handler = self._handlers.get(str(device_id))
            if handler is not None:
                return handler

            target_id = str(device_id).strip()
            if not target_id:
                return None

            entries = self._build_device_entries_locked()
            matched_entry = next(
                (entry for entry in entries if entry.get("device_id") == target_id),
                None
            )
            if matched_entry is None:
                return None
            internal_device_id = matched_entry.get("internal_device_id")
            return self._handlers.get(str(internal_device_id))

    def _logical_identifiers_from_snapshot(self, snapshot):
        identifiers = []

        for key in ["device_name", "mac_address"]:
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                identifiers.append(value.strip())

        payload = snapshot.get("last_json_payload")
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
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _preferred_device_id_from_snapshot(self, snapshot, fallback_id):
        logical_ids = self._logical_identifiers_from_snapshot(snapshot)
        if logical_ids:
            return logical_ids[0], logical_ids
        return str(fallback_id), []

    def _device_rank(self, device_entry):
        last_update = device_entry.get("last_update_at") or ""
        connected_at = device_entry.get("connected_at") or ""
        return (last_update, connected_at)

    def _build_device_entries_locked(self):
        grouped_devices = {}
        for internal_device_id, handler in self._handlers.items():
            snapshot = handler.get_ui_snapshot()
            display_id, logical_ids = self._preferred_device_id_from_snapshot(snapshot, internal_device_id)
            entry = {
                "device_id": display_id,
                "internal_device_id": str(internal_device_id),
                "logical_device_ids": logical_ids,
                "client_address": handler.client_address,
                "device_name": snapshot.get("device_name"),
                "device_type": snapshot.get("device_type"),
                "mac_address": snapshot.get("mac_address"),
                "last_update_at": snapshot.get("last_update_at"),
                "last_topic": snapshot.get("last_topic"),
                "connected_at": snapshot.get("connected_at"),
                "active_loggers": snapshot.get("active_loggers", []),
                "data_flow": snapshot.get("data_flow", {})
            }

            existing = grouped_devices.get(display_id)
            if existing is None or self._device_rank(entry) >= self._device_rank(existing):
                grouped_devices[display_id] = entry

        return list(grouped_devices.values())

    def list_devices(self):
        with self._lock:
            return self._build_device_entries_locked()

    def get_device_snapshot(self, device_id):
        handler = self.get_handler(device_id)
        if handler is None:
            return None

        snapshot = handler.get_ui_snapshot()
        snapshot["device_id"] = str(device_id)
        return snapshot

    def send_to_device(self, device_id, payload, recv_timeout=3.0, max_bytes=4096, wait_for_response=True):
        handler = self.get_handler(device_id)
        if handler is None:
            raise KeyError("device not found")

        return handler.admin_exchange(
            payload,
            recv_timeout=recv_timeout,
            max_bytes=max_bytes,
            wait_for_response=wait_for_response
        )

    def set_device_type(self, device_id, device_type):
        handler = self.get_handler(device_id)
        if handler is None:
            raise KeyError("device not found")
        handler.set_device_type(device_type)

    def deploy_configuration(self, device_id, configuration):
        handler = self.get_handler(device_id)
        if handler is None:
            raise KeyError("device not found")

        if not hasattr(handler, "apply_configuration_dict"):
            raise ValueError("handler does not support configuration deployment")

        if not isinstance(configuration, dict):
            raise ValueError("Configuration must be a JSON object")

        identifiers = self._identifiers_for_handler(handler, device_id)
        primary_identifier = identifiers[0] if identifiers else str(device_id)
        file_name = f"{self._safe_identifier(primary_identifier)}.json"
        config_path = os.path.join(DEPLOYED_CONFIGS_DIR, file_name)

        with open(config_path, "w", encoding="utf-8") as fp:
            json.dump(configuration, fp, indent=2, sort_keys=True)

        with self._lock:
            for identifier in identifiers:
                self._deployed_config_index[identifier] = file_name
            self._save_deployed_config_index_locked()

        handler.apply_configuration_dict(configuration)

    def get_persisted_configuration(self, device_identifier):
        identifier = str(device_identifier or "").strip()
        if not identifier:
            return None

        with self._lock:
            file_name = self._deployed_config_index.get(identifier)

        if not file_name:
            return None

        config_path = os.path.join(DEPLOYED_CONFIGS_DIR, os.path.basename(file_name))
        if not os.path.isfile(config_path):
            return None

        try:
            with open(config_path, "r", encoding="utf-8") as fp:
                loaded = json.load(fp)
        except Exception as ex:
            logger.error("Failed reading persisted config for '%s': %s", identifier, ex)
            return None

        if not isinstance(loaded, dict):
            return None
        return loaded


def build_mona_topics(device_name):
    target_device = device_name or "dev-bln"
    return [
        f"/{target_device}/devices/{target_device}/cmd-req",
        f"/{target_device}/devices/{target_device}/update-trigger",
        "/iotaapsys/services/heartbeat"
    ]


def _json_response(connection, payload):
    connection.sendall((json.dumps(payload) + "\n").encode("utf-8"))


def _readline(connection, max_bytes=16384):
    data = b""
    while b"\n" not in data and len(data) < max_bytes:
        chunk = connection.recv(1024)
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", errors="replace").strip()


def _hex_preview(payload, max_chars=120):
    hex_str = payload.hex()
    if len(hex_str) <= max_chars:
        return hex_str
    return f"{hex_str[:max_chars]}..."


def create_web_app(registry):
    app = Flask(__name__)
    HEARTBEAT_TOPIC = "/iotaapsys/services/heartbeat"

    def _parse_iso_timestamp(ts):
        if not isinstance(ts, str) or not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _auto_refresh_seconds_from_request():
        raw = request.args.get("auto_refresh", "0")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 0
        if value < 0:
            return 0
        if value > 60:
            return 60
        return value

    def _enrich_device_health(device):
        now_utc = datetime.now(timezone.utc)
        last_rx_at = device.get("data_flow", {}).get("last_rx_at")
        last_rx_dt = _parse_iso_timestamp(last_rx_at)
        if last_rx_dt is None:
            device["is_stale"] = True
            device["stale_for_seconds"] = "n/a"
            return

        stale_for_seconds = int((now_utc - last_rx_dt).total_seconds())
        if stale_for_seconds < 0:
            stale_for_seconds = 0
        device["stale_for_seconds"] = stale_for_seconds
        device["is_stale"] = stale_for_seconds >= STALE_DEVICE_SECONDS

    def _auth_required_response():
        return Response(
            "Authentication required",
            401,
            {"WWW-Authenticate": 'Basic realm="Device Admin"'}
        )

    def _check_basic_auth():
        auth = request.authorization
        if auth is None:
            return False

        return (
            hmac.compare_digest(auth.username or "", ADMIN_UI_USERNAME) and
            hmac.compare_digest(auth.password or "", ADMIN_UI_PASSWORD)
        )

    @app.before_request
    def require_basic_auth():
        if not _check_basic_auth():
            return _auth_required_response()
        return None

    def build_heartbeat_payload_text():
        return f"epoch_ms {int(time.time() * 1000)}"

    def build_command_payload(topic, device_name, command_name, extra_payload_text):
        payload = {
            "topic": topic,
            "payload": {
                "command": command_name,
                "device": device_name,
                "command_id": str(uuid.uuid4())
            }
        }

        extra_payload_text = (extra_payload_text or "").strip()
        if extra_payload_text:
            extra_payload = json.loads(extra_payload_text)
            if not isinstance(extra_payload, dict):
                raise ValueError("Extra payload JSON must be an object")
            payload["payload"].update(extra_payload)

        return payload

    def build_text_payload(topic, plain_text_payload):
        return {
            "topic": topic,
            "payload": plain_text_payload
        }

    def default_form_values(device):
        device_name = device.get("device_name") or "dev-bln"
        topic = device.get("last_topic") or f"/dev/devices/{device_name}/cmd-req"
        device_type = device.get("device_type") or "Other"
        if device_type == "Mona":
            topic = build_mona_topics(device_name)[0]
        return {
            "device_type": device_type,
            "message_mode": "command_json",
            "topic": topic,
            "device_name": device_name,
            "command": "restart",
            "extra_payload": "{}",
            "plain_text_payload": "",
            "recv_timeout": "10",
            "max_bytes": "4096",
            "append_newline": True,
            "wait_for_response": True
        }

    def _template_search_dirs():
        candidates = [
            DEVICE_TEMPLATES_DIR,
            os.path.join(os.getcwd(), "config-files", "templates"),
            "/app/config-files/templates",
        ]
        deduped = []
        seen = set()
        for path in candidates:
            normalized = os.path.abspath(path)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _list_template_files():
        collected = []
        seen_names = set()
        for directory in _template_search_dirs():
            try:
                names = os.listdir(directory)
            except FileNotFoundError:
                continue

            for name in names:
                if not name.endswith(".json"):
                    continue
                if name in seen_names:
                    continue
                seen_names.add(name)
                collected.append(name)

        collected.sort()
        if not collected:
            logger.warning("No device templates found in search paths: %s", _template_search_dirs())
        return collected

    def _template_path(template_name):
        safe_name = os.path.basename(template_name or "")
        if not safe_name.endswith(".json"):
            raise ValueError("Template must be a .json file")
        for base_dir in _template_search_dirs():
            path = os.path.join(base_dir, safe_name)
            if os.path.isfile(path):
                return path
        raise FileNotFoundError(f"Template not found: {safe_name}")

    def _load_template_text(template_name):
        path = _template_path(template_name)
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read()

    def _is_env_var_name(value):
        if not isinstance(value, str):
            return False
        text = value.strip()
        if not text:
            return False
        if text != text.upper():
            return False
        if not (text[0].isalpha() or text[0] == "_"):
            return False
        return all(ch.isalnum() or ch == "_" for ch in text)

    def _device_identifiers_for_hint(device):
        identifiers = []

        for key in ["device_id", "device_name", "mac_address"]:
            value = device.get(key)
            if isinstance(value, str) and value.strip():
                identifiers.append(value.strip())

        payload = device.get("last_json_payload")
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

    def _build_iot_hint(template_payload_text, device):
        hint = {
            "error": None,
            "items": [],
            "all_present": True,
        }

        if not template_payload_text:
            return hint

        try:
            config = json.loads(template_payload_text)
        except json.JSONDecodeError:
            hint["error"] = "Template JSON is invalid; cannot verify IoT key mapping."
            return hint

        if not isinstance(config, dict):
            hint["error"] = "Template JSON must be an object."
            return hint

        logger_entries = config.get("loggers")
        if not isinstance(logger_entries, list):
            return hint

        known_identifiers = _device_identifiers_for_hint(device)
        for logger_entry in logger_entries:
            if not isinstance(logger_entry, dict):
                continue
            if logger_entry.get("enabled", True) is False:
                continue

            logger_name = str(logger_entry.get("name", "")).strip().lower()
            if logger_name not in ["iot", "iot.py"]:
                continue

            options = logger_entry.get("options", {})
            if not isinstance(options, dict):
                options = {}

            key_fields = options.get("device_key_fields", ["dev", "device_id", "device"])
            if not isinstance(key_fields, list) or len(key_fields) == 0:
                key_fields = ["dev", "device_id", "device"]

            mapping = options.get("device_api_key_env_map", {})
            if not isinstance(mapping, dict):
                mapping = {}

            selected_identifier = None
            selected_value = None
            for identifier in known_identifiers:
                if identifier in mapping:
                    selected_identifier = identifier
                    selected_value = mapping.get(identifier)
                    break

            source = "default"
            if selected_value is None:
                selected_value = options.get("default_api_key_env", options.get("api_key_env", "DEVICE_API_KEY"))
            else:
                source = f"mapped:{selected_identifier}"

            selected_value = str(selected_value or "").strip()
            is_env = _is_env_var_name(selected_value)
            if is_env:
                present = bool(os.environ.get(selected_value))
                key_label = selected_value
            else:
                present = bool(selected_value)
                key_label = "literal token"

            hint["items"].append({
                "source": source,
                "key_label": key_label,
                "is_env": is_env,
                "present": present,
                "selected_identifier": selected_identifier,
            })
            hint["all_present"] = hint["all_present"] and present

        return hint

    @app.route("/")
    def device_list():
        devices = registry.list_devices()
        for device in devices:
            _enrich_device_health(device)

        auto_refresh_seconds = _auto_refresh_seconds_from_request()
        dashboard = {
            "connected_devices": len(devices),
            "total_rx_messages": sum(device.get("data_flow", {}).get("rx_messages", 0) for device in devices),
            "total_tx_messages": sum(device.get("data_flow", {}).get("tx_messages", 0) for device in devices),
            "total_rx_bytes": sum(device.get("data_flow", {}).get("rx_bytes", 0) for device in devices),
            "total_tx_bytes": sum(device.get("data_flow", {}).get("tx_bytes", 0) for device in devices),
            "stale_devices": sum(1 for device in devices if device.get("is_stale")),
        }
        return render_template(
            DEVICE_LIST_TEMPLATE,
            devices=devices,
            dashboard=dashboard,
            auto_refresh_seconds=auto_refresh_seconds,
        )

    @app.route("/set-device-type", methods=["POST"])
    def set_device_type():
        device_id = request.form.get("device_id", "").strip()
        device_type = request.form.get("device_type", "Other").strip()
        if device_id:
            try:
                registry.set_device_type(device_id, device_type)
            except Exception as ex:
                logger.error("Failed setting device type: %s", ex)
        return redirect(url_for("device_list"))

    @app.route("/devices/<device_id>", methods=["GET", "POST"])
    def device_detail(device_id):
        device = registry.get_device_snapshot(device_id)
        if device is None:
            return redirect(url_for("device_list"))

        form_values = default_form_values(device)
        send_result = None
        template_result = None
        payload_preview = ""
        mona_topics = build_mona_topics(form_values.get("device_name") or device.get("device_name"))
        available_templates = _list_template_files()
        selected_template = available_templates[0] if available_templates else ""
        template_payload = ""
        if selected_template:
            try:
                template_payload = _load_template_text(selected_template)
            except Exception:
                template_payload = "{}"
        iot_hint = _build_iot_hint(template_payload, device)

        if request.method == "POST":
            form_action = request.form.get("form_action", "send_command")
            form_values = {
                "device_type": request.form.get("device_type", "Other"),
                "message_mode": request.form.get("message_mode", "command_json"),
                "topic": request.form.get("topic", "").strip(),
                "device_name": request.form.get("device_name", "").strip(),
                "command": request.form.get("command", "").strip(),
                "extra_payload": request.form.get("extra_payload", "{}"),
                "plain_text_payload": request.form.get("plain_text_payload", ""),
                "recv_timeout": request.form.get("recv_timeout", "10"),
                "max_bytes": request.form.get("max_bytes", "4096"),
                "append_newline": request.form.get("append_newline") == "1",
                "wait_for_response": request.form.get("wait_for_response") == "1"
            }
            selected_template = request.form.get("template_name", selected_template).strip()
            template_payload = request.form.get("template_payload", template_payload)
            iot_hint = _build_iot_hint(template_payload, device)

            if "device_type" in request.form:
                try:
                    registry.set_device_type(device_id, form_values["device_type"])
                except Exception as ex:
                    logger.error("Failed setting device type from detail page: %s", ex)

            if form_action == "load_template":
                try:
                    template_payload = _load_template_text(selected_template)
                    template_result = {
                        "ok": True,
                        "message": f"Loaded template {selected_template}"
                    }
                except Exception as ex:
                    template_result = {
                        "ok": False,
                        "message": f"Failed loading template: {escape(str(ex))}"
                    }

            elif form_action == "deploy_template":
                try:
                    deployed_config = json.loads(template_payload)
                    if not isinstance(deployed_config, dict):
                        raise ValueError("Template payload must be a JSON object")
                    registry.deploy_configuration(device_id, deployed_config)
                    template_result = {
                        "ok": True,
                        "message": f"Deployed template to device {device_id}"
                    }
                except Exception as ex:
                    template_result = {
                        "ok": False,
                        "message": f"Deploy failed: {escape(str(ex))}"
                    }

            if form_action != "send_command":
                device = registry.get_device_snapshot(device_id) or device
                mona_topics = build_mona_topics(form_values.get("device_name") or device.get("device_name"))
                payload_preview = ""
                events = []
                for event in device.get("recent_received", []):
                    events.append({
                        "direction": "received",
                        "timestamp": event.get("timestamp"),
                        "text": event.get("text")
                    })
                for event in device.get("recent_sent", []):
                    events.append({
                        "direction": "sent",
                        "timestamp": event.get("timestamp"),
                        "text": event.get("text")
                    })
                events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
                return render_template(
                    DEVICE_DETAIL_TEMPLATE,
                    device=device,
                    events=events,
                    send_result=send_result,
                    template_result=template_result,
                    form_values=form_values,
                    payload_preview=payload_preview,
                    mona_topics=mona_topics,
                    available_templates=available_templates,
                    selected_template=selected_template,
                    template_payload=template_payload,
                    iot_hint=iot_hint
                )

            try:
                is_mona_heartbeat = (
                    form_values["device_type"] == "Mona" and
                    form_values["topic"] == HEARTBEAT_TOPIC
                )
                if is_mona_heartbeat:
                    form_values["message_mode"] = "topic_text"
                    if not form_values["plain_text_payload"].strip():
                        form_values["plain_text_payload"] = build_heartbeat_payload_text()

                if form_values["message_mode"] == "topic_text":
                    command_payload = build_text_payload(
                        form_values["topic"],
                        form_values["plain_text_payload"]
                    )
                    request_id = str(uuid.uuid4())
                else:
                    command_payload = build_command_payload(
                        form_values["topic"],
                        form_values["device_name"],
                        form_values["command"],
                        form_values["extra_payload"]
                    )
                    request_id = command_payload["payload"]["command_id"]

                payload_text = json.dumps(command_payload)
                payload_preview = payload_text + ("\n" if form_values["append_newline"] else "")
                payload_bytes = payload_preview.encode("utf-8")
                exchange_result = registry.send_to_device(
                    device_id,
                    payload_bytes,
                    recv_timeout=float(form_values["recv_timeout"] or 10),
                    max_bytes=int(form_values["max_bytes"] or 4096),
                    wait_for_response=form_values["wait_for_response"]
                )
                response = exchange_result.get("response", b"")
                send_result = {
                    "request_id": request_id,
                    "timed_out": exchange_result.get("timed_out", False),
                    "response_text": response.decode("utf-8", errors="replace")
                }
                device = registry.get_device_snapshot(device_id) or device
            except Exception as ex:
                send_result = {
                    "request_id": "not-sent",
                    "timed_out": False,
                    "response_text": f"Error: {escape(str(ex))}"
                }
        else:
            is_mona_heartbeat = (
                form_values["device_type"] == "Mona" and
                form_values["topic"] == HEARTBEAT_TOPIC
            )
            if is_mona_heartbeat:
                form_values["message_mode"] = "topic_text"
                if not form_values["plain_text_payload"].strip():
                    form_values["plain_text_payload"] = build_heartbeat_payload_text()

            if form_values["message_mode"] == "topic_text":
                command_payload = {
                    "topic": form_values["topic"],
                    "payload": form_values["plain_text_payload"] or "epoch_ms 1786717797"
                }
            else:
                command_payload = {
                    "topic": form_values["topic"],
                    "payload": {
                        "command": form_values["command"],
                        "device": form_values["device_name"],
                        "command_id": "auto-generated-on-send"
                    }
                }
            payload_preview = json.dumps(command_payload, indent=2)

        events = []
        for event in device.get("recent_received", []):
            events.append({
                "direction": "received",
                "timestamp": event.get("timestamp"),
                "text": event.get("text")
            })
        for event in device.get("recent_sent", []):
            events.append({
                "direction": "sent",
                "timestamp": event.get("timestamp"),
                "text": event.get("text")
            })
        events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

        return render_template(
            DEVICE_DETAIL_TEMPLATE,
            device=device,
            events=events,
            send_result=send_result,
            template_result=template_result,
            form_values=form_values,
            payload_preview=payload_preview,
            mona_topics=mona_topics,
            available_templates=available_templates,
            selected_template=selected_template,
            template_payload=template_payload,
            iot_hint=iot_hint
        )

    return app


def handle_admin_connection(registry, connection, admin_address):
    try:
        logger.info(f"admin client connected: {admin_address}")
        raw_line = _readline(connection)
        if not raw_line:
            _json_response(connection, {"ok": False, "error": "empty request"})
            return

        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError:
            _json_response(connection, {"ok": False, "error": "invalid json"})
            return

        action = request.get("action", "status")
        request_id = request.get("request_id") or str(uuid.uuid4())
        logger.info(
            "admin request received: request_id=%s action=%s from=%s",
            request_id,
            action,
            admin_address
        )

        if action == "status":
            devices = registry.list_devices()
            logger.info(
                "admin status: request_id=%s connected_count=%s",
                request_id,
                len(devices)
            )
            _json_response(connection, {
                "ok": True,
                "request_id": request_id,
                "device_connected": len(devices) > 0,
                "connected_count": len(devices)
            })
            return

        if action == "list":
            devices = registry.list_devices()
            logger.info(
                "admin list: request_id=%s connected_count=%s device_ids=%s",
                request_id,
                len(devices),
                [device.get("device_id") for device in devices]
            )
            _json_response(connection, {
                "ok": True,
                "request_id": request_id,
                "devices": devices,
                "connected_count": len(devices)
            })
            return

        if action != "send":
            logger.warning(
                "admin unsupported action: request_id=%s action=%s from=%s",
                request_id,
                action,
                admin_address
            )
            _json_response(connection, {"ok": False, "request_id": request_id, "error": "unsupported action"})
            return

        device_id = request.get("device_id")
        if device_id is None:
            logger.warning(
                "admin send rejected: request_id=%s missing device_id from=%s",
                request_id,
                admin_address
            )
            _json_response(connection, {"ok": False, "request_id": request_id, "error": "missing device_id"})
            return

        handler = registry.get_handler(device_id)

        if handler is None:
            logger.warning(
                "admin send rejected: request_id=%s device not found device_id=%s from=%s",
                request_id,
                device_id,
                admin_address
            )
            _json_response(connection, {"ok": False, "request_id": request_id, "error": "device not found"})
            return

        payload_data = request.get("data")
        if payload_data is None:
            logger.warning(
                "admin send rejected: request_id=%s missing data device_id=%s from=%s",
                request_id,
                device_id,
                admin_address
            )
            _json_response(connection, {"ok": False, "request_id": request_id, "error": "missing data"})
            return

        encoding = request.get("encoding", "utf-8")
        recv_timeout = float(request.get("recv_timeout", 3))
        max_bytes = int(request.get("max_bytes", 4096))
        wait_for_response = bool(request.get("wait_for_response", True))
        append_newline = bool(request.get("append_newline", False))

        if encoding == "hex":
            try:
                payload = bytes.fromhex(payload_data)
            except ValueError:
                logger.warning(
                    "admin send rejected: request_id=%s invalid hex payload device_id=%s from=%s",
                    request_id,
                    device_id,
                    admin_address
                )
                _json_response(connection, {"ok": False, "request_id": request_id, "error": "invalid hex payload"})
                return
        else:
            payload = str(payload_data).encode("utf-8")

        if append_newline:
            payload += b"\n"

        logger.info(
            "admin send: request_id=%s from=%s device_id=%s target=%s encoding=%s bytes=%s append_newline=%s wait_for_response=%s recv_timeout=%s max_bytes=%s payload=%s",
            request_id,
            admin_address,
            device_id,
            getattr(handler, "client_address", None),
            encoding,
            len(payload),
            append_newline,
            wait_for_response,
            recv_timeout,
            max_bytes,
            payload
        )

        exchange_result = handler.admin_exchange(
            payload,
            recv_timeout=recv_timeout,
            max_bytes=max_bytes,
            wait_for_response=wait_for_response
        )
        response = exchange_result.get("response", b"")
        timed_out = exchange_result.get("timed_out", False)
        logger.info(
            "admin send result: request_id=%s from=%s device_id=%s target=%s timed_out=%s response_bytes=%s response_hex=%s",
            request_id,
            admin_address,
            device_id,
            getattr(handler, "client_address", None),
            timed_out,
            len(response),
            _hex_preview(response)
        )
        _json_response(connection, {
            "ok": True,
            "request_id": request_id,
            "device_id": str(device_id),
            "timed_out": timed_out,
            "response_hex": response.hex(),
            "response_text": response.decode("utf-8", errors="replace")
        })
    except Exception as ex:
        logger.exception(ex)
        try:
            _json_response(connection, {"ok": False, "error": str(ex)})
        except Exception:
            pass
    finally:
        connection.close()


def run_admin_server(registry):
    admin_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    admin_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    admin_sock.bind(("0.0.0.0", ADMIN_SOCKET_PORT))
    admin_sock.listen(5)
    logger.info(f"admin socket listening on 0.0.0.0:{ADMIN_SOCKET_PORT}")

    while True:
        connection, admin_address = admin_sock.accept()
        admin_thread = threading.Thread(
            target=handle_admin_connection,
            args=(registry, connection, admin_address),
            daemon=True
        )
        admin_thread.start()


def main():
    registry = DeviceRegistry()
    web_app = create_web_app(registry)
    admin_thread = threading.Thread(
        target=run_admin_server,
        args=(registry,),
        daemon=True
    )
    admin_thread.start()

    web_thread = threading.Thread(
        target=web_app.run,
        kwargs={
            "host": "0.0.0.0",
            "port": WEB_UI_PORT,
            "debug": False,
            "use_reloader": False
        },
        daemon=True
    )
    web_thread.start()
    logger.info(f"web admin listening on 0.0.0.0:{WEB_UI_PORT}")

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the address given on the command line
    server_name = sys.argv[1]
    server_address = (server_name, SOCKET_PORT)
    logger.info('starting up on %s port %s' % server_address)
    sock.bind(server_address)
    sock.listen(5)

    def serve_device_connection(connection, client_address):
        client_handler = None
        device_id = None
        try:
            client_handler = ClientHandler(
                connection,
                client_address
            )
            device_id = registry.add_handler(client_handler)
            logger.info(f"device {device_id} registered: {client_address}")
            while True:
                client_handler.serve()
        except Exception as ex:
            logger.exception(ex)
        finally:
            if device_id is not None:
                registry.remove_handler(device_id)
                logger.info(f"device {device_id} removed: {client_address}")
            connection.close()

    while True:
        try:
            logger.info('waiting for a connection')
            connection, client_address = sock.accept()
            logger.info(f'client connected: {client_address}')
            device_thread = threading.Thread(
                target=serve_device_connection,
                args=(connection, client_address),
                daemon=True
            )
            device_thread.start()
        except Exception as ex:
            logger.exception(ex)

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        logger.exception("Failed to start server: ")
        logger.exception(ex)
