import json
import logging
import math
import os
import socket
import subprocess
import uuid
from base64 import b64encode
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
RESET_INFO_IDS = [
    info_id.strip()
    for info_id in os.environ.get(
        "HABRIDGE_RESET_INFO_IDS",
        f"{DEFAULT_INFO_ID},ha_effect,ha_weather,ha_test,nabweatherd,nabweatherd_rain",
    ).split(",")
    if info_id.strip()
]
HA_URL = os.environ.get("HABRIDGE_HA_URL", "").rstrip("/")
HA_TOKEN = os.environ.get("HABRIDGE_HA_TOKEN", "")
HA_TTS_TIMEOUT = float(os.environ.get("HABRIDGE_HA_TTS_TIMEOUT", "30"))
QUIET_SERVICES = [
    service.strip()
    for service in os.environ.get(
        "HABRIDGE_QUIET_SERVICES",
        "nabclockd.service,nabsurprised.service,nabtaichid.service",
    ).split(",")
    if service.strip()
]


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


def run_systemctl(action: str, services: List[str]) -> List[Dict[str, Any]]:
    results = []
    for service in services:
        completed = subprocess.run(
            ["systemctl", action, service],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        results.append(
            {
                "service": service,
                "action": action,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
    return results


def validate_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise BridgeError(HTTPStatus.BAD_REQUEST, f"{name} must be a boolean")
    return value


def set_quiet_mode(enabled: bool) -> Dict[str, Any]:
    nabd_result = send_to_nabd(
        {
            "type": "config-update",
            "service": "nabd",
            "slot": "quiet_mode",
            "value": enabled,
        }
    )
    action = "stop" if enabled else "start"
    service_results = run_systemctl(action, QUIET_SERVICES)
    ears_result = send_to_nabd(
        {"type": "ears", "left": 10 if enabled else 0, "right": 10 if enabled else 0}
    )
    return {
        "quiet_mode": enabled,
        "nabd": nabd_result,
        "ears": ears_result,
        "services": service_results,
    }


def restart_wyoming() -> Dict[str, Any]:
    service_results = run_systemctl("restart", ["wyoming-satellite.service"])
    clear_result = send_to_nabd({"type": "info", "info_id": "wyoming"})
    return {
        "status": "ok",
        "service": service_results[0],
        "clear_status": clear_result,
    }


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


def build_audio_choreography_packet(
    audio_url: str, active_choreography: str, end_choreography: str
) -> Dict[str, Any]:
    audio_packet = build_audio_packet(audio_url)
    audio_packet["sequence"][0]["choreography"] = active_choreography
    audio_packet["sequence"].append({"choreography": end_choreography})
    return audio_packet


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
    wind_speed = body.get("wind_speed")
    wind_unit = body.get("wind_unit")
    if not isinstance(wind_unit, str) or not wind_unit:
        wind_unit = "km/h"

    def rounded_text(value: Any) -> str:
        value_text = str(value)
        try:
            value_text = str(
                Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        except (InvalidOperation, ValueError):
            pass
        return value_text

    if temperature in (None, "", "unknown", "unavailable"):
        message = (
            f"Das Wetter ist {condition_text}."
            if language == "de"
            else f"The weather is {condition_text}."
        )
    else:
        temperature_text = rounded_text(temperature)
        if language == "de":
            spoken_unit = "Grad" if unit in ("\u00b0C", "\u00b0F", "C", "F") else unit
            message = (
                f"Das Wetter ist {condition_text}, bei "
                f"{temperature_text} {spoken_unit}."
            )
        else:
            message = f"The weather is {condition_text}, {temperature_text} {unit}."

    if wind_speed not in (None, "", "unknown", "unavailable"):
        wind_text = rounded_text(wind_speed)
        if language == "de":
            spoken_wind_unit = (
                "Kilometer pro Stunde"
                if wind_unit.lower() in ("km/h", "kmh", "kmph")
                else wind_unit
            )
            message += f" Der Wind liegt bei {wind_text} {spoken_wind_unit}."
        else:
            message += f" Wind speed is {wind_text} {wind_unit}."

    return message


RGB = Tuple[int, int, int]
WeatherFrame = Dict[int, RGB]

LED_BOTTOM = 0
LED_RIGHT = 1
LED_CENTER = 2
LED_LEFT = 3
LED_NOSE = 4
WEATHER_LEDS = (LED_LEFT, LED_CENTER, LED_RIGHT, LED_BOTTOM, LED_NOSE)


def clamp_color(value: float) -> int:
    return max(0, min(255, int(round(value))))


def blend_color(start: RGB, end: RGB, fraction: float) -> RGB:
    return tuple(
        clamp_color(start[ix] + ((end[ix] - start[ix]) * fraction))
        for ix in range(3)
    )


def frame_from_color(color: RGB, leds: Tuple[int, ...] = WEATHER_LEDS) -> WeatherFrame:
    return {led: color for led in leds}


def add_weather_frame(data: bytearray, frame: WeatherFrame, wait: int = 1) -> None:
    first = True
    for led in WEATHER_LEDS:
        color = frame.get(led, (0, 0, 0))
        data.extend(
            [wait if first else 0, 7, led, color[0], color[1], color[2], 0, 0]
        )
        first = False


def add_ears(data: bytearray, wait: int, left: int, right: int) -> None:
    data.extend([wait, 8, 0, left, 0])
    data.extend([0, 8, 1, right, 0])


def weather_choreography_data_uri(
    frames: List[WeatherFrame],
    frame_duration: int = 8,
    start_ears: Optional[Tuple[int, int]] = None,
    end_ears: Optional[Tuple[int, int]] = None,
    ear_frames: Optional[Dict[int, Tuple[int, int]]] = None,
) -> str:
    data = bytearray([0, 1, frame_duration])
    if start_ears is not None:
        add_ears(data, 0, start_ears[0], start_ears[1])

    ear_frames = ear_frames or {}
    for index, frame in enumerate(frames):
        if index in ear_frames:
            left, right = ear_frames[index]
            add_ears(data, 0, left, right)
        add_weather_frame(data, frame)

    if end_ears is not None:
        add_ears(data, 1, end_ears[0], end_ears[1])

    return (
        "data:application/x-nabaztag-mtl-choreography;base64,"
        + b64encode(bytes(data)).decode("ascii")
    )


def repeated_static_frames(color: RGB, count: int = 240) -> List[WeatherFrame]:
    return [frame_from_color(color) for _ in range(count)]


def pulsing_frames(
    base: RGB,
    peak: RGB,
    count: int = 360,
    leds: Tuple[int, ...] = WEATHER_LEDS,
) -> List[WeatherFrame]:
    frames = []
    for index in range(count):
        fraction = (math.sin(index / 18.0) + 1.0) / 2.0
        frames.append(frame_from_color(blend_color(base, peak, fraction), leds))
    return frames


def rain_frames(count: int = 420) -> List[WeatherFrame]:
    frames = []
    base = (0, 0, 18)
    trail = (0, 24, 110)
    drop = (0, 85, 255)
    led_path = (LED_LEFT, LED_CENTER, LED_RIGHT, LED_BOTTOM)
    for index in range(count):
        phase = index % 28
        frame = frame_from_color(base)
        for path_index, led in enumerate(led_path):
            distance = abs(phase - (path_index * 5))
            if distance <= 2:
                frame[led] = blend_color(drop, trail, distance / 2.0)
            elif distance <= 5:
                frame[led] = blend_color(trail, base, (distance - 2) / 3.0)
        if phase in (22, 23, 24):
            frame[LED_CENTER] = blend_color(frame[LED_CENTER], (0, 50, 180), 0.5)
        frames.append(frame)
    return frames


def snow_frames(count: int = 360) -> List[WeatherFrame]:
    frames = []
    base = (18, 28, 45)
    snow = (210, 245, 255)
    led_path = (LED_LEFT, LED_NOSE, LED_CENTER, LED_RIGHT, LED_BOTTOM)
    for index in range(count):
        frame = frame_from_color(base)
        for path_index, led in enumerate(led_path):
            phase = (index + (path_index * 11)) % 45
            if phase < 12:
                frame[led] = blend_color(base, snow, math.sin((phase / 12.0) * math.pi))
        frames.append(frame)
    return frames


def lightning_frames(count: int = 360) -> List[WeatherFrame]:
    frames = []
    base = (45, 0, 105)
    flash = (255, 255, 120)
    for index in range(count):
        phase = index % 80
        if phase in (18, 19, 24):
            frames.append(frame_from_color(flash))
        elif phase in (20, 21, 25, 26):
            frames.append(frame_from_color(blend_color(base, flash, 0.45)))
        else:
            pulse = (math.sin(index / 14.0) + 1.0) / 2.0
            frames.append(frame_from_color(blend_color(base, (80, 0, 150), pulse)))
    return frames


def windy_frames(count: int = 360) -> List[WeatherFrame]:
    frames = []
    base = (0, 24, 38)
    gust = (0, 190, 165)
    led_path = (LED_LEFT, LED_CENTER, LED_RIGHT, LED_BOTTOM)
    for index in range(count):
        phase = index % 32
        frame = frame_from_color(base)
        for path_index, led in enumerate(led_path):
            distance = abs(phase - (path_index * 6))
            if distance <= 6:
                frame[led] = blend_color(gust, base, distance / 6.0)
        frames.append(frame)
    return frames


def weather_frames_for_condition(condition: str) -> List[WeatherFrame]:
    if condition in ("rainy", "pouring", "lightning-rainy"):
        return rain_frames()
    if condition in ("snowy", "snowy-rainy"):
        return snow_frames()
    if condition in ("sunny", "clear-night"):
        return repeated_static_frames((255, 210, 0))
    if condition in ("cloudy", "partlycloudy", "fog"):
        return pulsing_frames((65, 70, 78), (230, 235, 245))
    if condition in ("lightning", "hail"):
        return lightning_frames()
    if condition in ("windy", "windy-variant"):
        return windy_frames()
    return pulsing_frames((0, 45, 22), (0, 190, 85))


def build_weather_choreographies(condition: str) -> Tuple[str, str]:
    frames = weather_frames_for_condition(condition)
    ear_frames = {
        0: (10, 10),
        80: (4, 12),
        150: (12, 4),
        220: (10, 10),
        300: (6, 14),
    }
    end_frames = [
        frame_from_color(blend_color((40, 40, 40), (0, 0, 0), step / 12.0))
        for step in range(1, 13)
    ]
    return (
        weather_choreography_data_uri(
            frames,
            frame_duration=8,
            start_ears=(10, 10),
            ear_frames=ear_frames,
        ),
        weather_choreography_data_uri(
            end_frames,
            frame_duration=5,
            end_ears=(0, 0),
        ),
    )


def all_leds_off_choreography_data_uri() -> str:
    data = bytearray([0, 1, 1])  # one wait unit is 10ms
    for led_index in (0, 1, 2, 3, 4):
        data.extend([0, 7, led_index, 0, 0, 0, 0, 0])
    return (
        "data:application/x-nabaztag-mtl-choreography;base64,"
        + b64encode(bytes(data)).decode("ascii")
    )


def build_led_reset_packet() -> Dict[str, Any]:
    return {
        "type": "command",
        "sequence": [{"choreography": all_leds_off_choreography_data_uri()}],
        "cancelable": False,
    }


def reset_leds() -> Dict[str, Any]:
    clear_all = send_to_nabd(
        {"type": "info", "info_id": "habridge_reset", "clear_all": True}
    )
    cleared = []
    for info_id in RESET_INFO_IDS:
        cleared.append(
            {
                "info_id": info_id,
                "nabd": send_to_nabd({"type": "info", "info_id": info_id}),
            }
        )
    return {
        "status": "ok",
        "clear_all": clear_all,
        "cleared_info_ids": cleared,
        "reset": send_to_nabd(build_led_reset_packet()),
    }


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

        if path == "/leds/reset":
            return reset_leds()

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

        if path == "/quiet":
            return set_quiet_mode(validate_bool(body.get("enabled"), "enabled"))

        if path == "/quiet/on":
            return set_quiet_mode(True)

        if path == "/quiet/off":
            return set_quiet_mode(False)

        if path == "/wyoming/restart":
            return restart_wyoming()

        if path == "/audio/url":
            packet = build_audio_packet(body.get("url"), bool(body.get("cancelable", False)))
            return send_to_nabd(packet)

        if path == "/tts/ha":
            return play_ha_tts(body)

        if path == "/weather/say":
            tts_body = dict(body)
            tts_body["message"] = build_weather_message(body)
            condition = body.get("condition", "unknown")
            if not isinstance(condition, str):
                condition = "unknown"
            if "tts_language" in tts_body:
                tts_body["language"] = tts_body.pop("tts_language")
            else:
                tts_body.pop("language", None)
            tts_body.pop("message_language", None)
            audio_url = get_ha_tts_url(tts_body)
            active_chor, end_chor = build_weather_choreographies(condition)
            packet = build_audio_choreography_packet(audio_url, active_chor, end_chor)
            result = send_to_nabd(packet)
            result["audio_url"] = audio_url
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
