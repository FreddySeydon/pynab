#!/usr/bin/env python3
import json
import socket
import sys


def send_to_nabd(packet):
    try:
        with socket.create_connection(("127.0.0.1", 10543), timeout=5) as s:
            s.sendall((json.dumps(packet) + "\r\n").encode("utf-8"))
    except OSError as err:
        print(f"Error sending command to nabd: {err}", file=sys.stderr)


def idle():
    send_to_nabd({"type": "info", "info_id": "wyoming"})
    send_to_nabd({"type": "ears", "left": 0, "right": 0})


def listening():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "wyoming",
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
            "info_id": "wyoming",
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


def speaking():
    send_to_nabd(
        {
            "type": "info",
            "info_id": "wyoming",
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
            "info_id": "wyoming",
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


def main():
    if len(sys.argv) < 2:
        print("Usage: wyoming_event_handler.py <event>", file=sys.stderr)
        sys.exit(1)

    event = sys.argv[1]
    if event == "detect":
        idle()
    elif event in ("detection", "stt-start"):
        listening()
    elif event == "stt-stop":
        processing()
    elif event == "tts-start":
        speaking()
    elif event == "tts-stop":
        idle()
    elif event == "error":
        error()


if __name__ == "__main__":
    main()
