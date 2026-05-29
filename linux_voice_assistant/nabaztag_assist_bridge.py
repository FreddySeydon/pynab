#!/usr/bin/env python3
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NABD_HOST = "127.0.0.1"
NABD_PORT = 10543

HA_URL = os.environ.get("HA_URL", "").rstrip("/")
HA_ACCESS_TOKEN = os.environ.get("HA_ACCESS_TOKEN", "")
HA_ENTITY_ID = os.environ.get("HA_ASSIST_SATELLITE_ENTITY_ID", "")
POLL_SECONDS = float(os.environ.get("HA_STATE_POLL_SECONDS", "1.0"))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def send_to_nabd(packet):
    try:
        with socket.create_connection((NABD_HOST, NABD_PORT), timeout=5) as s:
            s.sendall((json.dumps(packet) + "\r\n").encode("utf-8"))
    except OSError as err:
        logging.error("Error sending command to nabd: %s", err)


def idle():
    send_to_nabd({"type": "info", "info_id": "assist"})
    send_to_nabd({"type": "ears", "left": 0, "right": 0})


def listening():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "assist",
            "animation": {
                "tempo": 100,
                "colors": [
                    {
                        "left": "000000",
                        "center": "0000ff",
                        "right": "000000",
                    }
                ],
            },
        }
    )
    send_to_nabd({"type": "ears", "left": 10, "right": 10})


def processing():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "assist",
            "animation": {
                "tempo": 200,
                "colors": [
                    {
                        "left": "000000",
                        "center": "ffffff",
                        "right": "000000",
                    },
                    {
                        "left": "000000",
                        "center": "000000",
                        "right": "000000",
                    },
                ],
            },
        }
    )


def responding():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "assist",
            "animation": {
                "tempo": 150,
                "colors": [
                    {
                        "left": "000000",
                        "center": "00ff00",
                        "right": "000000",
                    },
                    {
                        "left": "000000",
                        "center": "000000",
                        "right": "000000",
                    },
                ],
            },
        }
    )
    send_to_nabd({"type": "ears", "left": 15, "right": 15})


def error():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "assist",
            "animation": {
                "tempo": 250,
                "colors": [
                    {
                        "left": "000000",
                        "center": "ff0000",
                        "right": "000000",
                    },
                    {
                        "left": "000000",
                        "center": "000000",
                        "right": "000000",
                    },
                ],
            },
        }
    )


STATE_HANDLERS = {
    "idle": idle,
    "ready": idle,
    "standby": idle,
    "listening": listening,
    "detecting": listening,
    "wake_word": listening,
    "wakeword": listening,
    "processing": processing,
    "thinking": processing,
    "responding": responding,
    "speaking": responding,
    "unavailable": error,
    "unknown": error,
}


def read_assist_state():
    quoted_entity = urllib.parse.quote(HA_ENTITY_ID, safe="")
    req = urllib.request.Request(
        f"{HA_URL}/api/states/{quoted_entity}",
        headers={
            "Authorization": f"Bearer {HA_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("state", "unknown")


def bridge_enabled():
    return HA_URL and HA_ACCESS_TOKEN and HA_ENTITY_ID


def main():
    last_state = None

    while True:
        if not bridge_enabled():
            logging.info(
                "Assist bridge disabled. Set HA_URL, HA_ACCESS_TOKEN, "
                "and HA_ASSIST_SATELLITE_ENTITY_ID."
            )
            time.sleep(60)
            continue

        try:
            state = read_assist_state()
            if state != last_state:
                logging.info("Assist satellite state: %s", state)
                STATE_HANDLERS.get(state, error)()
                last_state = state
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            logging.error("Failed to read Home Assistant state: %s", err)
            error()
            last_state = None
            time.sleep(max(POLL_SECONDS, 5))
            continue
        except json.JSONDecodeError as err:
            logging.error("Invalid Home Assistant state response: %s", err)
            error()
            last_state = None

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
