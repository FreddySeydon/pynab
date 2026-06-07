#!/usr/bin/env python3
import sys
import socket
import json


def send_to_nabd(packet):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 10543))
        s.sendall((json.dumps(packet) + "\r\n").encode("utf-8"))
        s.close()
    except Exception as e:
        print(f"Error sending command to nabd: {e}", file=sys.stderr)


def set_center_info(color, tempo=100):
    send_to_nabd(
        {
            "type": "info",
            "info_id": "wyoming",
            "animation": {
                "tempo": tempo,
                "colors": [
                    {
                        "left": "000000",
                        "center": color,
                        "right": "000000",
                    }
                ],
            },
        }
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: wyoming_event_handler.py <event>", file=sys.stderr)
        sys.exit(1)

    event = sys.argv[1]
    print(f"wyoming_event_handler: {event}", file=sys.stderr, flush=True)

    if event == "detect":
        # Waiting for wake word: LEDs off, ears to default (0, 0)
        # Clear any active info animations
        send_to_nabd({"type": "info", "info_id": "wyoming"})
        send_to_nabd({"type": "ears", "left": 0, "right": 0})

    elif event == "detection":
        # Wake word detected: blue center light, ears slightly forward.
        set_center_info("0000ff")
        send_to_nabd({"type": "ears", "left": 4, "right": 4})

    elif event == "stt-start":
        # Listening: blue center light, ears slightly forward.
        set_center_info("0000ff")
        send_to_nabd({"type": "ears", "left": 4, "right": 4})

    elif event == "stt-stop":
        # Thinking: white center light.
        set_center_info("ffffff")

    elif event == "tts-start":
        # Speaking: green center light, wiggle ears.
        set_center_info("00ff00")
        send_to_nabd({"type": "ears", "left": 15, "right": 15})

    elif event == "tts-stop":
        # Back to idle: Clear LEDs and reset ears
        send_to_nabd({"type": "info", "info_id": "wyoming"})
        send_to_nabd({"type": "ears", "left": 0, "right": 0})

    elif event == "error":
        # Error: Blink nose light red
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


if __name__ == "__main__":
    main()
