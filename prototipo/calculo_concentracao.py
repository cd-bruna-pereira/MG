"""
Cálculo da concentração de O2 e H2 a partir da leitura bruta dos sensores.
As concentrações são retornadas em ppm.
"""

COEF_H2 = {"a": -21338.26, "b": 79095.03}
TOTAL_PPM = 1_000_000.0


def calcular_concentracao_o2(concentracao_h2_ppm: float) -> float:
    """Calcula a concentração de O2 em ppm a partir da concentração de H2."""
    return max(0.0, TOTAL_PPM - float(concentracao_h2_ppm))


def calcular_concentracao_h2(leitura_bruta: float) -> float:
    """Converte a leitura bruta do sensor de H2 em concentração ppm."""
    return max(0.0, COEF_H2["a"] * float(leitura_bruta) + COEF_H2["b"])
