# Monitor do Misturador de Gás

## Como rodar
```
streamlit run app.py
```

## Senha de acesso
Senha padrão: **H2O2#2026**

Para trocar, gere um novo hash e cole em `autenticacao.py` (constante `HASH_SENHA_VALIDA`):
```
python -c "import hashlib; print(hashlib.sha256(b'NOVA_SENHA').hexdigest())"
```

## Estrutura dos arquivos
- **app.py** — tela principal (login, válvulas, métricas, gráficos, histórico).
- **autenticacao.py** — controla o login por senha.
- **calculo_concentracao.py** — equação de calibração `y = a*x + b` para O2 e H2. É o único lugar que precisa ser editado quando a calibração real dos sensores estiver pronta.
- **simulador.py** — gera dados falsos (passeio aleatório) com a mesma interface do `ArduinoHandler` real, só para visualizar a tela funcionando sem hardware conectado.
- **arduino_connection.py** / **arduino_handler.py** — seus arquivos já existentes, usados apenas quando `MODO_SIMULACAO = False`.

## Saindo do modo de simulação
Em `app.py`, troque:
```python
MODO_SIMULACAO = True
```
para
```python
MODO_SIMULACAO = False
```
Quando não precisar mais do simulador, o arquivo `simulador.py` pode ser apagado.

## Atenção
- O cálculo de O2/H2 espera que `ArduinoHandler.get_dataframe_format()` devolva as chaves `O2_Raw`, `H2_Raw`, `Ambient_Temp`, `Ambient_Hum` e `Ambient_Pressure` (essa última é nova — confirme se o seu sensor de pressão já está sendo lido e formatado lá). Ajuste os nomes em `app.py`/`simulador.py` caso seu handler real use nomes diferentes.
- As cores e nomes das válvulas estão no dicionário `GASES` em `app.py`.
