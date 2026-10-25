"""Weather from Open-Meteo: free, no key, works for Chinese city names."""

from __future__ import annotations

import httpx

from anima.skills.base import SkillContext, skill

WMO = {
    0: "晴", 1: "大致晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "冻毛毛雨", 57: "冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒", 80: "阵雨", 81: "阵雨", 82: "暴雨",
    85: "阵雪", 86: "大阵雪", 95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}


@skill(
    "weather",
    "查某个城市现在的天气和未来三天预报。",
    {"city": {"type": "string", "description": "城市名，比如 上海、成都、Tokyo"}},
    required=["city"],
)
async def weather(ctx: SkillContext, args: dict) -> dict:
    city = args["city"].strip()
    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        places = geo.json().get("results") or []
        if not places:
            return {"error": f"没找到叫{city}的地方"}
        place = places[0]
        forecast = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
        data = forecast.json()
    cur, daily = data.get("current", {}), data.get("daily", {})
    days = []
    for i, date in enumerate(daily.get("time", [])):
        days.append({
            "date": date,
            "weather": WMO.get(daily["weather_code"][i], "未知"),
            "low": daily["temperature_2m_min"][i],
            "high": daily["temperature_2m_max"][i],
            "rain_chance": daily["precipitation_probability_max"][i],
        })
    return {
        "place": f"{place.get('name')}（{place.get('admin1', '')}{', ' + place['country'] if place.get('country') else ''}）",
        "now": {
            "weather": WMO.get(cur.get("weather_code"), "未知"),
            "temp": cur.get("temperature_2m"),
            "feels_like": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind_kmh": cur.get("wind_speed_10m"),
        },
        "next_days": days,
    }
