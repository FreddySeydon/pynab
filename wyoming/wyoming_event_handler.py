#!/usr/bin/env python3
import sys
import socket
import json
from base64 import b64encode

def send_to_nabd(packet):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('127.0.0.1', 10543))
        s.sendall((json.dumps(packet) + '\r\n').encode('utf-8'))
        s.close()
    except Exception as e:
        print(f"Error sending command to nabd: {e}", file=sys.stderr)


def center_led_choreography(color, flashes, tempo=8):
    data = bytearray([0, 1, tempo])
    frames = []
    for _ in range(flashes):
        frames.append(color)
        frames.append((0, 0, 0))
    for index, (r, g, b) in enumerate(frames):
        wait = 0 if index == 0 else 1
        data.extend([wait, 7, 2, r, g, b, 0, 0])
    return (
        "data:application/x-nabaztag-mtl-choreography;base64,"
        + b64encode(bytes(data)).decode("ascii")
    )


def play_center_led(color, flashes, tempo=8):
    send_to_nabd(
        {
            "type": "command",
            "sequence": [
                {
                    "choreography": center_led_choreography(
                        color, flashes, tempo
                    )
                }
            ],
            "cancelable": True,
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
        # Wake word detected: ears slightly forward, no persistent LED state.
        send_to_nabd({"type": "info", "info_id": "wyoming"})
        send_to_nabd({"type": "ears", "left": 4, "right": 4})

    elif event == "stt-start":
        # Listening: short blue center light, ears slightly forward.
        play_center_led((0, 0, 255), flashes=8, tempo=8)
        send_to_nabd({"type": "ears", "left": 4, "right": 4})

    elif event == "stt-stop":
        # Thinking: short white center light.
        play_center_led((255, 255, 255), flashes=4, tempo=8)

    elif event == "tts-start":
        # Speaking: short green center light, wiggle ears.
        play_center_led((0, 255, 0), flashes=6, tempo=10)
        send_to_nabd({"type": "ears", "left": 15, "right": 15})

    elif event == "tts-stop":
        # Back to idle: Clear LEDs and reset ears
        send_to_nabd({"type": "info", "info_id": "wyoming"})
        send_to_nabd({"type": "ears", "left": 0, "right": 0})

    elif event == "error":
        # Error: Blink nose light red
        send_to_nabd({
            "type": "info",
            "info_id": "wyoming",
            "animation": {
                "tempo": 250,
                "colors": [
                    {"left": "000000", "center": "ff0000", "right": "000000"},
                    {"left": "000000", "center": "000000", "right": "000000"}
                ]
            }
        })

if __name__ == "__main__":
    main()
