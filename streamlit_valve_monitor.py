import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
from datetime import datetime
from collections import deque
from arduino_connection import ArduinoConnection
from arduino_handler import ArduinoHandler

# Configuração inicial.
st.set_page_config(page_title="Monitor de Gases Industriais", layout="wide")

# Estilo.
st.markdown("""
<style>
    .stApp { background-color: #0f172a !important; color: #ffffff !important; }
    .control-panel { 
        background-color: #1e293b !important; 
        padding: 20px; 
        border-radius: 15px; 
        border: 1px solid #334155; 
        margin-bottom: 20px;
    }
    h1, h2, h3, p, span, label, .stMarkdown { color: #ffffff !important; }
    .stButton>button { background-color: #334155 !important; color: white !important; border: 1px solid #475569 !important; }
    div[data-baseweb="select"] > div, input { background-color: #0f172a !important; color: white !important; border: 1px solid #334155 !important; }
    .time-font { font-family: 'Courier New', monospace; font-size: 12px; color: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# Config.
FLOW_GASES = {'Metano': '#f59e0b'}
CONCENTRATION_GASES = {'CO': '#ef4444', 'CO2': '#2dd4bf', 'H2': '#a855f7'}

# Session state.
if 'connected' not in st.session_state: st.session_state.connected = False
if 'arduino_handler' not in st.session_state: st.session_state.arduino_handler = None
if 'valve_stats' not in st.session_state: st.session_state.valve_stats = {gas: {'total_time': 0, 'last_opened': None} for gas in FLOW_GASES}
if 'data_history' not in st.session_state: st.session_state.data_history = deque(maxlen=None)
if 'last_valve_states' not in st.session_state: st.session_state.last_valve_states = {gas: False for gas in FLOW_GASES}
if 'last_read_time' not in st.session_state: st.session_state.last_read_time = None

def read_arduino_data():
    current_time = time.time()
    if st.session_state.last_read_time and (current_time - st.session_state.last_read_time < 2):
        return
    if st.session_state.arduino_handler and st.session_state.arduino_handler.is_connected():
        data = st.session_state.arduino_handler.read_sensor_data()
        if data:
            fmt = st.session_state.arduino_handler.get_dataframe_format(data)
            st.session_state.data_history.append(fmt)
            st.session_state.last_read_time = current_time

# Barra lateral.
with st.sidebar:
    st.markdown("### 🔌 Conectividade")
    if not st.session_state.connected:
        arduino_temp = ArduinoConnection()
        porta_detectada = arduino_temp.detect_arduino_port()
        if porta_detectada:
            porta_serial = porta_detectada
            st.info(f"Porta detectada automaticamente: {porta_serial}")
        else:
            porta_serial = st.text_input("Porta Serial", value="/dev/ttyACM0")
            st.caption("Nenhuma porta detectada automaticamente. Informe a porta manualmente.")
        baud_rate = st.selectbox("Baud Rate", options=[9600, 115200])
        
        if st.button("🚀 Conectar Hardware", width='stretch', type="primary"):
            arduino_conn = ArduinoConnection(port=porta_serial, baud_rate=baud_rate)
            if arduino_conn.connect():
                st.session_state.arduino_handler = ArduinoHandler(arduino_conn)
                st.session_state.connected = True
                st.rerun()
            else:
                st.error(f"Não foi possível conectar na porta {porta_serial}. Verifique a porta e o baud rate.")
    else:
        st.success("Hardware Conectado")
        if st.button("✖ Desligar Sistema", width='stretch'):
            if st.session_state.arduino_handler:
                if hasattr(st.session_state.arduino_handler, "disconnect"):
                    st.session_state.arduino_handler.disconnect()
                else:
                    st.session_state.arduino_handler.arduino.disconnect()
            st.session_state.connected = False
            st.session_state.arduino_handler = None
            st.session_state.data_history.clear()
            st.rerun()

# Área principal.
if st.session_state.connected:
    read_arduino_data()
    df = pd.DataFrame(list(st.session_state.data_history))
    
    st.title("📊 Gestão Operacional de Válvulas")

    # Cards de válvula.
    v_cols = st.columns(len(FLOW_GASES))
    for i, (gas, color) in enumerate(FLOW_GASES.items()):
        with v_cols[i]:
            st.markdown(f'<div class="control-panel" style="border-top: 5px solid {color};">', unsafe_allow_html=True)
            st.markdown(f"**Válvula: {gas}**")
            is_open = st.toggle(f"Operar {gas}", key=f"v_{gas}", value=st.session_state.last_valve_states[gas])
            
            if is_open != st.session_state.last_valve_states[gas]:
                if is_open: st.session_state.arduino_handler.open_valve(gas)
                else: st.session_state.arduino_handler.close_valve(gas)
                st.session_state.last_valve_states[gas] = is_open
            
            status_color = "#2dd4bf" if is_open else "#f87171"
            status_text = "● ABERTA" if is_open else "○ FECHADA"
            
            if is_open:
                if st.session_state.valve_stats[gas]['last_opened'] is None:
                    st.session_state.valve_stats[gas]['last_opened'] = datetime.now()
            else:
                if st.session_state.valve_stats[gas]['last_opened'] is not None:
                    st.session_state.valve_stats[gas]['total_time'] += (datetime.now() - st.session_state.valve_stats[gas]['last_opened']).total_seconds()
                    st.session_state.valve_stats[gas]['last_opened'] = None
            
            st.markdown(f'<span style="color:{status_color};">{status_text}</span>', unsafe_allow_html=True)
            st.markdown(f'<div class="time-font">Acumulado: {int(st.session_state.valve_stats[gas]["total_time"])}s</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # Gráficos e histórico.
    if not df.empty:
        tab_f, tab_r, tab_s, tab_csv = st.tabs(["📈 VAZÃO", "📊 CONCENTRAÇÃO", "☁️ SENSORES DO AR", "💾 HISTÓRICO"])
        
        with tab_f:
            fig = go.Figure(go.Scatter(x=df['Timestamp'], y=df['Metane_Flow'], name="Metano", line=dict(color='#f59e0b', width=3)))
            fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, width='stretch')

        with tab_r:
            fig_r = go.Figure()
            for gas, color in {**CONCENTRATION_GASES, **FLOW_GASES}.items():
                col = f'{gas}_Rel'
                if col in df.columns:
                    fig_r.add_trace(go.Scatter(x=df['Timestamp'], y=df[col], name=gas, line=dict(color=color), fill='tozeroy'))
            fig_r.update_layout(yaxis=dict(range=[0, 1024]), template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_r, width='stretch')

        with tab_s:
            fig_air = make_subplots(specs=[[{"secondary_y": True}]])
            fig_air.add_trace(go.Scatter(x=df['Timestamp'], y=df['Ambient_Temp'], name="Temp (°C)", line=dict(color='#ff4b4b')))
            fig_air.add_trace(go.Scatter(x=df['Timestamp'], y=df['Ambient_Hum'], name="Umidade (%)", line=dict(color='#3b82f6')), secondary_y=True)
            fig_air.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_air, width='stretch')

        with tab_csv:
            st.dataframe(df.sort_values(by='Timestamp', ascending=False), width='stretch')

    time.sleep(1)
    st.rerun()
else:
    st.info("Aguardando conexão com o hardware na barra lateral...")