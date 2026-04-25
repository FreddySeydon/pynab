import datetime
import logging
import random
import sys
import json
from typing import Optional, Dict, Any

from asgiref.sync import sync_to_async
from dateutil import tz

from nabcommon.nabservice import NabInfoService
from nabcommon.typing import NabdPacket, Animation

from . import rfid_data, providers


class NabWeatherd(NabInfoService):
    UNIT_CELSIUS = 1
    UNIT_FAHRENHEIT = 2

    ANIMATIONS = {
        "sunny": {"tempo": 25, "colors": [{"left": "ffff00", "center": "ffff00", "right": "ffff00"}] * 5 + [{"left": "000000", "center": "000000", "right": "000000"}] * 3},
        "cloudy": {"tempo": 125, "colors": [{"left": "000000", "center": "ffff00", "right": "000000"}, {"left": "0000ff", "center": "000000", "right": "0000ff"}]},
        "rainy": {"tempo": 20, "colors": [{"left": "000000", "center": "000000", "right": "000000"}, {"left": "000000", "center": "0000ff", "right": "000000"}, {"left": "0000ff", "center": "000000", "right": "0000ff"}]},
        "snowy": {"tempo": 40, "colors": [{"left": "0000ff", "center": "000000", "right": "000000"}, {"left": "000000", "center": "000000", "right": "0000ff"}]},
        "foggy": {"tempo": 25, "colors": [{"left": "0000ff", "center": "0000ff", "right": "0000ff"}] * 5 + [{"left": "000000", "center": "000000", "right": "000000"}]},
        "stormy": {"tempo": 25, "colors": [{"left": "000000", "center": "0000ff", "right": "ffff00"}, {"left": "000000", "center": "000000", "right": "000000"}]},
    }

    RAIN_ANIMATION = {"tempo": 16, "colors": [{"left": "000000", "center": "003399", "right": "000000"}, {"left": "003399", "center": "000000", "right": "003399"}]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider = providers.OpenMeteoProvider()
        self.weather_bedtime_done = False
        self.weather_wakeup_done = False

    async def fetch_info_data(self, config_t) -> Optional[Dict[str, Any]]:
        location = config_t[0]
        if not location or "lat" not in location:
            return None

        # Fetch from provider
        forecast = await self.provider.get_forecast(location["lat"], location["lon"])
        if not forecast:
            return None

        return {
            "weather_animation_type": config_t[2],
            "today": forecast["today"],
            "tomorrow": forecast["tomorrow"]
        }

    def get_animation(self, info_data) -> Optional[Dict[str, Any]]:
        if not info_data:
            return None

        anim_type = info_data["weather_animation_type"]
        
        # Handle Rain info separately (info_id: nabweatherd_rain)
        if anim_type in ["weather_and_rain", "rain_only"]:
            rain_packet = {"type": "info", "info_id": "nabweatherd_rain"}
            if info_data["today"]["rain"]:
                rain_packet["animation"] = self.RAIN_ANIMATION
            self.write_packet(rain_packet)

        # Main weather animation
        if anim_type in ["weather_and_rain", "weather_only"]:
            if anim_type == "weather_only":
                self.write_packet({"type": "info", "info_id": "nabweatherd_rain"}) # Remove rain
            
            weather_class = info_data["today"]["class"]
            return self.ANIMATIONS.get(weather_class)

        if anim_type == "nothing":
            self.write_packet({"type": "info", "info_id": "nabweatherd_rain"})
            return None
        
        return None

    async def perform_additional(self, expiration, type, info_data, config_t):
        if not info_data:
            logging.error("Weather data unavailable for vocal performance")
            return

        unit = config_t[1]
        forecast = info_data[type]
        weather_class = forecast["class"]
        temp = forecast["temp"]

        unit_sound = "degree.mp3"
        if unit == self.UNIT_FAHRENHEIT:
            temp = round(temp * 1.8 + 32.0)
            unit_sound = "degree_f.mp3"

        # Construct the message sequence
        body_audio = [
            f"nabweatherd/{type}.mp3",
            f"nabweatherd/sky/{weather_class}.mp3",
            f"nabweatherd/temp/{temp}.mp3",
            f"nabweatherd/{unit_sound}"
        ]

        await self.send_message(
            signature_audio=["nabweatherd/signature.mp3"],
            body_audio=body_audio,
            expiration=expiration
        )

    async def send_message(self, signature_audio, body_audio, expiration):
        packet = {
            "type": "message",
            "signature": {"audio": signature_audio},
            "body": [{"audio": body_audio}],
            "expiration": expiration.isoformat()
        }
        self.write_packet(packet)
        await self.writer.drain()

    async def perform(self, expiration, args, config):
        await super().perform(expiration, args, config)
        
        # Check if we need to perform random vocal forecast
        next_vocal_date = config[4]
        next_vocal_flag = config[5]
        
        current_tz = self.get_system_tz()
        now = datetime.datetime.now(tz=tz.gettz(current_tz))

        if next_vocal_flag and next_vocal_date and next_vocal_date < now:
            forecast_type = "tomorrow" if now.hour > 18 else "today"
            await self._do_perform_additional(config, forecast_type)
            
            # Reset flag
            from . import models
            config_m = await models.Config.load_async()
            config_m.next_performance_weather_vocal_flag = 0
            await config_m.save_async()

    def get_system_tz(self):
        try:
            with open("/etc/timezone") as f:
                return f.read().strip()
        except:
            return "UTC"

    async def _do_perform_additional(self, config, type):
        info_data = await self.fetch_info_data(config)
        now = datetime.datetime.now(datetime.timezone.utc)
        expiration = now + datetime.timedelta(minutes=2)
        await self.perform_additional(expiration, type, info_data, config)

    async def process_nabd_packet(self, packet: NabdPacket):
        if packet["type"] == "asr_event" and packet["nlu"]["intent"] == "nabweatherd/forecast":
            # Logic for today vs tomorrow based on NLU date if available
            target = "today"
            if "date" in packet["nlu"]:
                if packet["nlu"]["date"][:10] != datetime.datetime.now().strftime("%Y-%m-%d"):
                    target = "tomorrow"
            await self._trigger_vocal(target)

        elif packet["type"] == "rfid_event" and packet["app"] == "nabweatherd" and packet["event"] == "detected":
            target = rfid_data.unserialize(packet["data"].encode("utf8")) if "data" in packet else "today"
            await self._trigger_vocal(target)

    async def _trigger_vocal(self, type):
        from . import models
        config_m = await models.Config.load_async()
        # Pack config exactly as perform/fetch_info_data expects it
        config_t = (
            config_m.location,
            config_m.unit,
            config_m.weather_animation_type,
            config_m.weather_frequency,
            config_m.next_performance_weather_vocal_date,
            config_m.next_performance_weather_vocal_flag,
        )
        await self._do_perform_additional(config_t, type)

    async def get_config(self):
        from . import models
        config = await models.Config.load_async()
        return (
            config.next_performance_date,
            config.next_performance_type,
            (
                config.location,
                config.unit,
                config.weather_animation_type,
                config.weather_frequency,
                config.next_performance_weather_vocal_date,
                config.next_performance_weather_vocal_flag,
            ),
        )

if __name__ == "__main__":
    NabWeatherd.main(sys.argv[1:])
