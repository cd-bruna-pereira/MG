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
          return <circle key={item.time} cx={x} cy={y} r="4" fill="#101c2d" stroke={color} strokeWidth="2" />;
        })}
      </svg>
      <div className="chart-labels">{data.map((item) => <span key={item.time}>{item.time}</span>)}</div>
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
  const [activeTab, setActiveTab] = useState("concentration");
  const [interval, setIntervalValue] = useState(1);
  const [readings, setReadings] = useState([]);
  const [lastUpdated, setLastUpdated] = useState("--");

  useEffect(() => {
    if (!connected) return undefined;
    const socketUrl = `${apiBase.replace(/^http/, "ws")}/ws`;
    const socket = new WebSocket(socketUrl);
    socket.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      const date = new Date(payload.date_time);
      const next = {
        time: date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
        o2: payload.concentracao_o2,
        h2: payload.concentracao_h2,
        temp: payload.temperatura,
        humidity: payload.umidade,
        pressure: payload.pressao,
      };
      setReadings((items) => [...items.slice(-7), next]);
      setLastUpdated(date.toLocaleTimeString("pt-BR"));
    };
    socket.onerror = () => setConnected(false);
    return () => socket.close();
  }, [apiBase, connected]);

  useEffect(() => {
    if (!connected) return undefined;
    const end = new Date();
    const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
    const params = new URLSearchParams({ inicio: start.toISOString(), fim: end.toISOString() });
    fetch(`${apiBase}/api/leituras?${params}`)
      .then((response) => {
        if (!response.ok) throw new Error("Não foi possível consultar o histórico.");
        return response.json();
      })
      .then((items) => {
        if (!items.length) return;
        setReadings(items.slice(-8).map((item) => {
          const date = new Date(item.date_time);
          return {
            time: date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
            o2: item.concentracao_o2,
            h2: item.concentracao_h2,
            temp: item.temperatura,
            humidity: item.umidade,
            pressure: item.pressao,
          };
        }));
      })
      .catch(() => setConnected(false));
    return undefined;
  }, [apiBase, connected]);

  const current = readings[readings.length - 1];
  const previous = readings[readings.length - 2];
  const averageReadings = useMemo(() => ({
    o2: movingAverage(readings, "o2"),
    h2: movingAverage(readings, "h2"),
  }), [readings]);
  const delta = (key, digits = 0) => `${current[key] - previous[key] >= 0 ? "+" : ""}${(current[key] - previous[key]).toFixed(digits)}`;
  const csv = useMemo(() => [
    "Timestamp,O2_Conc,H2_Conc,Ambient_Temp,Ambient_Hum,Ambient_Pressure",
    ...readings.map((item) => `${item.time},${item.o2},${item.h2},${item.temp.toFixed(1)},${item.humidity.toFixed(1)},${item.pressure.toFixed(2)}`),
  ].join("\n"), [readings]);

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
        <div className={`connection-status ${connected ? "online" : ""}`}><span className="status-dot" /><div><strong>{connected ? "Sistema conectado" : "Sistema offline"}</strong><small>{connected ? "Arduino em tempo real" : "Aguardando conexão"}</small></div></div>
        <label className="sidebar-setting">Janela de média<select value={interval} onChange={(event) => setIntervalValue(event.target.value)}><option value="1">1 minuto</option><option value="5">5 minutos</option><option value="10">10 minutos</option></select></label>
        <button className="button primary sidebar-connect" onClick={() => setConnected((value) => !value)}>{connected ? "Desconectar Arduino" : "Conectar Arduino"} <span>{connected ? "×" : "→"}</span></button>
      </nav>
      <div className="sidebar-bottom"><button className="nav-item logout" onClick={() => setAuthenticated(false)}><span>↪</span> Sair</button></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div><p className="eyebrow">VISÃO GERAL</p><h1>Monitor do misturador</h1></div><div className="top-actions"><button className="theme-toggle" onClick={toggleTheme} aria-label={`Ativar modo ${theme === "dark" ? "claro" : "escuro"}`} title={`Modo ${theme === "dark" ? "claro" : "escuro"}`}>{theme === "dark" ? "☀" : "☾"}</button></div></header>
      <section className="section-heading"><div><h2>Leituras atuais</h2><p>Última atualização hoje, {lastUpdated}</p></div><span className="sample-count">{readings.length} amostras coletadas</span></section>
      <div className="metrics-grid">
        <Metric tone="cyan" icon="O₂" label="Concentração de oxigênio" value={`${(current.o2 / 1e6).toFixed(3)} ×10⁶ ppm`} detail={`${delta("o2", 0)} ppm desde a última leitura`} />
        <Metric tone="orange" icon="H₂" label="Concentração de hidrogênio" value={`${(current.h2 / 1000).toFixed(1)}k ppm`} detail={`${delta("h2", 0)} ppm desde a última leitura`} />
        <Metric tone="red" icon="°" label="Temperatura ambiente" value={`${current.temp.toFixed(1)} °C`} detail={`${delta("temp", 1)} °C desde a última leitura`} />
        <Metric tone="blue" icon="◒" label="Umidade relativa" value={`${current.humidity.toFixed(1)} %`} detail={`${delta("humidity", 1)} % desde a última leitura`} />
        <Metric tone="purple" icon="⌁" label="Pressão atmosférica" value={`${current.pressure.toFixed(2)} bar`} detail={`${delta("pressure", 2)} bar desde a última leitura`} />
      </div>
      <div className="tabs">{[["concentration", "Concentração O₂ / H₂"], ["environment", "Condições ambientais"], ["history", "Histórico"]].map(([key, label]) => <button key={key} className={activeTab === key ? "selected" : ""} onClick={() => setActiveTab(key)}>{label}</button>)}</div>
      {activeTab === "concentration" && <section className="charts-grid concentration-charts">
        <article className="panel"><div className="panel-heading"><div><h2>O₂ em tempo real</h2><p>Leituras individuais dos sensores</p></div></div><LineChart data={readings} dataKey="o2" color={gasConfig.O2.color} label="O₂ · tempo real" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>O₂ por média</h2><p>Média móvel de {interval} minuto{interval > 1 ? "s" : ""}</p></div></div><LineChart data={averageReadings.o2} dataKey="o2" color={gasConfig.O2.color} label="O₂ · média" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>H₂ em tempo real</h2><p>Leituras individuais dos sensores</p></div></div><LineChart data={readings} dataKey="h2" color={gasConfig.H2.color} label="H₂ · tempo real" /></article>
        <article className="panel"><div className="panel-heading"><div><h2>H₂ por média</h2><p>Média móvel de {interval} minuto{interval > 1 ? "s" : ""}</p></div></div><LineChart data={averageReadings.h2} dataKey="h2" color={gasConfig.H2.color} label="H₂ · média" /></article>
      </section>}
      {activeTab === "environment" && <section className="charts-grid"><article className="panel"><div className="panel-heading"><div><h2>Temperatura ambiente</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="temp" color="#ff6f72" label="Temperatura" unit="°C" /></article><article className="panel"><div className="panel-heading"><div><h2>Umidade relativa</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="humidity" color="#60a5fa" label="Umidade" unit="%" /></article><article className="panel"><div className="panel-heading"><div><h2>Pressão atmosférica</h2><p>Leituras brutas em tempo real</p></div></div><LineChart data={readings} dataKey="pressure" color="#bb8cff" label="Pressão" unit="bar" /></article></section>}
      {activeTab === "history" && <section className="panel history-panel"><div className="panel-heading"><div><h2>Leituras em tempo real</h2><p>Dados recebidos do sensor</p></div><a className="button secondary" href={`data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`} download="leituras-gasmix.csv">↓ Baixar CSV</a></div><div className="table-scroll"><table><thead><tr><th>Horário</th><th>O₂ (ppm)</th><th>H₂ (ppm)</th><th>Temperatura (°C)</th><th>Umidade (%)</th><th>Pressão (bar)</th></tr></thead><tbody>{[...readings].reverse().map((item) => <tr key={`${item.time}-${item.o2}`}><td>{item.time}</td><td>{item.o2.toLocaleString("pt-BR")}</td><td>{item.h2.toLocaleString("pt-BR")}</td><td>{item.temp.toFixed(1)}</td><td>{item.humidity.toFixed(1)}</td><td>{item.pressure.toFixed(2)}</td></tr>)}</tbody></table></div></section>}
      <footer>GasMix Monitoring <span>·</span> Dados recebidos do backend</footer>
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
