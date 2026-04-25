import abc
import logging
import requests
import asyncio
from typing import Optional, Dict, Any

class WeatherProvider(abc.ABC):
    @abc.abstractmethod
    async def get_forecast(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Return forecast data normalized for NabWeatherd"""
        pass

class OpenMeteoProvider(WeatherProvider):
    # Free, no-key, global, asyncio-friendly (via run_in_executor)
    URL = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 2
        }
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.get(self.URL, params=params, timeout=10))
            
            if resp.status_code != 200:
                logging.error(f"OpenMeteo error: {resp.status_code}")
                return None
            
            data = resp.json()
            
            # Map WMO codes to Nabaztag weather classes
            today_code = data["daily"]["weather_code"][0]
            tomorrow_code = data["daily"]["weather_code"][1]
            
            return {
                "today": {
                    "class": self._map_code(today_code),
                    "temp": int(data["daily"]["temperature_2m_max"][0]),
                    "rain": data["daily"]["precipitation_probability_max"][0] > 30
                },
                "tomorrow": {
                    "class": self._map_code(tomorrow_code),
                    "temp": int(data["daily"]["temperature_2m_max"][1]),
                    "rain": data["daily"]["precipitation_probability_max"][1] > 30
                }
            }
        except Exception as e:
            logging.error(f"OpenMeteo exception: {e}")
            return None

    def _map_code(self, code: int) -> str:
        # Map codes to existing audio files in sounds/nabweatherd/sky/
        if code == 0: return "sunny"
        if code in [1, 2, 3]: return "cloudy"
        if code in [45, 48]: return "foggy"
        if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "rainy"
        if code in [71, 73, 75, 77, 85, 86]: return "snowy"
        if code in [95, 96, 99]: return "stormy"
        return "cloudy"
