#!/usr/bin/env python3
import argparse
import json
import socket
import sys


def decode_escape_sequences(value):
    return bytes(value, "utf-8").decode("unicode_escape")


def send_request(host, port, request_payload, timeout):
    data = (json.dumps(request_payload) + "\n").encode("utf-8")

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(data)

        response = b""
        while b"\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

    response_text = response.decode("utf-8", errors="replace").strip()
    if not response_text:
        raise RuntimeError("Empty response from admin socket")

    return json.loads(response_text)


def print_json(payload):
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_status(args):
    payload = {"action": "status"}
    response = send_request(args.host, args.port, payload, args.timeout)
    print_json(response)
    return 0 if response.get("ok") else 1


def cmd_list(args):
    payload = {"action": "list"}
    response = send_request(args.host, args.port, payload, args.timeout)
    print_json(response)
    return 0 if response.get("ok") else 1


def cmd_send(args):
    payload_data = args.data
    if args.encoding == "utf-8" and args.decode_escapes:
        payload_data = decode_escape_sequences(payload_data)

    payload = {
        "action": "send",
        "device_id": str(args.device_id),
        "data": payload_data,
        "encoding": args.encoding,
        "recv_timeout": args.recv_timeout,
        "max_bytes": args.max_bytes,
        "wait_for_response": not args.no_wait,
        "append_newline": args.append_newline,
    }
    response = send_request(args.host, args.port, payload, args.timeout)
    print_json(response)
    return 0 if response.get("ok") else 1


def build_parser():
    parser = argparse.ArgumentParser(
        description="CLI for socket server admin interface"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Admin socket host")
    parser.add_argument("--port", type=int, default=9024, help="Admin socket port")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Network timeout in seconds"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show admin server status")
    status_parser.set_defaults(func=cmd_status)

    list_parser = subparsers.add_parser(
        "list",
        help="List connected devices with their device_id"
    )
    list_parser.set_defaults(func=cmd_list)

    send_parser = subparsers.add_parser(
        "send",
        help="Send payload to a specific connected device"
    )
    send_parser.add_argument(
        "--device-id",
        required=True,
        help="Target device ID from the list command"
    )
    send_parser.add_argument(
        "--data",
        required=True,
        help="Payload string or hex data based on encoding"
    )
    send_parser.add_argument(
        "--encoding",
        choices=["utf-8", "hex"],
        default="utf-8",
        help="How to encode --data before sending"
    )
    send_parser.add_argument(
        "--recv-timeout",
        type=float,
        default=3.0,
        help="Device response timeout in seconds"
    )
    send_parser.add_argument(
        "--max-bytes",
        type=int,
        default=4096,
        help="Maximum response bytes to read"
    )
    send_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Send payload and return immediately without waiting for device response"
    )
    send_parser.add_argument(
        "--append-newline",
        action="store_true",
        help="Append newline to payload before sending (useful for line-delimited JSON devices)"
    )
    send_parser.add_argument(
        "--decode-escapes",
        action="store_true",
        help="Decode escape sequences in --data such as \\n before sending"
    )
    send_parser.set_defaults(func=cmd_send)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except (ConnectionError, OSError, RuntimeError, json.JSONDecodeError) as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
