import time
from collections import deque
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from autenticacao import exigir_login
from calculo_concentracao import calcular_concentracao_h2, calcular_concentracao_o2

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Monitor do Misturador de Gás", page_icon="⚗️", layout="wide")

# --- ESTILO GLOBAL ---
st.markdown("""
<style>
    .stApp { background-color: #0a0f1c !important; }
    html, body, [class*="css"] { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
    h1, h2, h3, p, span, label, .stMarkdown, .stCaption { color: #e8edf5 !important; }
    .cartao {
        background-color: #131b2e; border: 1px solid #243047;
        border-radius: 14px; padding: 1.1rem 1.3rem; margin-bottom: 0.8rem;
    }
    .cartao-login {
        background-color: #131b2e; border: 1px solid #243047;
        border-radius: 16px; padding: 2rem 2rem 1.2rem 2rem; margin-top: 8vh;
    }
    div[data-testid="stMetric"] {
        background-color: #131b2e; border: 1px solid #243047;
        border-radius: 14px; padding: 0.9rem 1.1rem;
    }
    div[data-testid="stMetricLabel"] { color: #8b97ad !important; }
    .stButton>button {
        background-color: #1c2740 !important; color: #e8edf5 !important;
        border: 1px solid #2e3c59 !important; border-radius: 10px !important;
    }
    div[data-baseweb="select"]>div, input {
        background-color: #0a0f1c !important; color: #e8edf5 !important; border: 1px solid #243047 !important;
    }
    .texto-mono { font-family: 'Cascadia Code', 'Courier New', monospace; font-size: 12px; color: #8b97ad; }
</style>
""", unsafe_allow_html=True)

# --- LOGIN ---
exigir_login()

#   True  -> usa o simulador (simulador.py) para testar a tela sem hardware
#   False -> usa a conexão real com o Arduino
MODO_SIMULACAO = False

if MODO_SIMULACAO:
    from simulador import HandlerSimulado
else:
    from arduino_connection import ArduinoConnection
    from arduino_handler import ArduinoHandler

# --- GASES MONITORADOS ---
GASES = {
    "O2": {"nome": "Oxigênio", "cor": "#38bdf8"},
    "H2": {"nome": "Hidrogênio", "cor": "#fb923c"},
}

# ESTADO DA SESSÃO
if "connected"            not in st.session_state: st.session_state.connected = False
if "arduino_handler"      not in st.session_state: st.session_state.arduino_handler = None
if "auto_refresh"         not in st.session_state: st.session_state.auto_refresh = True
if "last_valve_states"    not in st.session_state: st.session_state.last_valve_states = {g: False for g in GASES}
if "last_read_time"       not in st.session_state: st.session_state.last_read_time = None
if "valve_stats"          not in st.session_state:
    st.session_state.valve_stats = {g: {"total_time": 0, "last_opened": None} for g in GASES}

# Histórico bruto: todas as leituras individuais (1 por segundo)
if "historico_bruto"      not in st.session_state: st.session_state.historico_bruto = deque(maxlen=None)

# Buffer temporário: acumula leituras do minuto atual para fazer a média
if "buffer_minuto"        not in st.session_state: st.session_state.buffer_minuto = []

# Histórico de médias: 1 ponto por minuto, usado no gráfico de concentração
if "historico_medias"     not in st.session_state: st.session_state.historico_medias = deque(maxlen=None)

# Marca o início do minuto atual de acumulação
if "inicio_minuto_atual"  not in st.session_state: st.session_state.inicio_minuto_atual = None


# =====================================================================
# LEITURA E AGREGAÇÃO DE DADOS
# =====================================================================
def ler_dados_sensores():
    """Lê uma nova amostra do hardware (real ou simulado) a cada ~1s.

    Cada leitura é salva no histórico bruto (tempo real).
    Ao completar 1 minuto de acumulação, calcula a média de O2 e H2
    e registra um ponto no histórico de médias (usado no gráfico).
    """
    agora = time.time()
    if st.session_state.last_read_time and (agora - st.session_state.last_read_time < 1):
        return  # ainda não passou 1 segundo desde a última leitura

    handler = st.session_state.arduino_handler
    if not (handler and handler.is_connected()):
        return

    dado_bruto = handler.read_sensor_data()
    if not dado_bruto:
        return

    registro = handler.get_dataframe_format(dado_bruto)

    # Aplica equação de calibração (y = a*x + b) — ajustar em calculo_concentracao.py
    registro["O2_Conc"] = calcular_concentracao_o2(registro["O2_Raw"])
    registro["H2_Conc"] = calcular_concentracao_h2(registro["H2_Raw"])

    # Salva leitura individual no histórico bruto (para download de tempo real)
    st.session_state.historico_bruto.append(registro)
    st.session_state.last_read_time = agora

    # --- Acumulação para média de 1 minuto ---
    if st.session_state.inicio_minuto_atual is None:
        # Primeiro registro: marca o início do minuto
        st.session_state.inicio_minuto_atual = agora

    st.session_state.buffer_minuto.append(registro)

    segundos_no_minuto = agora - st.session_state.inicio_minuto_atual
    if segundos_no_minuto >= 60:
        _fechar_minuto()


def _fechar_minuto():
    """Calcula a média das leituras acumuladas no último minuto e grava
    um ponto no histórico de médias. Reinicia o buffer para o próximo minuto."""
    buf = st.session_state.buffer_minuto
    if not buf:
        return

    ts_medio = buf[len(buf) // 2]["Timestamp"]   # timestamp central do intervalo

    media = {
        "Timestamp":       ts_medio,
        "O2_Conc_Media":   sum(r["O2_Conc"]       for r in buf) / len(buf),
        "H2_Conc_Media":   sum(r["H2_Conc"]       for r in buf) / len(buf),
        "Ambient_Temp":    sum(r["Ambient_Temp"]   for r in buf) / len(buf),
        "Ambient_Hum":     sum(r["Ambient_Hum"]    for r in buf) / len(buf),
        "Ambient_Pressure":sum(r["Ambient_Pressure"] for r in buf) / len(buf),
        "N_Amostras":      len(buf),
    }

    st.session_state.historico_medias.append(media)

    # Reinicia o buffer e o marcador de início
    st.session_state.buffer_minuto = []
    st.session_state.inicio_minuto_atual = None


def segundos_ate_proximo_ponto():
    """Calcula quantos segundos faltam para fechar o minuto atual (para exibir no UI)."""
    if st.session_state.inicio_minuto_atual is None:
        return 60
    decorrido = time.time() - st.session_state.inicio_minuto_atual
    return max(0, int(60 - decorrido))


# BARRA LATERAL
with st.sidebar:
    st.markdown("### 🔌 Conectividade")
    if MODO_SIMULACAO:
        st.caption("🧪 Modo simulação ativo — dados gerados só para teste de interface")

    if not st.session_state.connected:
        if MODO_SIMULACAO:
            if st.button("🚀 Conectar (simulado)", width="stretch", type="primary"):
                st.session_state.arduino_handler = HandlerSimulado()
                st.session_state.connected = True
                st.rerun()
        else:
            arduino_temp = ArduinoConnection()
            porta_detectada = arduino_temp.detect_arduino_port()
            if porta_detectada:
                porta_serial = porta_detectada
                st.info(f"Porta detectada automaticamente: {porta_serial}")
            else:
                porta_serial = st.text_input("Porta Serial", value="/dev/ttyACM0")
                st.caption("Nenhuma porta detectada automaticamente. Informe a porta manualmente.")
            baud_rate = st.selectbox("Baud Rate", options=[9600, 115200])
            if st.button("🚀 Conectar Hardware", width="stretch", type="primary"):
                arduino_conn = ArduinoConnection(port=porta_serial, baud_rate=baud_rate)
                if arduino_conn.connect():
                    st.session_state.arduino_handler = ArduinoHandler(arduino_conn)
                    st.session_state.connected = True
                    st.rerun()
                else:
                    st.error(f"Não foi possível conectar na porta {porta_serial}. Verifique a porta e o baud rate.")
    else:
        st.success("Conectado")
        if st.button("✖ Desligar Sistema", width="stretch"):
            if st.session_state.arduino_handler:
                if hasattr(st.session_state.arduino_handler, "disconnect"):
                    st.session_state.arduino_handler.disconnect()
                else:
                    st.session_state.arduino_handler.arduino.disconnect()
            st.session_state.connected = False
            st.session_state.arduino_handler = None
            st.session_state.historico_bruto.clear()
            st.session_state.historico_medias.clear()
            st.session_state.buffer_minuto = []
            st.session_state.inicio_minuto_atual = None
            st.rerun()

    st.divider()
    st.session_state.auto_refresh = st.toggle("Atualização automática", value=st.session_state.auto_refresh)
    st.caption("Leitura serial a cada ~1s")

    st.divider()
    if st.button("🔒 Sair", width="stretch"):
        st.session_state.autenticado = False
        st.rerun()


# =====================================================================
# ÁREA PRINCIPAL
# =====================================================================
if st.session_state.connected:
    ler_dados_sensores()

    # DataFrames de trabalho
    df_bruto  = pd.DataFrame(list(st.session_state.historico_bruto))
    df_medias = pd.DataFrame(list(st.session_state.historico_medias))

    st.title("⚗️ Monitor do Misturador de Gás")

    # Indicador de progresso do minuto atual
    if not df_bruto.empty:
        amostras_no_buffer = len(st.session_state.buffer_minuto)
        faltam = segundos_ate_proximo_ponto()
        col_ts, col_prox = st.columns([3, 1])
        col_ts.caption(f"Última leitura: {df_bruto['Timestamp'].iloc[-1].strftime('%H:%M:%S')}  ·  "
                       f"{amostras_no_buffer} amostras no minuto atual  ·  "
                       f"próximo ponto no gráfico em {faltam}s")

    # ── PAINEL DE VÁLVULAS ──────────────────────────────────────────
    st.subheader("🛠️ Válvulas de Entrada")
    v_cols = st.columns(len(GASES))
    for i, (gas, info) in enumerate(GASES.items()):
        with v_cols[i]:
            st.markdown(f'<div class="cartao" style="border-top: 3px solid {info["cor"]};">', unsafe_allow_html=True)
            st.markdown(f"**{info['nome']} ({gas})**")
            aberta = st.toggle(f"Liberar {gas}", key=f"v_{gas}", value=st.session_state.last_valve_states[gas])

            if aberta != st.session_state.last_valve_states[gas]:
                if aberta: st.session_state.arduino_handler.open_valve(gas)
                else:      st.session_state.arduino_handler.close_valve(gas)
                st.session_state.last_valve_states[gas] = aberta

            # Acumula tempo com válvula aberta
            if aberta:
                if st.session_state.valve_stats[gas]["last_opened"] is None:
                    st.session_state.valve_stats[gas]["last_opened"] = datetime.now()
            else:
                if st.session_state.valve_stats[gas]["last_opened"] is not None:
                    decorrido = (datetime.now() - st.session_state.valve_stats[gas]["last_opened"]).total_seconds()
                    st.session_state.valve_stats[gas]["total_time"] += decorrido
                    st.session_state.valve_stats[gas]["last_opened"] = None

            cor_status   = "#34d399" if aberta else "#f87171"
            texto_status = "● LIBERADA" if aberta else "○ FECHADA"
            st.markdown(f'<span style="color:{cor_status};">{texto_status}</span>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="texto-mono">Tempo acumulado: {int(st.session_state.valve_stats[gas]["total_time"])}s</div>',
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    if not df_bruto.empty:
        # ── LEITURAS ATUAIS (última leitura bruta) ──────────────────
        st.subheader("📊 Leituras Atuais")
        ultima   = df_bruto.iloc[-1]
        anterior = df_bruto.iloc[-2] if len(df_bruto) > 1 else ultima

        m_cols = st.columns(5)
        m_cols[0].metric("O2 — Concentração",  f"{ultima['O2_Conc']:.1f} %",
                         f"{ultima['O2_Conc'] - anterior['O2_Conc']:+.1f}")
        m_cols[1].metric("H2 — Concentração",  f"{ultima['H2_Conc']:.1f} %",
                         f"{ultima['H2_Conc'] - anterior['H2_Conc']:+.1f}")
        m_cols[2].metric("Temperatura",         f"{ultima['Ambient_Temp']:.1f} °C",
                         f"{ultima['Ambient_Temp'] - anterior['Ambient_Temp']:+.1f}")
        m_cols[3].metric("Umidade",             f"{ultima['Ambient_Hum']:.1f} %",
                         f"{ultima['Ambient_Hum'] - anterior['Ambient_Hum']:+.1f}")
        m_cols[4].metric("Pressão",             f"{ultima['Ambient_Pressure']:.1f} kPa",
                         f"{ultima['Ambient_Pressure'] - anterior['Ambient_Pressure']:+.2f}")

        # ── ABAS PRINCIPAIS ─────────────────────────────────────────
        tab_conc, tab_amb, tab_hist = st.tabs(["📈 Concentração O2 / H2", "🌡️ Condições Ambientais", "💾 Histórico"])

        # ── ABA: GRÁFICO DE CONCENTRAÇÃO (médias de 1 min) ──────────
        with tab_conc:
            if df_medias.empty:
                # Enquanto o primeiro minuto não fecha, exibe aviso com contagem regressiva
                faltam = segundos_ate_proximo_ponto()
                st.info(
                    f"O gráfico de concentração exibe a **média de cada minuto**. "
                    f"Aguardando o fim do primeiro minuto de coleta — **{faltam}s restantes**."
                )
                # Pré-visualização das leituras brutas do minuto atual (sem escalar o histórico)
                if st.session_state.buffer_minuto:
                    df_buf = pd.DataFrame(st.session_state.buffer_minuto)
                    st.caption(f"Pré-visualização — {len(df_buf)} leituras brutas do minuto atual:")
                    fig_pre = go.Figure()
                    fig_pre.add_trace(go.Scatter(x=df_buf["Timestamp"], y=df_buf["O2_Conc"],
                                                 name="O2 (%)", line=dict(color=GASES["O2"]["cor"], width=2, dash="dot")))
                    fig_pre.add_trace(go.Scatter(x=df_buf["Timestamp"], y=df_buf["H2_Conc"],
                                                 name="H2 (%)", line=dict(color=GASES["H2"]["cor"], width=2, dash="dot")))
                    fig_pre.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                          plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (%)",
                                          height=300)
                    st.plotly_chart(fig_pre, width="stretch")
            else:
                # Gráfico principal: 1 ponto por minuto (média)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_medias["Timestamp"], y=df_medias["O2_Conc_Media"],
                    name="O2 — média/min (%)", mode="lines+markers",
                    line=dict(color=GASES["O2"]["cor"], width=3),
                    marker=dict(size=7),
                ))
                fig.add_trace(go.Scatter(
                    x=df_medias["Timestamp"], y=df_medias["H2_Conc_Media"],
                    name="H2 — média/min (%)", mode="lines+markers",
                    line=dict(color=GASES["H2"]["cor"], width=3),
                    marker=dict(size=7),
                ))
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (%)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig, width="stretch")

                # Pré-visualização pontilhada do minuto em andamento
                if st.session_state.buffer_minuto:
                    df_buf = pd.DataFrame(st.session_state.buffer_minuto)
                    st.caption(f"🔄 Acumulando minuto atual — {len(df_buf)} amostras / {segundos_ate_proximo_ponto()}s para o próximo ponto")

        # ── ABA: CONDIÇÕES AMBIENTAIS (leituras brutas, taxa real) ──
        with tab_amb:
            col_a, col_b = st.columns(2)
            with col_a:
                fig_ta = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ta.add_trace(go.Scatter(x=df_bruto["Timestamp"], y=df_bruto["Ambient_Temp"],
                                            name="Temp (°C)", line=dict(color="#f87171")))
                fig_ta.add_trace(go.Scatter(x=df_bruto["Timestamp"], y=df_bruto["Ambient_Hum"],
                                            name="Umidade (%)", line=dict(color="#60a5fa")), secondary_y=True)
                fig_ta.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ta, width="stretch")
            with col_b:
                fig_p = go.Figure(go.Scatter(x=df_bruto["Timestamp"], y=df_bruto["Ambient_Pressure"],
                                             name="Pressão (kPa)", line=dict(color="#c084fc", width=3)))
                fig_p.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)", yaxis_title="kPa")
                st.plotly_chart(fig_p, width="stretch")

        # ── ABA: HISTÓRICO E DOWNLOADS ───────────────────────────────
        with tab_hist:
            sub_rt, sub_med = st.tabs(["⏱️ Tempo Real (1s)", "📉 Médias por Minuto"])

            # Sub-aba: histórico bruto (uma linha por segundo)
            with sub_rt:
                st.caption("Todas as leituras individuais recebidas via serial, a cada ~1s.")
                colunas_rt = ["Timestamp", "O2_Conc", "H2_Conc",
                              "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure"]
                df_rt_exib = df_bruto[colunas_rt].sort_values("Timestamp", ascending=False)
                df_rt_exib.columns = ["Timestamp", "O2 (%)", "H2 (%)", "Temp (°C)", "Umidade (%)", "Pressão (kPa)"]
                st.dataframe(df_rt_exib, width="stretch")
                st.download_button(
                    "⬇️ Baixar leituras em tempo real (CSV)",
                    data=df_rt_exib.to_csv(index=False).encode("utf-8"),
                    file_name=f"tempo_real_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    width="stretch",
                )

            # Sub-aba: histórico de médias (uma linha por minuto)
            with sub_med:
                if df_medias.empty:
                    st.info("Ainda sem médias calculadas. Aguarde o primeiro minuto completo de coleta.")
                else:
                    st.caption("Uma linha por minuto completo, com a média das leituras do intervalo.")
                    colunas_med = ["Timestamp", "O2_Conc_Media", "H2_Conc_Media",
                                   "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure", "N_Amostras"]
                    df_med_exib = df_medias[colunas_med].sort_values("Timestamp", ascending=False)
                    df_med_exib.columns = ["Timestamp", "O2 média (%)", "H2 média (%)",
                                           "Temp (°C)", "Umidade (%)", "Pressão (kPa)", "Nº amostras"]
                    st.dataframe(df_med_exib, width="stretch")
                    st.download_button(
                        "⬇️ Baixar médias por minuto (CSV)",
                        data=df_med_exib.to_csv(index=False).encode("utf-8"),
                        file_name=f"medias_por_minuto_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        width="stretch",
                    )
    else:
        st.info("Aguardando a primeira leitura dos sensores...")

    if st.session_state.auto_refresh:
        time.sleep(1)
        st.rerun()
else:
    st.info("🔌 Conecte o hardware na barra lateral para começar a monitorar.")
