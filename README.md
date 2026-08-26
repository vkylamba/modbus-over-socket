#### Modbus over socket

#### Web Admin UI

A lightweight web admin is now available for device management.

Default UI port:
- Web UI: `WEB_UI_PORT` (default `8080`)

Features:
- See currently connected devices
- Monitoring dashboard summary with connected device count and total RX/TX message+byte counters
- Optional auto-refresh for dashboard (`/?auto_refresh=5` or `10`)
- Stale device indicator based on last RX time (threshold via `STALE_DEVICE_SECONDS`, default `90`)
- View each device's last update time
- Set device type (`Mona` or `Other`) from list and details page
- Open a device details page
- View per-device active logger list and per-device RX/TX flow stats
- Inspect recent inbound and outbound device traffic in a scrollable panel
- Load a template from `config-files/templates`, edit JSON, and deploy runtime configuration to a connected device from the device detail page
- Build either a structured JSON command payload or a topic + plain-text payload
- Auto-generate `command_id` values on every send
- Send command payloads on the existing TCP device connection

Mona behavior:
- Tracks `device_name` and `mac` from Mona status payloads when available
- Shows Mona command topic presets in details page:
	- `/<device_name>/devices/<device_name>/cmd-req`
	- `/<device_name>/devices/<device_name>/update-trigger`
	- `/iotaapsys/services/heartbeat`

Mona config template:
- Use `config-files/templates/mona_device_template.json` as a base template.
- Logger config is now supported using `loggers` in device config.
- Default logger is `json_store` (writes to `data/data.json`).
- Optional external logger example:
  - `iot.py` with `options.api_key_env` set to `DEVICE_API_KEY`.

Serial device config template:
- Use `config-files/templates/serial_device_template.json` for function code `4` (input registers).
- Use `config-files/templates/serial_device_template_fc3.json` for function code `3` (holding registers).
- Includes serial/RTU communication fields and sample register entries.
- Includes logger configuration with per-device API key mapping using `dev` and `device_id`.

Example plain-text payload in the web UI:
- Topic: `/iotaapsys/services/heartbeat`
- Plain Text Payload: `epoch_ms 1786717797`

Open in browser:

```bash
http://127.0.0.1:8080/
```

#### Admin Socket Interface

The server now also exposes an admin TCP interface so you can list connected
devices, select one by `device_id`, send payloads, and read one response frame.

Default ports:
- Device socket: `SOCKET_PORT` (default `8024`)
- Admin socket: `ADMIN_SOCKET_PORT` (default `9024`)

Admin request format (one JSON per line):

```json
{"action":"status"}
```

```json
{"action":"list"}
```

```json
{"action":"send","device_id":"1","data":"Hello device","encoding":"utf-8","recv_timeout":3,"max_bytes":4096}
```

```json
{"action":"send","device_id":"1","data":"010300000002c40b","encoding":"hex","recv_timeout":3}
```

Admin response format:

```json
{"ok":true,"response_hex":"...","response_text":"..."}
```

Quick examples:

```bash
echo '{"action":"status"}' | nc 127.0.0.1 9024
```

```bash
echo '{"action":"list"}' | nc 127.0.0.1 9024
```

```bash
echo '{"action":"send","device_id":"1","data":"ping","encoding":"utf-8"}' | nc 127.0.0.1 9024
```

#### Admin CLI Tool

Use the CLI wrapper for the admin interface:

```bash
python3 admin_cli.py status
```

```bash
python3 admin_cli.py list
```

```bash
python3 admin_cli.py send --device-id 1 --data ping
```

If device responses are delayed, increase wait timeout:

```bash
python3 admin_cli.py send --device-id 1 --data ping --recv-timeout 10
```

Fire-and-forget send (do not wait for response):

```bash
python3 admin_cli.py send --device-id 1 --data ping --no-wait
```

JSON payload to device (zsh-safe quoting):

```bash
python3 admin_cli.py send --device-id 1 --data '{"hello":"world"}' --append-newline --recv-timeout 10
```

If you want to include escape sequences directly in `--data`, decode them first in the CLI:

```bash
python3 admin_cli.py send --device-id 1 --data '{"topic":"/dev/devices/DEVICE123/cmd-req","payload":{"command":"restart","device":"DEVICE123","command_id":"abc-1"}}\n' --decode-escapes --recv-timeout 10
```

Hex payload example:

```bash
python3 admin_cli.py send --device-id 1 --encoding hex --data 010300000002c40b
```

Custom host/port example:

```bash
python3 admin_cli.py --host 127.0.0.1 --port 9024 list
```