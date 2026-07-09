"""
Cálculo da concentração de O2 e H2 a partir da leitura bruta dos sensores.
Equação padrão linear (y = a*x + b)
"""

COEF_O2 = {"a": 0.1, "b": 0.0}
COEF_H2 = {"a":-21338.26, "b":79095.03}


def calcular_concentracao_o2(leitura_bruta: float) -> float:
    """Converte a leitura bruta do sensor de O2 em concentração (%)."""
    return COEF_O2["a"] * leitura_bruta + COEF_O2["b"]


def calcular_concentracao_h2(leitura_bruta: float) -> float:
    """Converte a leitura bruta do sensor de H2 em concentração (%)."""
    return COEF_H2["a"] * leitura_bruta + COEF_H2["b"]
