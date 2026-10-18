"""Pruebas exhaustivas de fechas y reglas meteorológicas.

Ejecutar con el Python de HDT4:
  python probar_todos_casos.py
  python probar_todos_casos.py --live
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from shared.parachute import MAX_FORECAST_DAYS, WeatherReport, evaluate_weather, validate_date, weather_tool


def make_report(**changes) -> WeatherReport:
    values = dict(
        date="2099-01-01",
        temperature_c=27.0,
        precipitation_mm=0.0,
        cloud_cover_pct=10.0,
        visibility_m=10000.0,
        wind_speed_kmh=10.0,
        wind_gust_kmh=20.0,
        decision="",
        reasons=[],
    )
    values.update(changes)
    return WeatherReport(**values)


def test_weather_rules() -> None:
    cases = {
        "IDEAL": make_report(),
        "MARGINAL: viento 20": make_report(wind_speed_kmh=20),
        "MARGINAL: viento 28": make_report(wind_speed_kmh=28),
        "MARGINAL: nubes 30": make_report(cloud_cover_pct=30),
        "MARGINAL: nubes 75": make_report(cloud_cover_pct=75),
        "INSEGURO: viento >28": make_report(wind_speed_kmh=28.01),
        "INSEGURO: ráfagas >35": make_report(wind_gust_kmh=35.01),
        "INSEGURO: precipitación >0": make_report(precipitation_mm=0.01),
        "INSEGURO: nubes >75": make_report(cloud_cover_pct=75.01),
        "INSEGURO: dato faltante": make_report(wind_speed_kmh=None),
    }
    print("\n=== REGLAS METEOROLÓGICAS ===")
    for name, report in cases.items():
        result = evaluate_weather(report)
        print(f"{name:<34} -> {result.decision}")


def test_dates() -> None:
    today = dt.date.today()
    cases = {
        "hoy": today.isoformat(),
        "mañana": (today + dt.timedelta(days=1)).isoformat(),
        "límite 16 días": (today + dt.timedelta(days=MAX_FORECAST_DAYS - 1)).isoformat(),
        "fuera de límite": (today + dt.timedelta(days=MAX_FORECAST_DAYS)).isoformat(),
        "fecha pasada": (today - dt.timedelta(days=1)).isoformat(),
        "formato inválido": "2026-99-99",
    }
    print("\n=== VALIDACIÓN DE FECHAS ===")
    for name, value in cases.items():
        try:
            accepted = validate_date(value, today)
            print(f"{name:<22} {value} -> ACEPTADA ({accepted})")
        except ValueError as exc:
            print(f"{name:<22} {value} -> RECHAZADA ({exc})")


def test_live_forecast() -> None:
    print("\n=== PRONÓSTICO REAL OPEN-METEO ===")
    today = dt.date.today()
    for offset in range(0, MAX_FORECAST_DAYS + 1):
        date = today + dt.timedelta(days=offset)
        result = json.loads(weather_tool(date.isoformat()))
        if "error" in result:
            print(f"{date}: ERROR -> {result['error']}")
        else:
            print(f"{date}: {result['decision']} | viento={result['wind_speed_kmh']} km/h | ráfagas={result['wind_gust_kmh']} km/h | lluvia={result['precipitation_mm']} mm | nubes={result['cloud_cover_pct']}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="consulta las 17 fechas reales disponibles")
    args = parser.parse_args()
    test_weather_rules()
    test_dates()
    if args.live:
        test_live_forecast()
