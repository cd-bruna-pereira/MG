"""Conversão das leituras brutas do sensor em ppm."""

TOTAL_PPM = 1_000_000.0
H2_SLOPE = -21_338.26
H2_INTERCEPT = 79_095.03


def calcular_concentracao_h2(leitura_bruta: float) -> float:
    return max(0.0, H2_SLOPE * float(leitura_bruta) + H2_INTERCEPT)


def calcular_concentracao_o2(concentracao_h2: float) -> float:
    return max(0.0, TOTAL_PPM - float(concentracao_h2))
