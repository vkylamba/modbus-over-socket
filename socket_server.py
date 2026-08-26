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

DEVICE_LIST_TEMPLATE = "device_list.html"
DEVICE_DETAIL_TEMPLATE = "device_detail.html"


class DeviceRegistry:

    def __init__(self):
        self._lock = threading.Lock()
        self._handlers = {}
        self._next_device_id = 1

    def add_handler(self, handler):
        with self._lock:
            device_id = str(self._next_device_id)
            self._next_device_id += 1
            self._handlers[device_id] = handler
            return device_id

    def remove_handler(self, device_id):
        with self._lock:
            self._handlers.pop(str(device_id), None)

    def get_handler(self, device_id):
        with self._lock:
            return self._handlers.get(str(device_id))

    def list_devices(self):
        with self._lock:
            devices = []
            for device_id, handler in self._handlers.items():
                snapshot = handler.get_ui_snapshot()
                devices.append({
                    "device_id": device_id,
                    "client_address": handler.client_address,
                    "device_name": snapshot.get("device_name"),
                    "device_type": snapshot.get("device_type"),
                    "mac_address": snapshot.get("mac_address"),
                    "last_update_at": snapshot.get("last_update_at"),
                    "last_topic": snapshot.get("last_topic"),
                    "connected_at": snapshot.get("connected_at"),
                    "active_loggers": snapshot.get("active_loggers", []),
                    "data_flow": snapshot.get("data_flow", {})
                })
            return devices

    def get_device_snapshot(self, device_id):
        with self._lock:
            handler = self._handlers.get(str(device_id))

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
        payload_preview = ""
        mona_topics = build_mona_topics(form_values.get("device_name") or device.get("device_name"))

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

            try:
                registry.set_device_type(device_id, form_values["device_type"])
            except Exception as ex:
                logger.error("Failed setting device type from detail page: %s", ex)

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
                    form_values=form_values,
                    payload_preview=payload_preview,
                    mona_topics=mona_topics
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
            form_values=form_values,
            payload_preview=payload_preview,
            mona_topics=mona_topics
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
