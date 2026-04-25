import datetime
import logging
import random
import sys
import json
from enum import Enum
from typing import Optional, Dict, Any, Tuple

from asgiref.sync import sync_to_async
from dateutil import tz

from nabcommon.nabservice import NabInfoCachedService
from nabcommon.typing import NabdPacket, Animation

from . import rfid_data, providers


class NabWeatherd(NabInfoCachedService):
    class Reason(Enum):
        BOOT = 1
        CONFIG_RELOADED = 2
        PERFORMANCE_PLAYED = 3

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

    async def get_config(self) -> Tuple[datetime.datetime, Any, Any]:
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

    async def update_next(self, next_date: datetime.datetime, next_args: Any) -> None:
        from . import models
        config = await models.Config.load_async()
        config.next_performance_date = next_date
        config.next_performance_type = next_args

        if config.weather_frequency > 0 and not config.next_performance_weather_vocal_flag:
            now = datetime.datetime.now(datetime.timezone.utc)
            minutes = random.randint(40, 70) if config.weather_frequency == 1 else random.randint(100, 190) if config.weather_frequency == 2 else None
            if minutes:
                config.next_performance_weather_vocal_date = now + datetime.timedelta(minutes=minutes)
                config.next_performance_weather_vocal_flag = 1
        
        await config.save_async()

    async def reload_config(self):
        """
        Reload configuration on USR1 signal from web interface.
        """
        logging.info("NabWeatherd: reloading configuration")
        async with self.loop_cv:
            self.reason = self.Reason.CONFIG_RELOADED
            self.loop_cv.notify()

    def compute_next(self, saved_date: datetime.datetime, saved_args: Any, config: Any, reason: Reason) -> Optional[Tuple[datetime.datetime, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        if saved_date is not None and saved_date < now + datetime.timedelta(minutes=10):
            return saved_date, saved_args
        if reason in [self.Reason.BOOT, self.Reason.CONFIG_RELOADED]:
            return now, "info"
        next_date = self.next_info_update(config)
        return next_date, "info"

    async def fetch_info_data(self, config_t) -> Optional[Dict[str, Any]]:
        location = config_t[0]
        if not location or not isinstance(location, dict) or "lat" not in location:
            return None
        forecast = await self.provider.get_forecast(location["lat"], location["lon"])
        if not forecast: return None
        return {
            "weather_animation_type": config_t[2],
            "today": forecast["today"],
            "tomorrow": forecast["tomorrow"]
        }

    def get_animation(self, info_data) -> Optional[str]:
        if not info_data: return None
        anim_type = info_data["weather_animation_type"]
        if anim_type in ["weather_and_rain", "rain_only"]:
            packet = {"type": "info", "info_id": "nabweatherd_rain"}
            if info_data["today"]["rain"]: packet["animation"] = self.RAIN_ANIMATION
            self.write_packet(packet)
        if anim_type in ["weather_and_rain", "weather_only"]:
            if anim_type == "weather_only": self.write_packet({"type": "info", "info_id": "nabweatherd_rain"})
            weather_class = info_data["today"]["class"]
            anim = self.ANIMATIONS.get(weather_class)
            return json.dumps(anim) if anim else None
        if anim_type == "nothing": self.write_packet({"type": "info", "info_id": "nabweatherd_rain"})
        return None

    def write_packet(self, packet: Dict[str, Any]):
        if self.writer:
            self.writer.write((json.dumps(packet) + "\r\n").encode("utf8"))

    async def perform_additional(self, expiration, type, info_data, config_t):
        if not info_data or type not in info_data: return
        unit = config_t[1]
        forecast = info_data[type]
        weather_class = forecast["class"]
        temp = forecast["temp"]
        unit_sound = "degree.mp3"
        if unit == self.UNIT_FAHRENHEIT:
            temp = round(temp * 1.8 + 32.0)
            unit_sound = "degree_f.mp3"
        
        # Audio files for temperatures are in sounds/nabweatherd/temp/
        # They only go up to 50 for Celsius, but Fahrenheit needs them too.
        # Ensure we stay within bounds of available audio files if possible
        body_audio = [f"nabweatherd/{type}.mp3", f"nabweatherd/sky/{weather_class}.mp3", f"nabweatherd/temp/{temp}.mp3", f"nabweatherd/{unit_sound}"]
        packet = {
            "type": "message",
            "signature": {"audio": ["nabweatherd/signature.mp3"]},
            "body": [{"audio": body_audio}],
            "expiration": expiration.isoformat()
        }
        self.write_packet(packet)
        await self.writer.drain()

    async def perform(self, expiration, args, config):
        # Base perform handles fetching info and setting animation
        await super().perform(expiration, args, config)
        
        vocal_date, vocal_flag, freq = config[4], config[5], config[3]
        current_tz = self.get_system_tz()
        now = datetime.datetime.now(tz=tz.gettz(current_tz))

        # Random vocal check
        if vocal_flag and vocal_date and vocal_date < now:
            target = "tomorrow" if now.hour > 18 else "today"
            info_data = await self._do_fetch_info_data(config)
            await self.perform_additional(expiration, target, info_data, config)
            from . import models
            config_m = await models.Config.load_async()
            config_m.next_performance_weather_vocal_flag = 0
            await config_m.save_async()

        # Bedtime/Wakeup check (Frequency 3 means "at bedtime/wakeup")
        if freq == 3:
            from nabclockd import models as clock_models
            clock = await clock_models.Config.load_async()
            
            # Construct naive datetimes for today's events
            bedtime = now.replace(hour=clock.sleep_hour, minute=clock.sleep_min, second=0, microsecond=0)
            wakeup = now.replace(hour=clock.wakeup_hour, minute=clock.wakeup_min, second=0, microsecond=0)
            
            # Check if we just passed wakeup time (within 5 min window)
            if wakeup < now < wakeup + datetime.timedelta(minutes=5):
                if not self.weather_wakeup_done:
                    info_data = await self._do_fetch_info_data(config)
                    await self.perform_additional(expiration, "today", info_data, config)
                    self.weather_wakeup_done = True
            else:
                self.weather_wakeup_done = False

            # Check if we are approaching bedtime (within 5 min window)
            if bedtime - datetime.timedelta(minutes=5) < now < bedtime:
                if not self.weather_bedtime_done:
                    info_data = await self._do_fetch_info_data(config)
                    await self.perform_additional(expiration, "tomorrow", info_data, config)
                    self.weather_bedtime_done = True
            else:
                self.weather_bedtime_done = False

    def get_system_tz(self):
        try:
            with open("/etc/timezone") as f: return f.read().strip()
        except: return "UTC"

    async def process_nabd_packet(self, packet: NabdPacket):
        if packet["type"] == "asr_event" and packet["nlu"]["intent"] == "nabweatherd/forecast":
            target = "tomorrow" if "date" in packet["nlu"] and packet["nlu"]["date"][:10] != datetime.datetime.now().strftime("%Y-%m-%d") else "today"
            await self._trigger_vocal(target)
        elif packet["type"] == "rfid_event" and packet["app"] == "nabweatherd" and packet["event"] == "detected":
            target = rfid_data.unserialize(packet["data"].encode("utf8")) if "data" in packet else "today"
            await self._trigger_vocal(target)

    async def _trigger_vocal(self, type):
        from . import models
        config_m = await models.Config.load_async()
        config_t = (config_m.location, config_m.unit, config_m.weather_animation_type, config_m.weather_frequency, config_m.next_performance_weather_vocal_date, config_m.next_performance_weather_vocal_flag)
        info_data = await self._do_fetch_info_data(config_t)
        now = datetime.datetime.now(datetime.timezone.utc)
        await self.perform_additional(now + datetime.timedelta(minutes=2), type, info_data, config_t)

if __name__ == "__main__":
    NabWeatherd.main(sys.argv[1:])
