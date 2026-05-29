#!/usr/bin/env python3
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request

NABD_HOST = "127.0.0.1"
NABD_PORT = 10543
HA_WEBHOOK_URL = os.environ.get("HA_WEBHOOK_URL", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def trigger_home_assistant_webhook(event_type):
    if not HA_WEBHOOK_URL:
        logging.warning("HA_WEBHOOK_URL is not set. Button event ignored.")
        return

    payload = json.dumps(
        {"event": event_type, "device": "Nabaztag"}
    ).encode("utf-8")
    req = urllib.request.Request(
        HA_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            logging.info("Webhook triggered with status %s", response.status)
    except urllib.error.URLError as err:
        logging.error("Failed to trigger Home Assistant webhook: %s", err)


def handle_packet(packet):
    if packet.get("type") != "button_event":
        return

    event_type = packet.get("event")
    logging.info("Detected button event: %s", event_type)

    if event_type == "click":
        trigger_home_assistant_webhook("single_click")
    elif event_type == "double_click":
        trigger_home_assistant_webhook("double_click")
    elif event_type in ("hold", "click_and_hold"):
        trigger_home_assistant_webhook("long_press")


def main():
    if HA_WEBHOOK_URL:
        logging.info("Starting Wyoming button bridge")
    else:
        logging.info(
            "Starting Wyoming button bridge without HA_WEBHOOK_URL; "
            "events will only be logged."
        )

    while True:
        try:
            logging.info("Connecting to nabd at %s:%s", NABD_HOST, NABD_PORT)
            with socket.create_connection((NABD_HOST, NABD_PORT)) as sock:
                logging.info("Connected to nabd. Listening for events.")
                for line in sock.makefile("r", encoding="utf-8"):
                    try:
                        handle_packet(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
                    except Exception as err:
                        logging.error("Error handling button event: %s", err)
        except OSError as err:
            logging.error("Socket connection lost/failed: %s", err)

        logging.info("Retrying in 5 seconds")
        time.sleep(5)


if __name__ == "__main__":
    main()
