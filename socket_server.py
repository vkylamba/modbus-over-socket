import json
import hmac
import os
import socket
import sys
import threading
import time
import uuid
from html import escape

from flask import Flask, Response, redirect, render_template_string, request, url_for
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

DEVICE_LIST_TEMPLATE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Device Admin</title>
    <style>
        :root {
            --bg: #f2efe8;
            --panel: #fffaf1;
            --ink: #1f2933;
            --muted: #52606d;
            --accent: #c8553d;
            --line: #dccfb8;
            --soft: #f8ecd7;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Iowan Old Style", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top left, #f8dcc2 0, transparent 24%),
                linear-gradient(135deg, #f4f0e7, #ebe4d8 50%, #e2d7c6 100%);
            min-height: 100vh;
        }
        .page {
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 20px 48px;
        }
        h1 {
            margin: 0 0 8px;
            font-size: 44px;
            letter-spacing: 0.02em;
        }
        .subtitle {
            margin: 0 0 28px;
            color: var(--muted);
            font-size: 18px;
        }
        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            gap: 12px;
            flex-wrap: wrap;
        }
        .pill {
            display: inline-block;
            padding: 8px 14px;
            border-radius: 999px;
            background: rgba(200, 85, 61, 0.12);
            color: var(--accent);
            font-weight: 700;
        }
        .refresh {
            text-decoration: none;
            color: var(--ink);
            border: 1px solid var(--line);
            padding: 10px 14px;
            border-radius: 12px;
            background: var(--panel);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 18px;
        }
        .card {
            display: block;
            text-decoration: none;
            color: inherit;
            padding: 20px;
            background: rgba(255, 250, 241, 0.92);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(59, 48, 30, 0.08);
        }
        .card:hover {
            transform: translateY(-2px);
            transition: transform 120ms ease;
        }
        .label { color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }
        .value { font-size: 24px; margin: 6px 0 14px; }
        .meta { color: var(--muted); font-size: 15px; line-height: 1.5; }
        .row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 12px;
        }
        .card form {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card select {
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 6px 8px;
            background: #fff;
        }
        .card button {
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #fff;
            padding: 6px 10px;
            cursor: pointer;
        }
        .view-link {
            color: var(--accent);
            font-weight: 700;
            text-decoration: none;
        }
        .empty {
            background: rgba(255,250,241,0.85);
            border: 1px dashed var(--line);
            border-radius: 20px;
            padding: 28px;
            color: var(--muted);
        }
    </style>
</head>
<body>
    <div class="page">
        <h1>Device Admin</h1>
        <p class="subtitle">Connected TCP clients and their latest activity.</p>
        <div class="toolbar">
            <span class="pill">{{ devices|length }} connected</span>
            <a class="refresh" href="{{ url_for('device_list') }}">Refresh</a>
        </div>
        {% if devices %}
            <div class="grid">
                {% for device in devices %}
                    <div class="card">
                        <div class="label">Device ID</div>
                        <div class="value">{{ device['device_id'] }}</div>
                        <div class="meta">Type: {{ device.get('device_type') or 'Other' }}</div>
                        <div class="meta">Name: {{ device.get('device_name') or 'Unknown' }}</div>
                        <div class="meta">MAC: {{ device.get('mac_address') or 'Unknown' }}</div>
                        <div class="meta">Client: {{ device['client_address'] }}</div>
                        <div class="meta">Last update: {{ device.get('last_update_at') or 'No data yet' }}</div>
                        <div class="meta">Last topic: {{ device.get('last_topic') or 'Unavailable' }}</div>
                        <div class="row">
                            <a class="view-link" href="{{ url_for('device_detail', device_id=device['device_id']) }}">Open details</a>
                            <form method="post" action="{{ url_for('set_device_type') }}">
                                <input type="hidden" name="device_id" value="{{ device['device_id'] }}">
                                <select name="device_type">
                                    <option value="Mona" {% if device.get('device_type') == 'Mona' %}selected{% endif %}>Mona</option>
                                    <option value="Other" {% if device.get('device_type') != 'Mona' %}selected{% endif %}>Other</option>
                                </select>
                                <button type="submit">Set</button>
                            </form>
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="empty">No devices are connected right now.</div>
        {% endif %}
    </div>
</body>
</html>
"""

DEVICE_DETAIL_TEMPLATE = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Device {{ device['device_id'] }}</title>
    <style>
        :root {
            --bg: #f0ece5;
            --panel: rgba(255, 252, 246, 0.95);
            --ink: #1f2933;
            --muted: #52606d;
            --accent: #0f766e;
            --accent-2: #c8553d;
            --line: #d8cbb8;
            --soft: #eef6f2;
            --warn: #fff4de;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Iowan Old Style", serif;
            color: var(--ink);
            background:
                linear-gradient(180deg, rgba(255,255,255,0.25), rgba(255,255,255,0)),
                linear-gradient(135deg, #f6f0e7, #ece3d6 50%, #e3d8c9 100%);
            min-height: 100vh;
        }
        .page {
            max-width: 1280px;
            margin: 0 auto;
            padding: 28px 18px 36px;
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }
        .back {
            text-decoration: none;
            color: var(--accent);
            font-weight: 700;
        }
        h1 {
            margin: 8px 0 6px;
            font-size: 40px;
        }
        .subtitle {
            color: var(--muted);
            font-size: 17px;
            margin: 0;
        }
        .facts {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 12px;
        }
        .fact {
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(15, 118, 110, 0.1);
            color: var(--accent);
            font-size: 14px;
            font-weight: 700;
        }
        .layout {
            display: grid;
            grid-template-columns: minmax(320px, 1.15fr) minmax(320px, 0.95fr);
            gap: 18px;
        }
        .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 24px;
            box-shadow: 0 12px 28px rgba(59, 48, 30, 0.08);
            overflow: hidden;
        }
        .panel-header {
            padding: 18px 20px;
            border-bottom: 1px solid var(--line);
            background: rgba(255,255,255,0.45);
        }
        .panel-title {
            margin: 0;
            font-size: 24px;
        }
        .panel-subtitle {
            margin: 6px 0 0;
            color: var(--muted);
            font-size: 14px;
        }
        .logbox {
            max-height: 72vh;
            overflow-y: auto;
            padding: 14px 16px 18px;
            background:
                linear-gradient(180deg, rgba(255,255,255,0.25), rgba(255,255,255,0.75));
        }
        .event {
            padding: 14px;
            border-radius: 16px;
            background: #fff;
            border: 1px solid #eadfce;
            margin-bottom: 12px;
        }
        .event.sent {
            border-left: 5px solid var(--accent-2);
        }
        .event.received {
            border-left: 5px solid var(--accent);
        }
        .event-meta {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            font-family: "SFMono-Regular", Menlo, monospace;
            font-size: 13px;
            line-height: 1.5;
        }
        .form-body {
            padding: 18px 20px 22px;
        }
        .status {
            padding: 12px 14px;
            border-radius: 14px;
            margin-bottom: 14px;
            background: var(--soft);
            border: 1px solid #cfe7df;
        }
        .status.warn {
            background: var(--warn);
            border-color: #efd69d;
        }
        label {
            display: block;
            margin-bottom: 6px;
            font-size: 14px;
            font-weight: 700;
            color: var(--muted);
        }
        input, textarea, select {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 12px 14px;
            font: inherit;
            background: #fffefb;
            color: var(--ink);
            margin-bottom: 14px;
        }
        textarea {
            min-height: 170px;
            resize: vertical;
            font-family: "SFMono-Regular", Menlo, monospace;
            font-size: 13px;
        }
        .split {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        .checkbox {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 14px;
            color: var(--muted);
            font-size: 14px;
        }
        .checkbox input {
            width: auto;
            margin: 0;
        }
        button {
            border: 0;
            border-radius: 16px;
            background: linear-gradient(135deg, #0f766e, #155e75);
            color: white;
            padding: 14px 18px;
            font: inherit;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
        }
        @media (max-width: 920px) {
            .layout { grid-template-columns: 1fr; }
            .logbox { max-height: 48vh; }
            .split { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="page">
        <div class="topbar">
            <div>
                <a class="back" href="{{ url_for('device_list') }}">Back to devices</a>
                <h1>{{ device.get('device_name') or 'Unnamed device' }}</h1>
                <p class="subtitle">Device ID {{ device['device_id'] }} at {{ device['client_address'] }}</p>
                <div class="facts">
                    <span class="fact">Type: {{ device.get('device_type') or 'Other' }}</span>
                    <span class="fact">Last update: {{ device.get('last_update_at') or 'No data yet' }}</span>
                    <span class="fact">MAC: {{ device.get('mac_address') or 'Unknown' }}</span>
                    <span class="fact">Topic: {{ device.get('last_topic') or 'Auto-build below' }}</span>
                </div>
            </div>
            <a class="back" href="{{ url_for('device_detail', device_id=device['device_id']) }}">Refresh</a>
        </div>

        <div class="layout">
            <section class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">Recent Device Traffic</h2>
                    <p class="panel-subtitle">Newest events first. Inbound and outbound messages are shown together.</p>
                </div>
                <div class="logbox">
                    {% if events %}
                        {% for event in events %}
                            <div class="event {{ event['direction'] }}">
                                <div class="event-meta">{{ event['direction'] }} | {{ event['timestamp'] }}</div>
                                <pre>{{ event['text'] }}</pre>
                            </div>
                        {% endfor %}
                    {% else %}
                        <div class="event received"><div class="event-meta">No traffic yet</div><pre>Waiting for device data.</pre></div>
                    {% endif %}
                </div>
            </section>

            <section class="panel">
                <div class="panel-header">
                    <h2 class="panel-title">Command Interface</h2>
                    <p class="panel-subtitle">Build a command payload and send it on the current device TCP connection.</p>
                </div>
                <div class="form-body">
                    {% if send_result %}
                        <div class="status {% if send_result.get('timed_out') %}warn{% endif %}">
                            Sent command <strong>{{ send_result['request_id'] }}</strong>.
                            {% if send_result.get('timed_out') %}
                                Device did not respond before timeout.
                            {% else %}
                                Response bytes: {{ send_result.get('response_text') or '(empty response)' }}
                            {% endif %}
                        </div>
                    {% endif %}

                    <form method="post">
                        <input type="hidden" name="form_action" value="send_command">

                        <label for="device_type">Device Type</label>
                        <select id="device_type" name="device_type">
                            <option value="Mona" {% if form_values['device_type'] == 'Mona' %}selected{% endif %}>Mona</option>
                            <option value="Other" {% if form_values['device_type'] != 'Mona' %}selected{% endif %}>Other</option>
                        </select>

                        <label for="message_mode">Message Type</label>
                        <select id="message_mode" name="message_mode">
                            <option value="command_json" {% if form_values['message_mode'] == 'command_json' %}selected{% endif %}>Structured JSON command</option>
                            <option value="topic_text" {% if form_values['message_mode'] == 'topic_text' %}selected{% endif %}>Topic + plain text payload</option>
                        </select>

                        {% if form_values['device_type'] == 'Mona' %}
                            <label for="topic_preset">Mona Topic Preset</label>
                            <select id="topic_preset" name="topic_preset">
                                {% for topic_value in mona_topics %}
                                    <option value="{{ topic_value }}" {% if form_values['topic'] == topic_value %}selected{% endif %}>{{ topic_value }}</option>
                                {% endfor %}
                            </select>
                        {% endif %}

                        <label for="topic">Topic</label>
                        <input id="topic" name="topic" value="{{ form_values['topic'] }}" placeholder="/dev/devices/DEVICE123/cmd-req">

                        <div class="split">
                            <div>
                                <label for="device_name">Device</label>
                                <input id="device_name" name="device_name" value="{{ form_values['device_name'] }}" placeholder="DEVICE123">
                            </div>
                            <div>
                                <label for="command">Command</label>
                                <input id="command" name="command" value="{{ form_values['command'] }}" placeholder="restart">
                            </div>
                        </div>

                        <label for="extra_payload">Extra Payload JSON</label>
                        <textarea id="extra_payload" name="extra_payload" placeholder='{"delay": 5}'>{{ form_values['extra_payload'] }}</textarea>

                        <label for="plain_text_payload">Plain Text Payload</label>
                        <textarea id="plain_text_payload" name="plain_text_payload" placeholder="epoch_ms 1786717797">{{ form_values['plain_text_payload'] }}</textarea>

                        <div class="split">
                            <div>
                                <label for="recv_timeout">Receive Timeout (seconds)</label>
                                <input id="recv_timeout" name="recv_timeout" type="number" min="0" step="0.5" value="{{ form_values['recv_timeout'] }}">
                            </div>
                            <div>
                                <label for="max_bytes">Max Response Bytes</label>
                                <input id="max_bytes" name="max_bytes" type="number" min="1" step="1" value="{{ form_values['max_bytes'] }}">
                            </div>
                        </div>

                        <div class="checkbox">
                            <input id="append_newline" name="append_newline" type="checkbox" value="1" {% if form_values['append_newline'] %}checked{% endif %}>
                            <label for="append_newline" style="margin:0; font-weight:400;">Append newline to payload</label>
                        </div>

                        <div class="checkbox">
                            <input id="wait_for_response" name="wait_for_response" type="checkbox" value="1" {% if form_values['wait_for_response'] %}checked{% endif %}>
                            <label for="wait_for_response" style="margin:0; font-weight:400;">Wait for device response</label>
                        </div>

                        <label for="payload_preview">Payload Preview</label>
                        <textarea id="payload_preview" readonly>{{ payload_preview }}</textarea>

                        <button type="submit">Send Command</button>
                    </form>
                </div>
            </section>
        </div>
    </div>
    <script>
        (function () {
            const deviceTypeEl = document.getElementById("device_type");
            const topicPresetEl = document.getElementById("topic_preset");
            const topicEl = document.getElementById("topic");
            const modeEl = document.getElementById("message_mode");
            const deviceNameEl = document.getElementById("device_name");
            const commandEl = document.getElementById("command");
            const extraPayloadEl = document.getElementById("extra_payload");
            const plainTextEl = document.getElementById("plain_text_payload");
            const appendNewlineEl = document.getElementById("append_newline");
            const payloadPreviewEl = document.getElementById("payload_preview");
            const heartbeatTopic = "/iotaapsys/services/heartbeat";

            if (!modeEl || !topicEl || !plainTextEl || !payloadPreviewEl) {
                return;
            }

            function ensureHeartbeatDefaults() {
                const isMona = deviceTypeEl && deviceTypeEl.value === "Mona";
                const selectedTopic = topicEl.value;
                if (isMona && selectedTopic === heartbeatTopic) {
                    modeEl.value = "topic_text";
                    if (!plainTextEl.value.trim()) {
                        plainTextEl.value = "epoch_ms " + Date.now();
                    }
                }
            }

            function buildPreviewPayload() {
                if (modeEl.value === "topic_text") {
                    return {
                        topic: topicEl.value,
                        payload: plainTextEl.value
                    };
                }

                const payload = {
                    topic: topicEl.value,
                    payload: {
                        command: deviceTypeEl && deviceTypeEl.value === "Mona" && topicEl.value === heartbeatTopic
                            ? "heartbeat"
                            : (commandEl ? commandEl.value : ""),
                        device: deviceNameEl ? deviceNameEl.value : "",
                        command_id: "auto-generated-on-send"
                    }
                };

                const extraPayloadText = extraPayloadEl ? extraPayloadEl.value.trim() : "";
                if (extraPayloadText) {
                    const extraPayload = JSON.parse(extraPayloadText);
                    if (typeof extraPayload !== "object" || extraPayload === null || Array.isArray(extraPayload)) {
                        throw new Error("Extra payload JSON must be an object");
                    }
                    Object.assign(payload.payload, extraPayload);
                }

                return payload;
            }

            function updatePreview() {
                try {
                    ensureHeartbeatDefaults();
                    let previewText = JSON.stringify(buildPreviewPayload(), null, 2);
                    if (appendNewlineEl && appendNewlineEl.checked) {
                        previewText += "\n";
                    }
                    payloadPreviewEl.value = previewText;
                } catch (error) {
                    payloadPreviewEl.value = "Preview error: " + error.message;
                }
            }

            if (topicPresetEl) {
                topicPresetEl.addEventListener("change", function () {
                    topicEl.value = topicPresetEl.value;
                    updatePreview();
                });
            }

            if (deviceTypeEl) {
                deviceTypeEl.addEventListener("change", updatePreview);
            }

            [
                topicEl,
                modeEl,
                deviceNameEl,
                commandEl,
                extraPayloadEl,
                plainTextEl,
                appendNewlineEl
            ].forEach(function (element) {
                if (!element) {
                    return;
                }
                element.addEventListener("input", updatePreview);
                element.addEventListener("change", updatePreview);
            });

            updatePreview();
        })();
    </script>
</body>
</html>
"""


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
                    "last_topic": snapshot.get("last_topic")
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
        return render_template_string(DEVICE_LIST_TEMPLATE, devices=devices)

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
                return render_template_string(
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

        return render_template_string(
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
