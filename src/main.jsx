import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const gasConfig = {
  O2: { label: "Oxigênio", color: "#35c8f4", tint: "cyan" },
  H2: { label: "Hidrogênio", color: "#ff9d5c", tint: "orange" },
};

function formatPpm(value) {
  return `${(value / 1000).toFixed(0)}k`;
}

function LineChart({ data, dataKey, color, label, unit = "ppm" }) {
  const width = 720;
  const height = 220;
  const values = data.map((item) => item[dataKey]);
  if (!data.length) {
    return <div className="chart-wrap"><div className="chart-legend"><span className="legend-dot" style={{ background: color }} />{label}<span className="chart-unit">{unit}</span></div><p>Nenhuma leitura disponível.</p></div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = data.map((item, index) => {
    const x = 26 + (index * (width - 52)) / Math.max(data.length - 1, 1);
    const y = height - 32 - ((item[dataKey] - min) / range) * (height - 72);
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="chart-wrap">
      <div className="chart-legend"><span className="legend-dot" style={{ background: color }} />{label}<span className="chart-unit">{unit}</span></div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Gráfico de ${label}`}>
        {[0, 1, 2, 3].map((line) => <line key={line} x1="26" x2={width - 26} y1={32 + line * 48} y2={32 + line * 48} className="grid-line" />)}
        <polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((item, index) => {
          const [x, y] = points.split(" ")[index].split(",");
          return <circle key={`${item.time}-${index}`} cx={x} cy={y} r="4" fill="#101c2d" stroke={color} strokeWidth="2" />;
        })}
      </svg>
      <div className="chart-labels">{data.map((item, index) => <span key={`${item.time}-${index}`}>{item.time}</span>)}</div>
    </div>
  );
}

function movingAverage(data, key, windowSize = 3) {
  return data.map((item, index) => {
    const window = data.slice(Math.max(0, index - windowSize + 1), index + 1);
    return {
      ...item,
      [key]: window.reduce((total, entry) => total + entry[key], 0) / window.length,
    };
  });
}

function movingAverageRows(data, windowSize = 3) {
  return data.map((item, index) => {
    const window = data.slice(Math.max(0, index - windowSize + 1), index + 1);
    return {
      ...item,
      o2: window.reduce((total, entry) => total + entry.o2, 0) / window.length,
      h2: window.reduce((total, entry) => total + entry.h2, 0) / window.length,
      temp: window.reduce((total, entry) => total + entry.temp, 0) / window.length,
      humidity: window.reduce((total, entry) => total + entry.humidity, 0) / window.length,
      pressure: window.reduce((total, entry) => total + entry.pressure, 0) / window.length,
    };
  });
}

function mapReading(item) {
  const date = new Date(item.date_time);
  return {
    dateTime: item.date_time,
    time: date.toLocaleString("pt-BR"),
    o2: item.concentracao_o2,
    h2: item.concentracao_h2,
    temp: item.temperatura,
    humidity: item.umidade,
    pressure: item.pressao,
  };
}

function Login({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  function submit(event) {
    event.preventDefault();
    if (password === "H2O2#2026") onLogin();
    else setError("Senha incorreta. Tente novamente.");
  }
  return (
    <main className="login-page">
      <div className="login-glow" />
      <section className="login-card">
        <div className="brand-mark">MG</div>
        <p className="eyebrow">MONITORAMENTO DE GÁS</p>
        <h1>Acesso restrito</h1>
        <p className="login-copy">Entre para acompanhar os sensores.</p>
        <form onSubmit={submit}>
          <label htmlFor="password">Senha de acesso</label>
          <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Digite sua senha" autoFocus />
          {error && <p className="form-error">{error}</p>}
          <button className="button primary full" type="submit">Entrar <span>→</span></button>
        </form>
        <p className="login-foot">Acesso protegido · v1.0</p>
      </section>
    </main>
  );
}

function Metric({ icon, label, value, detail, tone }) {
  return <article className="metric-card">
    <div className={`metric-icon ${tone}`}>{icon}</div>
    <div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div>
  </article>;
}

function App() {
  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const [authenticated, setAuthenticated] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("gasmix-theme") || "dark");
  const [connected, setConnected] = useState(false);
  const [arduinoStatus, setArduinoStatus] = useState({ connected: false, last_reading: null, error: null });
  const [availablePorts, setAvailablePorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [activeTab, setActiveTab] = useState("concentration");
  const [interval, setIntervalValue] = useState(1);
  const [readings, setReadings] = useState([]);
  const [historyReadings, setHistoryReadings] = useState([]);
  const [historyMode, setHistoryMode] = useState("realtime");
  const [filterStart, setFilterStart] = useState("");
  const [filterEnd, setFilterEnd] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("--");

  async function loadAvailablePorts() {
    try {
      const response = await fetch(`${apiBase}/api/arduino/ports`);
      if (!response.ok) throw new Error("Não foi possível listar as portas.");
      const ports = await response.json();
      setAvailablePorts(ports);
      setSelectedPort((currentPort) => currentPort || ports[0]?.device || "");
      setConnectionError("");
    } catch {
      setConnectionError("Não foi possível listar as portas seriais.");
    }
  }

  useEffect(() => {
    loadAvailablePorts();
  }, [apiBase]);

  useEffect(() => {
    if (!connected) return undefined;
    const socketUrl = `${apiBase.replace(/^http/, "ws")}/ws`;
    const socket = new WebSocket(socketUrl);
    socket.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      const next = mapReading(payload);
      const date = new Date(payload.date_time);
      setReadings((items) => [...items.slice(-7), next]);
      if (historyMode === "realtime") {
        setHistoryReadings((items) => [...items, next].slice(-100));
      }
      setLastUpdated(date.toLocaleTimeString("pt-BR"));
    };
    socket.onerror = () => setConnected(false);
    return () => socket.close();
  }, [apiBase, connected, historyMode]);

  async function toggleArduinoConnection() {
    setConnectionError("");
    if (connected) {
      await fetch(`${apiBase}/api/arduino/disconnect`, { method: "POST" });
      setConnected(false);
      return;
    }
    if (!selectedPort) {
      setConnectionError("Selecione uma porta serial.");
      return;
    }
    try {
      const response = await fetch(`${apiBase}/api/arduino/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ port: selectedPort }),
      });
      const status = await response.json();
      if (!response.ok) throw new Error(status.detail || "Não foi possível conectar.");
      setArduinoStatus(status);
      setConnected(true);
    } catch (error) {
      setConnectionError(error.message);
    }
  }

  useEffect(() => {
    if (!connected) {
      setArduinoStatus({ connected: false, last_reading: null, error: null });
      return undefined;
    }
    let active = true;
    const updateStatus = () => {
      fetch(`${apiBase}/api/arduino/status`)
        .then((response) => {
          if (!response.ok) throw new Error("Não foi possível consultar o Arduino.");
          return response.json();
        })
        .then((status) => {
          if (active) setArduinoStatus(status);
        })
        .catch(() => {
          if (active) setArduinoStatus({ connected: false, last_reading: null, error: "Backend indisponível" });
        });
    };
    updateStatus();
    const timer = window.setInterval(updateStatus, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [apiBase, connected]);

  useEffect(() => {
    if (!connected || historyMode !== "realtime") return undefined;
    let active = true;
    const loadReadings = () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
      const params = new URLSearchParams({ inicio: start.toISOString(), fim: end.toISOString() });
      fetch(`${apiBase}/api/leituras?${params}`)
        .then((response) => {
          if (!response.ok) throw new Error("Não foi possível consultar o histórico.");
          return response.json();
        })
        .then((items) => {
          if (!active) return;
          const mapped = items.map(mapReading);
          setReadings(mapped.slice(-8));
          setHistoryReadings(historyMode === "realtime" ? mapped.slice(-100) : mapped);
        })
        .catch(() => {
          if (active) setConnectionError("Não foi possível carregar as leituras do banco.");
        });
    };
    loadReadings();
    const timer = window.setInterval(loadReadings, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [apiBase, connected, historyMode]);

  async function applyHistoryFilter(event) {
    event.preventDefault();
    if (!filterStart || !filterEnd) {
      setConnectionError("Informe a data e o horário inicial e final.");
      return;
    }
    if (new Date(filterStart) > new Date(filterEnd)) {
      setConnectionError("O início do filtro deve ser anterior ao fim.");
      return;
    }
    setHistoryLoading(true);
    setConnectionError("");
    try {
      const params = new URLSearchParams({
        inicio: new Date(filterStart).toISOString(),
        fim: new Date(filterEnd).toISOString(),
      });
      const response = await fetch(`${apiBase}/api/leituras?${params}`);
      if (!response.ok) throw new Error("Não foi possível consultar o período informado.");
      setHistoryReadings((await response.json()).map(mapReading));
      setHistoryMode("filtered");
    } catch (error) {
      setConnectionError(error.message);
    } finally {
      setHistoryLoading(false);
    }
  }

  function showRealtimeHistory() {
    setHistoryMode("realtime");
    setConnectionError("");
    const end = new Date();
    const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
    const params = new URLSearchParams({ inicio: start.toISOString(), fim: end.toISOString() });
    setHistoryLoading(true);
    fetch(`${apiBase}/api/leituras?${params}`)
      .then((response) => {
        if (!response.ok) throw new Error("Não foi possível consultar as leituras recentes.");
        return response.json();
      })
      .then((items) => setHistoryReadings(items.map(mapReading)))
      .catch((error) => setConnectionError(error.message))
      .finally(() => setHistoryLoading(false));
  }

  const current = readings[readings.length - 1];
  const previous = readings[readings.length - 2];
  const averageReadings = useMemo(() => ({
    o2: movingAverage(readings, "o2"),
    h2: movingAverage(readings, "h2"),
  }), [readings]);
  const historyAverages = useMemo(() => movingAverageRows(historyReadings), [historyReadings]);
  const delta = (key, digits = 0) => {
    if (!current || !previous) return "--";
    const difference = current[key] - previous[key];
    return `${difference >= 0 ? "+" : ""}${difference.toFixed(digits)}`;
  };
  const csv = useMemo(() => {
    const headers = "Tipo,Timestamp,O2_Conc,H2_Conc,Ambient_Temp,Ambient_Hum,Ambient_Pressure";
    const row = (type, item) => [type, item.dateTime, item.o2, item.h2, item.temp, item.humidity, item.pressure].join(",");
    return [
      headers,
      ...historyReadings.map((item) => row("Leitura", item)),
      ...historyAverages.map((item) => row("Média móvel", item)),
    ].join("\n");
  }, [historyReadings, historyAverages]);

  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;

  function toggleTheme() {
    setTheme((currentTheme) => {
      const nextTheme = currentTheme === "dark" ? "light" : "dark";
      localStorage.setItem("gasmix-theme", nextTheme);
      return nextTheme;
    });
  }

  return <div className={`app-shell ${theme === "light" ? "light" : ""}`}>
    <aside className="sidebar">
      <div className="sidebar-brand"><div className="brand-mark small">MG</div><div><span>Monitoramento de Gás</span></div></div>
      <nav className="nav">
        <p className="nav-heading">PAINEL</p>
        <button className="nav-item active"><span>◈</span> Visão geral</button>
        <p className="nav-heading equipment">EQUIPAMENTO</p>
        <div className={`connection-status ${arduinoStatus.connected ? "online" : ""}`}><span className="status-dot" /><div><strong>{arduinoStatus.connected ? "Arduino conectado" : "Arduino não detectado"}</strong><small>{arduinoStatus.error || (arduinoStatus.last_reading ? `Última leitura: ${new Date(arduinoStatus.last_reading).toLocaleTimeString("pt-BR")}` : "Aguardando leitura")}</small></div></div>
        <label className="sidebar-setting">Porta do Arduino<select value={selectedPort} onChange={(event) => setSelectedPort(event.target.value)} disabled={connected}><option value="">Selecione uma porta</option>{availablePorts.map((port) => <option key={port.device} value={port.device}>{port.device} - {port.description}</option>)}</select><button className="button secondary" type="button" onClick={loadAvailablePorts} disabled={connected}>Atualizar portas</button></label>
        <label className="sidebar-setting">Janela de média<select value={interval} onChange={(event) => setIntervalValue(event.target.value)}><option value="1">1 minuto</option><option value="5">5 minutos</option><option value="10">10 minutos</option></select></label>
        {connectionError && <p className="form-error">{connectionError}</p>}
        <button className="button primary sidebar-connect" onClick={toggleArduinoConnection}>{connected ? "Desconectar Arduino" : "Conectar Arduino"} <span>{connected ? "×" : "→"}</span></button>
      </nav>
      <div className="sidebar-bottom"><button className="nav-item logout" onClick={() => setAuthenticated(false)}><span>↪</span> Sair</button></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><p className="eyebrow">VISÃO GERAL</p><h1>Monitor do misturador</h1></div><div className="top-actions"><button className="theme-toggle" onClick={toggleTheme} aria-label={`Ativar modo ${theme === "dark" ? "claro" : "escuro"}`} title={`Modo ${theme === "dark" ? "claro" : "escuro"}`}>{theme === "dark" ? "☀" : "☾"}</button></div></header>
      <section className="section-heading"><div><h2>Leituras atuais</h2><p>Última atualização hoje, {lastUpdated}</p></div><span className="sample-count">{readings.length} amostras coletadas</span></section>
      <div className="metrics-grid">
        <Metric tone="cyan" icon="O₂" label="Concentração de oxigênio" value={current ? `${(current.o2 / 1e6).toFixed(3)} ×10⁶ ppm` : "--"} detail={`${delta("o2", 0)} ppm desde a última leitura`} />
        <Metric tone="orange" icon="H₂" label="Concentração de hidrogênio" value={current ? `${(current.h2 / 1000).toFixed(1)}k ppm` : "--"} detail={`${delta("h2", 0)} ppm desde a última leitura`} />
        <Metric tone="red" icon="°" label="Temperatura ambiente" value={current ? `${current.temp.toFixed(1)} °C` : "--"} detail={`${delta("temp", 1)} °C desde a última leitura`} />
        <Metric tone="blue" icon="◒" label="Umidade relativa" value={current ? `${current.humidity.toFixed(1)} %` : "--"} detail={`${delta("humidity", 1)} % desde a última leitura`} />
        <Metric tone="purple" icon="⌁" label="Pressão atmosférica" value={current ? `${current.pressure.toFixed(2)} bar` : "--"} detail={`${delta("pressure", 2)} bar desde a última leitura`} />
      </div>
      <div className="tabs">{[["concentration", "Concentração O₂ / H₂"], ["environment", "Condições ambientais"], ["history", "Histórico"]].map(([key, label]) => <button key={key} className={activeTab === key ? "selected" : ""} onClick={() => setActiveTab(key)}>{label}</button>)}</div>
      {activeTab === "concentration" && <section className="charts-grid concentration-charts">
        <article className="panel"><div className="panel-heading"><div><h2>O₂ em tempo real</h2><p>Leituras individuais dos sensores</p></div></div><LineChart data={readings} dataKey="o2" color={gasConfig.O2.color} label="O₂ · tempo real" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>O₂ por média</h2><p>Média móvel de {interval} minuto{interval > 1 ? "s" : ""}</p></div></div><LineChart data={averageReadings.o2} dataKey="o2" color={gasConfig.O2.color} label="O₂ · média" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>H₂ em tempo real</h2><p>Leituras individuais dos sensores</p></div></div><LineChart data={readings} dataKey="h2" color={gasConfig.H2.color} label="H₂ · tempo real" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>H₂ por média</h2><p>Média móvel de {interval} minuto{interval > 1 ? "s" : ""}</p></div></div><LineChart data={averageReadings.h2} dataKey="h2" color={gasConfig.H2.color} label="H₂ · média" /></article>
      </section>}
      {activeTab === "environment" && <section className="charts-grid"><article className="panel"><div className="panel-heading"><div><h2>Temperatura ambiente</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="temp" color="#ff6f72" label="Temperatura" unit="°C" /></article><article className="panel"><div className="panel-heading"><div><h2>Umidade relativa</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="humidity" color="#60a5fa" label="Umidade" unit="%" /></article><article className="panel"><div className="panel-heading"><div><h2>Pressão atmosférica</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="pressure" color="#bb8cff" label="Pressão" unit="bar" /></article></section>}
      {activeTab === "history" && <section className="panel history-panel">
        <div className="panel-heading">
          <div><h2>Histórico de leituras</h2><p>{historyMode === "realtime" ? "Últimas 24 horas, atualizado em tempo real" : "Período filtrado no banco de dados"}</p></div>
          <a className="button secondary" href={`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`} download="leituras-gasmix.csv">↓ Baixar CSV</a>
        </div>
        <div className="history-toolbar">
          <button className={`button ${historyMode === "realtime" ? "primary" : "secondary"}`} type="button" onClick={showRealtimeHistory}>Tempo real</button>
          <form className="history-filter" onSubmit={applyHistoryFilter}>
            <label>Início<input type="datetime-local" value={filterStart} onChange={(event) => setFilterStart(event.target.value)} /></label>
            <label>Fim<input type="datetime-local" value={filterEnd} onChange={(event) => setFilterEnd(event.target.value)} /></label>
            <button className="button primary" type="submit" disabled={historyLoading}>{historyLoading ? "Consultando..." : "Filtrar"}</button>
          </form>
        </div>
        {connectionError && <p className="form-error">{connectionError}</p>}
        <h3 className="history-table-title">Leituras individuais ({historyReadings.length})</h3>
        <div className="table-scroll"><table><thead><tr><th>Horário</th><th>O₂ (ppm)</th><th>H₂ (ppm)</th><th>Temperatura (°C)</th><th>Umidade (%)</th><th>Pressão (bar)</th></tr></thead><tbody>{[...historyReadings].reverse().map((item, index) => <tr key={`${item.dateTime}-${index}`}><td>{item.time}</td><td>{item.o2.toLocaleString("pt-BR")}</td><td>{item.h2.toLocaleString("pt-BR")}</td><td>{item.temp.toFixed(1)}</td><td>{item.humidity.toFixed(1)}</td><td>{item.pressure.toFixed(2)}</td></tr>)}</tbody></table></div>
        <h3 className="history-table-title">Médias móveis ({historyAverages.length})</h3>
        <div className="table-scroll"><table><thead><tr><th>Horário</th><th>O₂ médio (ppm)</th><th>H₂ médio (ppm)</th><th>Temperatura (°C)</th><th>Umidade (%)</th><th>Pressão (bar)</th></tr></thead><tbody>{[...historyAverages].reverse().map((item, index) => <tr key={`average-${item.dateTime}-${index}`}><td>{item.time}</td><td>{item.o2.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</td><td>{item.h2.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</td><td>{item.temp.toFixed(1)}</td><td>{item.humidity.toFixed(1)}</td><td>{item.pressure.toFixed(2)}</td></tr>)}</tbody></table></div>
      </section>}
      <footer>GasMix Monitoring <span>·</span> Dados recebidos do backend</footer>
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
