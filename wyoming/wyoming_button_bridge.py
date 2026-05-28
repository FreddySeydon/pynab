#!/usr/bin/env python3
import sys
import socket
import json
import urllib.request
import urllib.error
import logging
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

NABD_HOST = '127.0.0.1'
NABD_PORT = 10543
# Read Home Assistant Webhook URL from environment variable
HA_WEBHOOK_URL = os.environ.get("HA_WEBHOOK_URL", "")

def trigger_home_assistant_webhook(event_type):
    if not HA_WEBHOOK_URL:
        logging.warning("HA_WEBHOOK_URL is not set. Button event ignored.")
        return

    logging.info(f"Triggering Home Assistant Webhook for event: {event_type}")
    payload = json.dumps({"event": event_type, "device": "Nabaztag"}).encode('utf-8')
    
    req = urllib.request.Request(
        HA_WEBHOOK_URL,
        data=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.getcode()
            logging.info(f"Webhook triggered successfully. Response status: {status}")
    except urllib.error.URLError as e:
        logging.error(f"Failed to trigger Home Assistant Webhook: {e}")

def main():
    if HA_WEBHOOK_URL:
        logging.info(f"Starting Wyoming Button Bridge with Webhook: {HA_WEBHOOK_URL}")
    else:
        logging.info("Starting Wyoming Button Bridge (No Webhook URL configured, running in logging mode)")

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            logging.info(f"Connecting to nabd at {NABD_HOST}:{NABD_PORT}...")
            s.connect((NABD_HOST, NABD_PORT))
            logging.info("Connected to nabd. Listening for button events...")
            
            # Read socket line by line
            f = s.makefile('r', encoding='utf-8')
            for line in f:
                try:
                    packet = json.loads(line.strip())
                    if packet.get("type") == "button_event":
                        event_type = packet.get("event")
                        logging.info(f"Detected button event: {event_type}")
                        if event_type == "single":
                            trigger_home_assistant_webhook("single_click")
                        elif event_type == "double":
                            trigger_home_assistant_webhook("double_click")
                        elif event_type == "long":
                            trigger_home_assistant_webhook("long_press")
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logging.error(f"Error parsing button event line: {e}")
            
            s.close()
        except socket.error as e:
            logging.error(f"Socket connection lost/failed: {e}")
        
        # Retry connection after 5 seconds
        logging.info("Retrying in 5 seconds...")
        import time
        time.sleep(5)

if __name__ == "__main__":
    main()
