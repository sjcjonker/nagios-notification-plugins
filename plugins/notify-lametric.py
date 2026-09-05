#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Send a Nagios notification to a LaMetric Time device."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request


TIMEOUT = 5
MAX_MESSAGE_LENGTH = 1_024
DEFAULT_CONFIG = Path("/etc/nagios4/private/notifications.env")
LEVELS = {
    "UP": ("18573", "notification2"),
    "OK": ("18573", "notification2"),
    "RECOVERY": ("18573", "notification2"),
    "DOWN": ("18412", "negative5"),
    "WARNING": ("18419", "negative5"),
    "CRITICAL": ("18412", "negative4"),
    "UNKNOWN": ("1396", "negative3"),
}
DEFAULT_LEVEL = ("555", "negative2")
HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def parse_hour(value: str) -> int:
    try:
        hour = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid hour: {value}") from exc
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be between 0 and 23: {value}")
    return hour


def in_silent_window(window: str | None, now: dt.datetime) -> bool:
    if not window:
        return False
    try:
        start_text, end_text = window.split(":", 1)
    except ValueError as exc:
        raise ValueError("silent window must use START:END, for example 23:9") from exc
    start = parse_hour(start_text)
    end = parse_hour(end_text)
    if start == end:
        raise ValueError("silent window start and end must differ")
    if start < end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def read_config(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def notification_endpoint(host: str) -> str:
    value = host.strip()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        labels = value.rstrip(".").split(".")
        if len(value) > 253 or not labels or not all(HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError("LaMetric host must be an IP address or DNS hostname")
        authority = value.rstrip(".")
    else:
        authority = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{authority}:8080/api/v2/device/notifications"


def values_from_environment(kind: str) -> tuple[str, str, str]:
    host = os.environ.get("NAGIOS__CONTACTLAMETRICIP", "")
    host_name = os.environ.get("NAGIOS_HOSTNAME", "")
    if kind == "host":
        level = os.environ.get("NAGIOS_HOSTSTATE", "")
        output = os.environ.get("NAGIOS_HOSTOUTPUT", "")
        message = f"{host_name} - {level} - '{output}'"
    else:
        level = os.environ.get("NAGIOS_SERVICESTATE", "")
        service = os.environ.get("NAGIOS_SERVICEDESC", "")
        output = os.environ.get("NAGIOS_SERVICEOUTPUT", "")
        message = f"{host_name} - {level} - {service} - '{output}'"
    if not host or not host_name or not level:
        raise ValueError("required Nagios environment variables are missing")
    return host, level, message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--nagios-host", action="store_true")
    mode.add_argument("--nagios-service", action="store_true")
    parser.add_argument("-H", "--host", help="LaMetric IP address or hostname")
    parser.add_argument("-G", "--guid", help="override LAMETRIC_GUID from the config")
    parser.add_argument("-l", "--level", help="Nagios state")
    parser.add_argument("-m", "--message", help="notification text")
    parser.add_argument("-s", "--silent-window", metavar="START:END")
    parser.add_argument(
        "-f", "--config", type=Path,
        default=Path(os.environ.get("NAGIOS_NOTIFICATION_CONFIG", DEFAULT_CONFIG)),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = read_config(args.config) if args.config.exists() else {}
        if args.nagios_host or args.nagios_service:
            args.host, args.level, args.message = values_from_environment(
                "host" if args.nagios_host else "service"
            )
        elif not args.host or not args.level or not args.message:
            raise ValueError("host, level and message are required outside Nagios mode")
        guid = args.guid or config.get("LAMETRIC_GUID", "")
        if not guid:
            if not args.config.exists():
                raise ValueError(f"cannot read {args.config}: file does not exist")
            raise ValueError(f"LAMETRIC_GUID is missing from {args.config}")
        silent_window = args.silent_window
        if silent_window is None:
            silent_window = config.get("LAMETRIC_SILENT_WINDOW")
        if in_silent_window(silent_window, dt.datetime.now().astimezone()):
            return 0
        if len(args.message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"message exceeds {MAX_MESSAGE_LENGTH} characters")
        endpoint = notification_endpoint(args.host)
    except ValueError as exc:
        print(f"LaMetric notification configuration error: {exc}", file=sys.stderr)
        return 2

    icon, sound = LEVELS.get(args.level.upper(), DEFAULT_LEVEL)
    payload = {
        "priority": "critical",
        "model": {
            "cycles": 1,
            "frames": [{"icon": icon, "text": args.message}],
            "sound": {"category": "notifications", "id": sound},
        },
    }
    credentials = base64.b64encode(f"dev:{guid}".encode()).decode()
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.status not in {200, 201}:
                print(f"LaMetric notification failed with HTTP {response.status}", file=sys.stderr)
                return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"LaMetric notification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
