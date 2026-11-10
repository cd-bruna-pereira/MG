"""
Simulador de leitura de sensores.

Gera valores plausíveis (passeio aleatório) usando a MESMA interface pública
do ArduinoHandler real: is_connected(), read_sensor_data(), get_dataframe_format(),
open_valve()/close_valve() e arduino.disconnect(). Assim, o app.py não precisa
saber se está falando com o hardware real ou com este simulador.

Para usar dados reais: em app.py, troque MODO_SIMULACAO para False.
Quando não precisar mais simular, este arquivo pode simplesmente ser apagado.
"""
import random
from datetime import datetime


class ConexaoSimulada:
    """Substitui ArduinoConnection só para manter a chamada `.arduino.disconnect()`."""

    def disconnect(self):
        pass


class HandlerSimulado:
    """Substitui ArduinoHandler, devolvendo dados sintéticos no mesmo formato esperado."""

    def __init__(self):
        self.arduino = ConexaoSimulada()
        # valores iniciais usados como base do passeio aleatório
        self._o2_raw = 620.0
        self._h2_raw = 280.0
        self._temp = 26.0
        self._umid = 48.0
        self._pressao = 101.3

    def is_connected(self):
        return True

    def read_sensor_data(self):
        # pequena variação a cada leitura, para imitar ruído/processo real
        self._o2_raw = min(1023, max(0, self._o2_raw + random.uniform(-6, 6)))
        self._h2_raw = min(1023, max(0, self._h2_raw + random.uniform(-6, 6)))
        self._temp += random.uniform(-0.15, 0.15)
        self._umid = min(100, max(0, self._umid + random.uniform(-0.4, 0.4)))
        self._pressao += random.uniform(-0.04, 0.04)
        return {
            "o2_raw": self._o2_raw,
            "h2_raw": self._h2_raw,
            "temp": self._temp,
            "umid": self._umid,
            "pressao": self._pressao,
        }

    def get_dataframe_format(self, dado_bruto):
        # formato final esperado pelo app — deve espelhar o retorno do
        # ArduinoHandler real (ajustar nomes das chaves se forem diferentes lá)
        return {
            "Timestamp": datetime.now(),
            "O2_Raw": dado_bruto["o2_raw"],
            "H2_Raw": dado_bruto["h2_raw"],
            "Ambient_Temp": dado_bruto["temp"],
            "Ambient_Hum": dado_bruto["umid"],
            "Ambient_Pressure": dado_bruto["pressao"],
        }

    def open_valve(self, gas):
        pass  # não existe válvula física no modo simulado

    def close_valve(self, gas):
        pass
