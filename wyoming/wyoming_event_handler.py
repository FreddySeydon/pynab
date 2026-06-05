#!/usr/bin/env python3
import sys
import socket
import json

def send_to_nabd(packet):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('127.0.0.1', 10543))
        s.sendall((json.dumps(packet) + '\r\n').encode('utf-8'))
        s.close()
    except Exception as e:
        print(f"Error sending command to nabd: {e}", file=sys.stderr)

def main():
    if len(sys.argv) < 2:
        print("Usage: wyoming_event_handler.py <event>", file=sys.stderr)
        sys.exit(1)

    event = sys.argv[1]

    if event == "detect":
        # Waiting for wake word: LEDs off, ears to default (0, 0)
        # Clear any active info animations
        send_to_nabd({"type": "info", "info_id": "wyoming"})
        send_to_nabd({"type": "ears", "left": 0, "right": 0})
    
    elif event == "detection" or event == "stt-start":
        # Wake word detected / listening: blue center light, ears slightly forward.
        send_to_nabd({
            "type": "info",
            "info_id": "wyoming",
            "animation": {
                "tempo": 100,
                "colors": [{"left": "000000", "center": "0000ff", "right": "000000"}]
            }
        })
        send_to_nabd({"type": "ears", "left": 4, "right": 4})

    elif event == "stt-stop":
        # Thinking: Blink center nose light white rapidly
        send_to_nabd({
            "type": "info",
            "info_id": "wyoming",
            "animation": {
                "tempo": 200,
                "colors": [
                    {"left": "000000", "center": "ffffff", "right": "000000"},
                    {"left": "000000", "center": "000000", "right": "000000"}
                ]
            }
        })

    elif event == "tts-start":
        # Speaking: Blink center nose light green, wiggle ears
        send_to_nabd({
            "type": "info",
            "info_id": "wyoming",
            "animation": {
                "tempo": 150,
                "colors": [
                    {"left": "000000", "center": "00ff00", "right": "000000"},
                    {"left": "000000", "center": "000000", "right": "000000"}
                ]
            }
        })
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
