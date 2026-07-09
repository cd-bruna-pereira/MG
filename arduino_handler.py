"""Interface de alto nível para o Arduino.

Este módulo encapsula a conexão serial e expõe a mesma API usada pela UI e
pelo simulador: ``is_connected()``, ``read_sensor_data()``,
``get_dataframe_format()``, ``open_valve()`` e ``close_valve()``.

A leitura aceita formatos comuns de firmware:
- JSON com chaves como ``o2_raw`` e ``temp``.
- Linha CSV com 5 valores na ordem O2, H2, temperatura, umidade e pressão.
- Pares ``chave=valor`` separados por vírgula, ponto e vírgula ou barra.

Os comandos de válvula usam strings simples e fáceis de ajustar para o
firmware do Arduino. Se o sketch usar outro protocolo, basta alterar os
valores em ``VALVE_COMMANDS``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from arduino_connection import ArduinoConnection


VALVE_COMMANDS = {
    "O2": {"open": "O2_OPEN", "close": "O2_CLOSE"},
    "H2": {"open": "H2_OPEN", "close": "H2_CLOSE"},
}


class ArduinoHandler:
    """Faixa de compatibilidade entre a serial e o app Streamlit."""

    def __init__(self, arduino: ArduinoConnection):
        self.arduino = arduino
        self._latest_ambient: Dict[str, float] = {}

    def is_connected(self) -> bool:
        return self.arduino.is_open()

    def read_sensor_data(self) -> Optional[Dict[str, Any]]:
        if not self.is_connected():
            return None

        line = self.arduino.read_line()
        if not line:
            return None

        parsed = self._parse_sensor_line(line)
        if parsed is None:
            return None

        if parsed.pop("_ambient_only", False):
            self._latest_ambient.update(parsed)
            return None

        if self._latest_ambient:
            parsed = {**self._latest_ambient, **parsed}

        return parsed

    def get_dataframe_format(self, dado_bruto: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "Timestamp": datetime.now(),
            "O2_Raw": self._extract_float(dado_bruto, "O2_Raw", "o2_raw", "o2", "O2"),
            "H2_Raw": self._extract_float(dado_bruto, "H2_Raw", "h2_raw", "h2", "H2"),
            "Ambient_Temp": self._extract_float(dado_bruto, "Ambient_Temp", "temp", "temperature", "temp_c"),
            "Ambient_Hum": self._extract_float(dado_bruto, "Ambient_Hum", "umid", "humidity", "hum"),
            "Ambient_Pressure": self._extract_float(dado_bruto, "Ambient_Pressure", "pressao", "pressure", "press"),
        }

    def open_valve(self, gas: str) -> bool:
        return self._send_valve_command(gas, "open")

    def close_valve(self, gas: str) -> bool:
        return self._send_valve_command(gas, "close")

    def disconnect(self) -> None:
        self.arduino.disconnect()

    def _send_valve_command(self, gas: str, action: str) -> bool:
        command_set = VALVE_COMMANDS.get(gas.upper())
        if not command_set:
            return False
        return self.arduino.write_command(command_set[action])

    def _parse_sensor_line(self, line: str) -> Optional[Dict[str, Any]]:
        raw_line = self._strip_serial_prefix(line)
        if not raw_line:
            return None

        mq_payload = self._try_parse_mq_line(raw_line)
        if mq_payload is not None:
            return mq_payload

        ambient_payload = self._try_parse_ambient_line(raw_line)
        if ambient_payload is not None:
            return ambient_payload

        json_payload = self._try_parse_json(raw_line)
        if json_payload is not None:
            return json_payload

        kv_payload = self._try_parse_key_value_line(raw_line)
        if kv_payload is not None:
            return kv_payload

        csv_payload = self._try_parse_csv_line(raw_line)
        if csv_payload is not None:
            return csv_payload

        return None

    def _strip_serial_prefix(self, line: str) -> str:
        stripped = line.strip()
        if "->" not in stripped:
            return stripped

        _, payload = stripped.split("->", 1)
        return payload.strip()

    def _try_parse_mq_line(self, line: str) -> Optional[Dict[str, Any]]:
        match = re.search(r"Medida\s+MQ8:\s*([+-]?\d+(?:[\.,]\d+)?)", line, flags=re.IGNORECASE)
        if not match:
            return None

        mq8_value = self._coerce_number(match.group(1))
        if mq8_value is None:
            return None

        # MQ8 alimenta o canal de H2 neste projeto.
        return {
            "mq8": mq8_value,
            "H2_Raw": mq8_value,
        }

    def _try_parse_ambient_line(self, line: str) -> Optional[Dict[str, Any]]:
        temp_match = re.search(r"Temperature\s*=\s*([+-]?\d+(?:[\.,]\d+)?)", line, flags=re.IGNORECASE)
        hum_match = re.search(r"Humidity\s*=\s*([+-]?\d+(?:[\.,]\d+)?)", line, flags=re.IGNORECASE)
        bar_match = re.search(r"Bar\s*=\s*([+-]?\d+(?:[\.,]\d+)?)", line, flags=re.IGNORECASE)

        if not (temp_match and hum_match and bar_match):
            return None

        temp_value = self._coerce_number(temp_match.group(1))
        hum_value = self._coerce_number(hum_match.group(1))
        bar_value = self._coerce_number(bar_match.group(1))

        if temp_value is None or hum_value is None or bar_value is None:
            return None

        return {
            "Ambient_Temp": temp_value,
            "Ambient_Hum": hum_value,
            "Ambient_Pressure": bar_value,
            "temp": temp_value,
            "humidity": hum_value,
            "pressure": bar_value,
            "_ambient_only": True,
        }

    def _try_parse_json(self, line: str) -> Optional[Dict[str, Any]]:
        if not (line.startswith("{") and line.endswith("}")):
            return None

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None

        if isinstance(payload, dict):
            return payload
        return None

    def _try_parse_key_value_line(self, line: str) -> Optional[Dict[str, Any]]:
        normalized = line.replace(";", ",").replace("|", ",")
        if "=" not in normalized and ":" not in normalized:
            return None

        parsed: Dict[str, Any] = {}
        for chunk in normalized.split(","):
            if not chunk.strip():
                continue
            separator = "=" if "=" in chunk else ":" if ":" in chunk else None
            if not separator:
                continue
            key, value = chunk.split(separator, 1)
            parsed[key.strip()] = self._coerce_number(value.strip())

        return parsed or None

    def _try_parse_csv_line(self, line: str) -> Optional[Dict[str, Any]]:
        normalized = line.replace(";", ",").replace("|", ",")
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) < 5:
            return None

        values = [self._coerce_number(part) for part in parts[:5]]
        if any(value is None for value in values):
            return None

        return {
            "o2_raw": values[0],
            "h2_raw": values[1],
            "temp": values[2],
            "umid": values[3],
            "pressao": values[4],
        }

    def _extract_float(self, data: Dict[str, Any], *keys: str) -> float:
        for key in keys:
            if key in data:
                value = self._coerce_number(data[key])
                if value is not None:
                    return float(value)

        if "H2_Raw" in keys:
            value = self._coerce_number(data.get("mq8"))
            if value is not None:
                return float(value)

        return float("nan")

    def _coerce_number(self, value: Any) -> Optional[float]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return None

        text = str(value).strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None