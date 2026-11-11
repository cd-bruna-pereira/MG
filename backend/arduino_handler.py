"""Leitura e normalização dos dados enviados pelo Arduino."""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from .arduino_connection import ArduinoConnection


class ArduinoHandler:
    def __init__(self, arduino: ArduinoConnection):
        self.arduino = arduino
        self._latest_ambient: Dict[str, float] = {}

    def is_connected(self) -> bool:
        return self.arduino.is_open()

    def read_sensor_data(self) -> Optional[Dict[str, Any]]:
        for _ in range(20):
            line = self.arduino.read_line()
            if not line:
                return None
            parsed = self._parse_sensor_line(line)
            if parsed is None:
                continue
            if parsed.pop("_ambient_only", False):
                self._latest_ambient.update(parsed)
                continue
            return {**self._latest_ambient, **parsed}
        return None

    def get_dataframe_format(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "Timestamp": datetime.now(),
            "H2_Raw": self._extract_float(data, "H2_Raw", "h2_raw", "h2", "H2", "mq8"),
            "Ambient_Temp": self._extract_float(data, "Ambient_Temp", "temp", "temperature", "temp_c"),
            "Ambient_Hum": self._extract_float(data, "Ambient_Hum", "umid", "humidity", "hum"),
            "Ambient_Pressure": self._extract_float(data, "Ambient_Pressure", "pressao", "pressure", "press"),
        }

    def _parse_sensor_line(self, line: str) -> Optional[Dict[str, Any]]:
        payload = line.split("->", 1)[-1].strip()
        mq8_match = re.search(
            r"Medida\s+MQ8:\s*([+-]?\d+(?:[.,]\d+)?)",
            payload,
            re.IGNORECASE,
        )
        if mq8_match:
            value = float(mq8_match.group(1).replace(",", "."))
            return {"mq8": value, "H2_Raw": value}

        if payload.startswith("{") and payload.endswith("}"):
            try:
                value = json.loads(payload)
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None

        ambient = re.findall(r"(?:Temperature|Humidity|Bar)\s*=\s*([+-]?\d+(?:[.,]\d+)?)", payload, re.I)
        if len(ambient) == 3:
            values = [float(item.replace(",", ".")) for item in ambient]
            return {"Ambient_Temp": values[0], "Ambient_Hum": values[1], "Ambient_Pressure": values[2], "_ambient_only": True}

        normalized = payload.replace(";", ",").replace("|", ",")
        if "=" in normalized or ":" in normalized:
            result: Dict[str, Any] = {}
            for item in normalized.split(","):
                if "=" in item:
                    separator = "="
                elif ":" in item:
                    separator = ":"
                else:
                    continue
                key, value = item.split(separator, 1)
                try:
                    result[key.strip()] = float(value.strip().replace(",", "."))
                except ValueError:
                    continue
            return result or None

        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) < 5:
            return None
        try:
            values = [float(part) for part in parts[:5]]
        except ValueError:
            return None
        return {"o2_raw": values[0], "h2_raw": values[1], "temp": values[2], "umid": values[3], "pressao": values[4]}

    @staticmethod
    def _extract_float(data: Dict[str, Any], *keys: str) -> float:
        for key in keys:
            try:
                return float(data[key])
            except (KeyError, TypeError, ValueError):
                continue
        return float("nan")
