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
    section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > div,
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        background-color: #0a0f1c !important;
    }
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
INTERVALOS_MEDIA_MINUTOS = [1, 5, 10]

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
if "intervalo_media_minutos" not in st.session_state: st.session_state.intervalo_media_minutos = 1
if "intervalo_media_minutos_anterior" not in st.session_state: st.session_state.intervalo_media_minutos_anterior = 1
if "last_valve_states"    not in st.session_state: st.session_state.last_valve_states = {g: False for g in GASES}
if "last_read_time"       not in st.session_state: st.session_state.last_read_time = None
if "valve_stats"          not in st.session_state:
    st.session_state.valve_stats = {g: {"total_time": 0, "last_opened": None} for g in GASES}

# Histórico bruto: todas as leituras individuais (1 por segundo)
if "historico_bruto"      not in st.session_state: st.session_state.historico_bruto = deque(maxlen=None)

# Buffer temporário: acumula leituras da janela atual para a pré-visualização
if "buffer_minuto"        not in st.session_state: st.session_state.buffer_minuto = []

# Marca o início da janela atual de acumulação
if "inicio_minuto_atual"  not in st.session_state: st.session_state.inicio_minuto_atual = None


# =====================================================================
# LEITURA E AGREGAÇÃO DE DADOS
# =====================================================================
def ler_dados_sensores():
    """Lê uma nova amostra do hardware (real ou simulado) a cada ~1s.

    Cada leitura é salva no histórico bruto (tempo real).
    Ao completar a janela selecionada, reinicia a pré-visualização da janela.
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
    registro["H2_Conc"] = calcular_concentracao_h2(registro["H2_Raw"])
    registro["O2_Conc"] = calcular_concentracao_o2(registro["H2_Conc"])

    # Salva leitura individual no histórico bruto (para download de tempo real)
    st.session_state.historico_bruto.append(registro)
    st.session_state.last_read_time = agora

    intervalo_segundos = st.session_state.intervalo_media_minutos * 60

    # --- Acumulação para pré-visualização da janela selecionada ---
    if st.session_state.inicio_minuto_atual is None:
        # Primeiro registro: marca o início da janela
        st.session_state.inicio_minuto_atual = agora

    st.session_state.buffer_minuto.append(registro)

    segundos_no_minuto = agora - st.session_state.inicio_minuto_atual
    if segundos_no_minuto >= intervalo_segundos:
        _fechar_minuto()


def _fechar_minuto():
    """Reinicia a pré-visualização da janela atual após ela completar."""
    st.session_state.buffer_minuto = []
    st.session_state.inicio_minuto_atual = None


def segundos_ate_proximo_ponto():
    """Calcula quantos segundos faltam para fechar a janela atual."""
    intervalo_segundos = st.session_state.intervalo_media_minutos * 60
    if st.session_state.inicio_minuto_atual is None:
        return intervalo_segundos
    decorrido = time.time() - st.session_state.inicio_minuto_atual
    return max(0, int(intervalo_segundos - decorrido))


def agregar_por_intervalo(df: pd.DataFrame, intervalo_minutos: int) -> pd.DataFrame:
    """Agrupa leituras brutas em janelas completas de tempo."""
    if df.empty:
        return pd.DataFrame(columns=[
            "Timestamp", "O2_Conc_Media", "H2_Conc_Media",
            "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure", "N_Amostras",
        ])

    df = df.sort_values("Timestamp").reset_index(drop=True).copy()
    intervalo_segundos = intervalo_minutos * 60
    inicio = df["Timestamp"].iloc[0]
    ultimo_timestamp = df["Timestamp"].iloc[-1]

    df["_bucket"] = ((df["Timestamp"] - inicio).dt.total_seconds() // intervalo_segundos).astype(int)
    df["_bucket_inicio"] = inicio + pd.to_timedelta(df["_bucket"] * intervalo_segundos, unit="s")
    df["_bucket_fim"] = df["_bucket_inicio"] + pd.to_timedelta(intervalo_segundos, unit="s")

    df = df[df["_bucket_fim"] <= ultimo_timestamp]
    if df.empty:
        return pd.DataFrame(columns=[
            "Timestamp", "O2_Conc_Media", "H2_Conc_Media",
            "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure", "N_Amostras",
        ])

    agrupado = (
        df.groupby("_bucket", as_index=False)
        .agg(
            Timestamp=("_bucket_fim", "first"),
            O2_Conc_Media=("O2_Conc", "mean"),
            H2_Conc_Media=("H2_Conc", "mean"),
            Ambient_Temp=("Ambient_Temp", "mean"),
            Ambient_Hum=("Ambient_Hum", "mean"),
            Ambient_Pressure=("Ambient_Pressure", "mean"),
            N_Amostras=("Timestamp", "size"),
        )
        .drop(columns=["_bucket"], errors="ignore")
        .sort_values("Timestamp")
        .reset_index(drop=True)
    )

    return agrupado


# BARRA LATERAL
with st.sidebar:
    st.markdown("### 🔌 Conectividade")
    if MODO_SIMULACAO:
        st.caption("🧪 Modo simulação ativo — dados gerados só para teste de interface")

    st.session_state.intervalo_media_minutos = st.selectbox(
        "Janela de média",
        options=INTERVALOS_MEDIA_MINUTOS,
        index=INTERVALOS_MEDIA_MINUTOS.index(st.session_state.intervalo_media_minutos),
        format_func=lambda valor: f"{valor} minuto{'s' if valor > 1 else ''}",
    )
    if st.session_state.intervalo_media_minutos != st.session_state.intervalo_media_minutos_anterior:
        st.session_state.buffer_minuto = []
        st.session_state.inicio_minuto_atual = None
        st.session_state.intervalo_media_minutos_anterior = st.session_state.intervalo_media_minutos

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
    df_medias = agregar_por_intervalo(df_bruto, st.session_state.intervalo_media_minutos)

    st.title("⚗️ Monitor do Misturador de Gás")

    # Indicador de progresso do minuto atual
    if not df_bruto.empty:
        amostras_no_buffer = len(st.session_state.buffer_minuto)
        faltam = segundos_ate_proximo_ponto()
        col_ts, col_prox = st.columns([3, 1])
        col_ts.caption(f"Última leitura: {df_bruto['Timestamp'].iloc[-1].strftime('%H:%M:%S')}  ·  "
                       f"{amostras_no_buffer} amostras na janela atual  ·  "
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
        m_cols[0].metric("O2 — Concentração",  f"{ultima['O2_Conc']:.0f} ppm",
                 f"{ultima['O2_Conc'] - anterior['O2_Conc']:+.0f} ppm")
        m_cols[1].metric("H2 — Concentração",  f"{ultima['H2_Conc']:.0f} ppm",
                 f"{ultima['H2_Conc'] - anterior['H2_Conc']:+.0f} ppm")
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
                    f"O gráfico de concentração exibe a **média de cada janela**. "
                    f"Aguardando o fim da primeira janela selecionada — **{faltam}s restantes**."
                )
                # Pré-visualização das leituras brutas da janela atual
                if st.session_state.buffer_minuto:
                    df_buf = pd.DataFrame(st.session_state.buffer_minuto)
                    st.caption(f"Pré-visualização — {len(df_buf)} leituras brutas da janela atual:")
                    fig_pre = go.Figure()
                    fig_pre.add_trace(go.Scatter(x=df_buf["Timestamp"], y=df_buf["O2_Conc"],
                                                 name="O2 (ppm)", line=dict(color=GASES["O2"]["cor"], width=2, dash="dot")))
                    fig_pre.add_trace(go.Scatter(x=df_buf["Timestamp"], y=df_buf["H2_Conc"],
                                                 name="H2 (ppm)", line=dict(color=GASES["H2"]["cor"], width=2, dash="dot")))
                    fig_pre.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                          plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (ppm)",
                                          height=300)
                    st.plotly_chart(fig_pre, width="stretch")
            else:
                # Gráfico principal: 1 ponto por janela completa
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_medias["Timestamp"], y=df_medias["O2_Conc_Media"],
                    name=f"O2 — média/{st.session_state.intervalo_media_minutos} min (ppm)", mode="lines+markers",
                    line=dict(color=GASES["O2"]["cor"], width=3),
                    marker=dict(size=7),
                ))
                fig.add_trace(go.Scatter(
                    x=df_medias["Timestamp"], y=df_medias["H2_Conc_Media"],
                    name=f"H2 — média/{st.session_state.intervalo_media_minutos} min (ppm)", mode="lines+markers",
                    line=dict(color=GASES["H2"]["cor"], width=3),
                    marker=dict(size=7),
                ))
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (ppm)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig, width="stretch")

                # Pré-visualização pontilhada do minuto em andamento
                if st.session_state.buffer_minuto:
                    df_buf = pd.DataFrame(st.session_state.buffer_minuto)
                    st.caption(f"🔄 Acumulando janela atual — {len(df_buf)} amostras / {segundos_ate_proximo_ponto()}s para o próximo ponto")
                    fig_preview = go.Figure()
                    fig_preview.add_trace(go.Scatter(
                        x=df_buf["Timestamp"], y=df_buf["O2_Conc"],
                        name="O2 em andamento", mode="lines",
                        line=dict(color=GASES["O2"]["cor"], width=2, dash="dot"),
                    ))
                    fig_preview.add_trace(go.Scatter(
                        x=df_buf["Timestamp"], y=df_buf["H2_Conc"],
                        name="H2 em andamento", mode="lines",
                        line=dict(color=GASES["H2"]["cor"], width=2, dash="dot"),
                    ))
                    fig_preview.update_layout(
                        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Concentração (ppm)",
                        height=260,
                    )
                    st.plotly_chart(fig_preview, width="stretch")

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
            sub_rt, sub_med = st.tabs(["⏱️ Tempo Real (1s)", "📉 Médias por Janela"])

            # Sub-aba: histórico bruto (uma linha por segundo)
            with sub_rt:
                st.caption("Todas as leituras individuais recebidas via serial, a cada ~1s.")
                colunas_rt = ["Timestamp", "O2_Conc", "H2_Conc",
                              "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure"]
                df_rt_exib = df_bruto[colunas_rt].sort_values("Timestamp", ascending=False)
                df_rt_exib.columns = ["Timestamp", "O2 (ppm)", "H2 (ppm)", "Temp (°C)", "Umidade (%)", "Pressão (kPa)"]
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
                    st.info(
                        f"Ainda sem médias calculadas. Aguarde o primeiro intervalo completo de {st.session_state.intervalo_media_minutos} minuto(s)."
                    )
                else:
                    st.caption(
                        f"Uma linha por janela completa de {st.session_state.intervalo_media_minutos} minuto(s), com a média das leituras do intervalo."
                    )
                    colunas_med = ["Timestamp", "O2_Conc_Media", "H2_Conc_Media",
                                   "Ambient_Temp", "Ambient_Hum", "Ambient_Pressure", "N_Amostras"]
                    df_med_exib = df_medias[colunas_med].sort_values("Timestamp", ascending=False)
                    df_med_exib.columns = ["Timestamp", "O2 média (ppm)", "H2 média (ppm)",
                                           "Temp (°C)", "Umidade (%)", "Pressão (kPa)", "Nº amostras"]
                    st.dataframe(df_med_exib, width="stretch")
                    st.download_button(
                        "⬇️ Baixar médias por janela (CSV)",
                        data=df_med_exib.to_csv(index=False).encode("utf-8"),
                        file_name=f"medias_por_janela_{st.session_state.intervalo_media_minutos}min_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
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
