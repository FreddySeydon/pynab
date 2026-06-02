import json
import logging
import os
import socket
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


LOG = logging.getLogger("habridge")

BRIDGE_HOST = os.environ.get("HABRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.environ.get("HABRIDGE_PORT", "10544"))
BRIDGE_TOKEN = os.environ.get("HABRIDGE_TOKEN", "")
NABD_HOST = os.environ.get("HABRIDGE_NABD_HOST", "127.0.0.1")
NABD_PORT = int(os.environ.get("HABRIDGE_NABD_PORT", "10543"))
NABD_TIMEOUT = float(os.environ.get("HABRIDGE_NABD_TIMEOUT", "10"))
MAX_BODY_BYTES = int(os.environ.get("HABRIDGE_MAX_BODY_BYTES", "65536"))
DEFAULT_INFO_ID = os.environ.get("HABRIDGE_INFO_ID", "ha_bridge")
HA_URL = os.environ.get("HABRIDGE_HA_URL", "").rstrip("/")
HA_TOKEN = os.environ.get("HABRIDGE_HA_TOKEN", "")
HA_TTS_TIMEOUT = float(os.environ.get("HABRIDGE_HA_TTS_TIMEOUT", "30"))


WEATHER_CONDITIONS = {
    "de": {
        "clear-night": "klar",
        "cloudy": "bewoelkt",
        "fog": "neblig",
        "hail": "hagelig",
        "lightning": "gewittrig",
        "lightning-rainy": "gewittrig und regnerisch",
        "partlycloudy": "teilweise bewoelkt",
        "pouring": "stark regnerisch",
        "rainy": "regnerisch",
        "snowy": "verschneit",
        "snowy-rainy": "Schneeregen",
        "sunny": "sonnig",
        "windy": "windig",
        "windy-variant": "windig und bewoelkt",
    },
    "en": {
        "clear-night": "clear",
        "cloudy": "cloudy",
        "fog": "foggy",
        "hail": "hailing",
        "lightning": "stormy",
        "lightning-rainy": "stormy and rainy",
        "partlycloudy": "partly cloudy",
        "pouring": "pouring",
        "rainy": "rainy",
        "snowy": "snowy",
        "snowy-rainy": "snowy and rainy",
        "sunny": "sunny",
        "windy": "windy",
        "windy-variant": "windy and cloudy",
    },
}


class BridgeError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def read_json_line(sock_file) -> Optional[Dict[str, Any]]:
    line = sock_file.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def send_to_nabd(packet: Dict[str, Any]) -> Dict[str, Any]:
    packet = dict(packet)
    request_id = packet.setdefault("request_id", "ha-" + uuid.uuid4().hex)

    with socket.create_connection((NABD_HOST, NABD_PORT), timeout=NABD_TIMEOUT) as sock:
        sock.settimeout(NABD_TIMEOUT)
        sock_file = sock.makefile("rwb")
        initial_state = read_json_line(sock_file)
        sock_file.write((json.dumps(packet) + "\r\n").encode("utf-8"))
        sock_file.flush()

        while True:
            response = read_json_line(sock_file)
            if response is None:
                raise BridgeError(
                    HTTPStatus.BAD_GATEWAY,
                    "nabd closed the connection without a response",
                )
            if response.get("type") == "response" and response.get("request_id") == request_id:
                return {"initial_state": initial_state, "response": response}


def build_audio_packet(audio_url: str, cancelable: bool = False) -> Dict[str, Any]:
    if not isinstance(audio_url, str):
        raise BridgeError(HTTPStatus.BAD_REQUEST, "url must be a string")
    audio_url = audio_url.strip()
    if not (audio_url.startswith("http://") or audio_url.startswith("https://")):
        raise BridgeError(HTTPStatus.BAD_REQUEST, "url must start with http:// or https://")
    if not urlparse(audio_url).path.lower().endswith(".mp3"):
        raise BridgeError(HTTPStatus.BAD_REQUEST, "url must point to an MP3 file")
    return {
        "type": "command",
        "sequence": [{"audio": [audio_url]}],
        "cancelable": bool(cancelable),
    }


def get_ha_tts_url(body: Dict[str, Any]) -> str:
    if not HA_URL or not HA_TOKEN:
        raise BridgeError(
            HTTPStatus.BAD_REQUEST,
            "HABRIDGE_HA_URL and HABRIDGE_HA_TOKEN must be configured",
        )

    engine_id = body.get("engine_id")
    message = body.get("message")
    if not isinstance(engine_id, str) or not engine_id:
        raise BridgeError(HTTPStatus.BAD_REQUEST, "engine_id must be a non-empty string")
    if not isinstance(message, str) or not message:
        raise BridgeError(HTTPStatus.BAD_REQUEST, "message must be a non-empty string")

    payload: Dict[str, Any] = {
        "engine_id": engine_id,
        "message": message,
        "cache": body.get("cache", True),
        "options": body.get(
            "options",
            {
                "preferred_format": "mp3",
                "preferred_sample_rate": 22050,
                "preferred_sample_channels": 1,
            },
        ),
    }
    if "language" in body:
        payload["language"] = body["language"]

    req = Request(
        HA_URL + "/api/tts_get_url",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + HA_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=HA_TTS_TIMEOUT) as response:  # nosec B310
        response_data = json.loads(response.read().decode("utf-8"))

    path = response_data.get("path")
    if isinstance(path, str) and path:
        return HA_URL + path

    audio_url = response_data.get("url")
    if isinstance(audio_url, str) and audio_url:
        return audio_url

    raise BridgeError(HTTPStatus.BAD_GATEWAY, "Home Assistant did not return a TTS URL")


def build_weather_message(body: Dict[str, Any]) -> str:
    language = body.get("message_language", body.get("language", "de"))
    if not isinstance(language, str):
        raise BridgeError(HTTPStatus.BAD_REQUEST, "language must be a string")
    language = language.lower().split("-")[0]
    if language not in WEATHER_CONDITIONS:
        language = "de"

    condition = body.get("condition", "unknown")
    if not isinstance(condition, str) or not condition:
        condition = "unknown"

    condition_text = WEATHER_CONDITIONS[language].get(condition, condition)
    temperature = body.get("temperature")
    unit = body.get("unit")
    if not isinstance(unit, str) or not unit:
        unit = "Grad" if language == "de" else "degrees"

    if temperature in (None, "", "unknown", "unavailable"):
        if language == "de":
            return f"Das Wetter ist {condition_text}."
        return f"The weather is {condition_text}."

    if language == "de":
        spoken_unit = "Grad" if unit in ("°C", "°F", "C", "F") else unit
        return f"Das Wetter ist {condition_text}, bei {temperature} {spoken_unit}."

    return f"The weather is {condition_text}, {temperature} {unit}."


def play_ha_tts(body: Dict[str, Any]) -> Dict[str, Any]:
    audio_url = get_ha_tts_url(body)
    packet = build_audio_packet(audio_url, bool(body.get("cancelable", False)))
    result = send_to_nabd(packet)
    result["audio_url"] = audio_url
    return result


def validate_info_colors(colors: Any) -> List[Dict[str, str]]:
    if not isinstance(colors, list) or not colors:
        raise BridgeError(HTTPStatus.BAD_REQUEST, "colors must be a non-empty list")

    normalized = []
    for item in colors:
        if not isinstance(item, dict):
            raise BridgeError(HTTPStatus.BAD_REQUEST, "each color item must be an object")
        normalized_item = {}
        for led in ("left", "center", "right"):
            color = item.get(led, "000000")
            if not isinstance(color, str):
                raise BridgeError(HTTPStatus.BAD_REQUEST, f"{led} must be a hex string")
            color = color.strip().lower().lstrip("#")
            if len(color) != 6 or any(c not in "0123456789abcdef" for c in color):
                raise BridgeError(HTTPStatus.BAD_REQUEST, f"{led} must be RRGGBB hex")
            normalized_item[led] = color
        normalized.append(normalized_item)
    return normalized


def validate_ear(value: Any, name: str) -> int:
    if not isinstance(value, int):
        raise BridgeError(HTTPStatus.BAD_REQUEST, f"{name} must be an integer")
    if value < 0 or value > 16:
        raise BridgeError(HTTPStatus.BAD_REQUEST, f"{name} must be between 0 and 16")
    return value


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "PynabHABridge/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), format % args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def handle_request(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            self.require_auth(parsed)

            if method == "GET" and parsed.path == "/health":
                result = send_to_nabd({"type": "gestalt"})
                self.write_json(HTTPStatus.OK, {"status": "ok", "nabd": result})
                return

            if method != "POST":
                raise BridgeError(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

            body = self.read_body()
            result = self.route_post(parsed.path, body)
            self.write_json(HTTPStatus.OK, {"status": "ok", "nabd": result})
        except BridgeError as err:
            self.write_json(err.status, {"status": "error", "message": err.message})
        except socket.timeout:
            self.write_json(
                HTTPStatus.BAD_GATEWAY,
                {"status": "error", "message": "timed out talking to nabd"},
            )
        except Exception as err:
            LOG.exception("Unhandled bridge error")
            self.write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"status": "error", "message": str(err)},
            )

    def route_post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if path == "/leds/info":
            info_id = body.get("info_id", DEFAULT_INFO_ID)
            if not isinstance(info_id, str) or not info_id:
                raise BridgeError(HTTPStatus.BAD_REQUEST, "info_id must be a non-empty string")
            tempo = body.get("tempo", 50)
            if not isinstance(tempo, (int, float)) or tempo <= 0:
                raise BridgeError(HTTPStatus.BAD_REQUEST, "tempo must be a positive number")
            packet = {
                "type": "info",
                "info_id": info_id,
                "animation": {
                    "tempo": tempo,
                    "colors": validate_info_colors(body.get("colors")),
                },
            }
            return send_to_nabd(packet)

        if path == "/leds/clear":
            info_id = body.get("info_id", DEFAULT_INFO_ID)
            if not isinstance(info_id, str) or not info_id:
                raise BridgeError(HTTPStatus.BAD_REQUEST, "info_id must be a non-empty string")
            return send_to_nabd({"type": "info", "info_id": info_id})

        if path == "/ears":
            left = validate_ear(body.get("left"), "left")
            right = validate_ear(body.get("right"), "right")
            packet = {"type": "ears", "left": left, "right": right}
            if "event" in body:
                if not isinstance(body["event"], bool):
                    raise BridgeError(HTTPStatus.BAD_REQUEST, "event must be a boolean")
                packet["event"] = body["event"]
            return send_to_nabd(packet)

        if path == "/sleep":
            return send_to_nabd({"type": "sleep"})

        if path == "/wakeup":
            return send_to_nabd({"type": "wakeup"})

        if path == "/audio/url":
            packet = build_audio_packet(body.get("url"), bool(body.get("cancelable", False)))
            return send_to_nabd(packet)

        if path == "/tts/ha":
            return play_ha_tts(body)

        if path == "/weather/say":
            tts_body = dict(body)
            tts_body["message"] = build_weather_message(body)
            if "tts_language" in tts_body:
                tts_body["language"] = tts_body.pop("tts_language")
            else:
                tts_body.pop("language", None)
            tts_body.pop("message_language", None)
            result = play_ha_tts(tts_body)
            result["message"] = tts_body["message"]
            return result

        if path == "/packet":
            packet = body.get("packet", body)
            if not isinstance(packet, dict) or "type" not in packet:
                raise BridgeError(HTTPStatus.BAD_REQUEST, "packet must be an object with a type")
            return send_to_nabd(packet)

        raise BridgeError(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def read_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_BODY_BYTES:
            raise BridgeError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
        if content_length == 0:
            return {}
        raw_body = self.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            raise BridgeError(HTTPStatus.BAD_REQUEST, "request body must be JSON")
        if not isinstance(body, dict):
            raise BridgeError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
        return body

    def require_auth(self, parsed) -> None:
        if not BRIDGE_TOKEN:
            return
        auth_header = self.headers.get("Authorization", "")
        if auth_header == "Bearer " + BRIDGE_TOKEN:
            return
        query_token = parse_qs(parsed.query).get("token", [""])[0]
        if query_token == BRIDGE_TOKEN:
            return
        raise BridgeError(HTTPStatus.UNAUTHORIZED, "missing or invalid token")

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def write_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(response)


def main() -> None:
    logging.basicConfig(level=os.environ.get("HABRIDGE_LOG_LEVEL", "INFO"))
    server_address: Tuple[str, int] = (BRIDGE_HOST, BRIDGE_PORT)
    httpd = ThreadingHTTPServer(server_address, BridgeHandler)
    LOG.info("HA bridge listening on %s:%s", BRIDGE_HOST, BRIDGE_PORT)
    httpd.serve_forever()
