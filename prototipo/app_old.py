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

# --- ESTILO GLOBAL (paleta escura, cartões e tipografia consistentes) ---
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

# --- LOGIN: interrompe a execução aqui se a senha ainda não foi validada ---
exigir_login()

# =====================================================================
# MODO DE OPERAÇÃO
#   True  -> usa o simulador (simulador.py) para testar a tela sem hardware
#   False -> usa a conexão real com o Arduino (arduino_connection / arduino_handler)
# Para testar com dados reais, basta trocar para False. Quando não precisar
# mais simular, o arquivo simulador.py pode ser apagado.
# =====================================================================
MODO_SIMULACAO = True

if MODO_SIMULACAO:
    from simulador import HandlerSimulado
else:
    from arduino_connection import ArduinoConnection
    from arduino_handler import ArduinoHandler

# --- GASES MONITORADOS (cor de identificação usada nos cartões e gráficos) ---
GASES = {
    "O2": {"nome": "Oxigênio", "cor": "#38bdf8"},
    "H2": {"nome": "Hidrogênio", "cor": "#fb923c"},
}

# --- ESTADO DA SESSÃO ---
if "connected" not in st.session_state: st.session_state.connected = False
if "arduino_handler" not in st.session_state: st.session_state.arduino_handler = None
if "valve_stats" not in st.session_state:
    st.session_state.valve_stats = {gas: {"total_time": 0, "last_opened": None} for gas in GASES}
if "data_history" not in st.session_state: st.session_state.data_history = deque(maxlen=None)
if "last_valve_states" not in st.session_state:
    st.session_state.last_valve_states = {gas: False for gas in GASES}
if "last_read_time" not in st.session_state: st.session_state.last_read_time = None
if "auto_refresh" not in st.session_state: st.session_state.auto_refresh = True


def ler_dados_sensores():
    """Lê uma nova amostra do hardware (real ou simulado), no máximo 1x a cada 2s,
    e já converte as leituras brutas de O2/H2 em concentração (%)."""
    agora = time.time()
    if st.session_state.last_read_time and (agora - st.session_state.last_read_time < 2):
        return
    handler = st.session_state.arduino_handler
    if handler and handler.is_connected():
        dado_bruto = handler.read_sensor_data()
        if dado_bruto:
            registro = handler.get_dataframe_format(dado_bruto)
            # --- aqui entra a equação de calibração (y = a*x + b) ---
            registro["O2_Conc"] = calcular_concentracao_o2(registro["O2_Raw"])
            registro["H2_Conc"] = calcular_concentracao_h2(registro["H2_Raw"])
            st.session_state.data_history.append(registro)
            st.session_state.last_read_time = agora


# --- BARRA LATERAL ---
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
            portas = arduino_temp.list_available_ports()
            porta_serial = st.selectbox("Porta Serial", options=portas if portas else ["COM3"])
            baud_rate = st.selectbox("Baud Rate", options=[9600, 115200])
            if st.button("🚀 Conectar Hardware", width="stretch", type="primary"):
                arduino_conn = ArduinoConnection(port=porta_serial, baud_rate=baud_rate)
                if arduino_conn.connect():
                    st.session_state.arduino_handler = ArduinoHandler(arduino_conn)
                    st.session_state.connected = True
                    st.rerun()
    else:
        st.success("Conectado")
        if st.button("✖ Desligar Sistema", width="stretch"):
            if st.session_state.arduino_handler:
                st.session_state.arduino_handler.arduino.disconnect()
            st.session_state.connected = False
            st.session_state.arduino_handler = None
            st.session_state.data_history.clear()
            st.rerun()

    st.divider()
    st.session_state.auto_refresh = st.toggle("Atualização automática", value=st.session_state.auto_refresh)
    st.caption("Atualiza a leitura a cada ~1s")

    st.divider()
    if st.button("🔒 Sair", width="stretch"):
        st.session_state.autenticado = False
        st.rerun()

# --- ÁREA PRINCIPAL ---
if st.session_state.connected:
    ler_dados_sensores()
    df = pd.DataFrame(list(st.session_state.data_history))

    st.title("⚗️ Monitor do Misturador de Gás")
    if not df.empty:
        st.caption(f"Última leitura: {df['Timestamp'].iloc[-1].strftime('%H:%M:%S')}")

    # --- PAINEL DE VÁLVULAS ---
    st.subheader("🛠️ Válvulas de Entrada")
    v_cols = st.columns(len(GASES))
    for i, (gas, info) in enumerate(GASES.items()):
        with v_cols[i]:
            st.markdown(f'<div class="cartao" style="border-top: 3px solid {info["cor"]};">', unsafe_allow_html=True)
            st.markdown(f"**{info['nome']} ({gas})**")
            aberta = st.toggle(f"Liberar {gas}", key=f"v_{gas}", value=st.session_state.last_valve_states[gas])

            if aberta != st.session_state.last_valve_states[gas]:
                if aberta: st.session_state.arduino_handler.open_valve(gas)
                else: st.session_state.arduino_handler.close_valve(gas)
                st.session_state.last_valve_states[gas] = aberta

            # acumula o tempo em que a válvula ficou aberta
            if aberta:
                if st.session_state.valve_stats[gas]["last_opened"] is None:
                    st.session_state.valve_stats[gas]["last_opened"] = datetime.now()
            else:
                if st.session_state.valve_stats[gas]["last_opened"] is not None:
                    decorrido = (datetime.now() - st.session_state.valve_stats[gas]["last_opened"]).total_seconds()
                    st.session_state.valve_stats[gas]["total_time"] += decorrido
                    st.session_state.valve_stats[gas]["last_opened"] = None

            cor_status = "#34d399" if aberta else "#f87171"
            texto_status = "● LIBERADA" if aberta else "○ FECHADA"
            st.markdown(f'<span style="color:{cor_status};">{texto_status}</span>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="texto-mono">Tempo acumulado: {int(st.session_state.valve_stats[gas]["total_time"])}s</div>',
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    if not df.empty:
        # --- LEITURAS ATUAIS ---
        st.subheader("📊 Leituras Atuais")
        ultima = df.iloc[-1]
        anterior = df.iloc[-2] if len(df) > 1 else ultima

        m_cols = st.columns(5)
        m_cols[0].metric("O2 — Concentração", f"{ultima['O2_Conc']:.1f} %", f"{ultima['O2_Conc'] - anterior['O2_Conc']:+.1f}")
        m_cols[1].metric("H2 — Concentração", f"{ultima['H2_Conc']:.1f} %", f"{ultima['H2_Conc'] - anterior['H2_Conc']:+.1f}")
        m_cols[2].metric("Temperatura", f"{ultima['Ambient_Temp']:.1f} °C", f"{ultima['Ambient_Temp'] - anterior['Ambient_Temp']:+.1f}")
        m_cols[3].metric("Umidade", f"{ultima['Ambient_Hum']:.1f} %", f"{ultima['Ambient_Hum'] - anterior['Ambient_Hum']:+.1f}")
        m_cols[4].metric("Pressão", f"{ultima['Ambient_Pressure']:.1f} kPa", f"{ultima['Ambient_Pressure'] - anterior['Ambient_Pressure']:+.2f}")

        # --- GRÁFICOS E HISTÓRICO ---
        tab_conc, tab_amb, tab_csv = st.tabs(["📈 Concentração O2 / H2", "🌡️ Condições Ambientais", "💾 Histórico"])

        with tab_conc:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["O2_Conc"], name="O2 (%)", line=dict(color=GASES["O2"]["cor"], width=3)))
            fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["H2_Conc"], name="H2 (%)", line=dict(color=GASES["H2"]["cor"], width=3)))
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (%)")
            st.plotly_chart(fig, width="stretch")

        with tab_amb:
            col_a, col_b = st.columns(2)
            with col_a:
                fig_temp_umid = make_subplots(specs=[[{"secondary_y": True}]])
                fig_temp_umid.add_trace(go.Scatter(x=df["Timestamp"], y=df["Ambient_Temp"], name="Temp (°C)", line=dict(color="#f87171")))
                fig_temp_umid.add_trace(go.Scatter(x=df["Timestamp"], y=df["Ambient_Hum"], name="Umidade (%)", line=dict(color="#60a5fa")), secondary_y=True)
                fig_temp_umid.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_temp_umid, width="stretch")
            with col_b:
                fig_pressao = go.Figure(go.Scatter(x=df["Timestamp"], y=df["Ambient_Pressure"], name="Pressão (kPa)", line=dict(color="#c084fc", width=3)))
                fig_pressao.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title="kPa")
                st.plotly_chart(fig_pressao, width="stretch")

        with tab_csv:
            df_ordenado = df.sort_values(by="Timestamp", ascending=False)
            st.dataframe(df_ordenado, width="stretch")
            st.download_button(
                "⬇️ Baixar histórico (CSV)",
                data=df_ordenado.to_csv(index=False).encode("utf-8"),
                file_name=f"historico_misturador_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
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
