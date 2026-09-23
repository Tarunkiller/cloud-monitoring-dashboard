import { useEffect, useRef, useState } from 'react';
import { Chart } from 'chart.js/auto';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8123/api';
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8123/ws/live';

function pctColor(value) {
  if (value >= 90) return '#ff5d6c';
  if (value >= 75) return '#f5b942';
  return '#3ddc97';
}

async function fetchSnapshot(token) {
  try {
    const headers = { Authorization: `Bearer ${token}` };
    const [serversRes, alertsRes, logsRes, summaryRes] = await Promise.all([
      fetch(`${API}/metrics/latest`, { headers }),
      fetch(`${API}/alerts?limit=8`, { headers }),
      fetch(`${API}/logs?limit=10`, { headers }),
      fetch(`${API}/logs/summary`, { headers }),
    ]);

    const [servers, alerts, logs, summary] = await Promise.all([
      serversRes.json(),
      alertsRes.json(),
      logsRes.json(),
      summaryRes.json(),
    ]);

    return {
      servers,
      alerts,
      logs,
      summary,
      lastUpdate: new Date(),
    };
  } catch (error) {
    console.error('Failed to fetch initial dashboard data:', error);
    return null;
  }
}

function Login({ onLogin }) {
  const [username, setUsername] = useState('viewer');
  const [password, setPassword] = useState('viewer123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Login failed');
      onLogin(result);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <form className="card login-card" onSubmit={submit}>
        <h1>Cloud Monitoring</h1>
        <p className="sub">Sign in to access live operations data.</p>
        <label>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        </label>
        {error && <div className="auth-error">{error}</div>}
        <button type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
        <small className="sub">Demo accounts: viewer/viewer123 · operator/operator123 · admin/admin123</small>
      </form>
    </main>
  );
}

function ServerHealth({ servers }) {
  return (
    <div className="card">
      <h2>Fleet Health</h2>
      {servers.length === 0 ? (
        <div className="empty">Waiting for fleet telemetry…</div>
      ) : (
        servers.map((server) => (
          <div className="metric-row" key={server.server_id || server.id}>
            <div>
              <div className="server-name">{server.server_name}</div>
              <div className="server-role">
                CPU {server.cpu_percent}% · Memory {server.memory_percent}% · Disk {server.disk_percent}%
              </div>
            </div>
            <div className="bar-wrap">
              <div
                className="bar"
                style={{ width: `${server.cpu_percent}%`, background: pctColor(server.cpu_percent) }}
              />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function AlertsPanel({ alerts }) {
  return (
    <div className="card">
      <h2>Alerts &amp; Automation</h2>
      {alerts.length === 0 ? (
        <div className="empty">No threshold breaches detected.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Server</th>
              <th>Metric</th>
              <th>Severity</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {alerts.slice(0, 8).map((alert) => (
              <tr key={alert.id}>
                <td>{alert.server_name}</td>
                <td>
                  {alert.metric.replace('_percent', '')} {alert.value}%
                </td>
                <td>
                  <span className={`badge ${alert.severity}`}>{alert.severity}</span>
                </td>
                <td>{alert.remediation_action ? `✓ ${alert.remediation_action}` : 'monitoring'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function LogSummary({ summary }) {
  if (!summary) {
    return (
      <div className="card">
        <h2>Log Validation</h2>
        <div className="empty">Loading validation results…</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Log Validation</h2>
      <div className="metric-row">
        <span>Total ingested</span>
        <strong>{summary.total_logs}</strong>
      </div>
      <div className="metric-row">
        <span>Flagged invalid</span>
        <strong style={{ color: '#ff5d6c' }}>{summary.flagged_invalid}</strong>
      </div>
      <div className="metric-row">
        <span>Valid rate</span>
        <strong style={{ color: '#3ddc97' }}>{summary.valid_rate_percent}%</strong>
      </div>
    </div>
  );
}

function OperationsPanel({ role, token }) {
  const [message, setMessage] = useState('');
  const [running, setRunning] = useState('');
  const canOperate = role === 'operator' || role === 'admin';
  const actions = role === 'admin'
    ? [
        ['clear_cache', 'Clear cache'],
        ['restart_service', 'Restart service'],
        ['rotate_logs', 'Rotate logs'],
      ]
    : [['clear_cache', 'Clear cache']];

  if (!canOperate) {
    return (
      <div className="card">
        <h2>Operations</h2>
        <div className="empty">Viewer access is read-only. No operational actions are available.</div>
      </div>
    );
  }

  async function run(action) {
    setRunning(action);
    setMessage('');
    try {
      const response = await fetch(`${API}/operations/${action}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Operation failed');
      setMessage(`${result.result} (${result.target})`);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setRunning('');
    }
  }

  return (
    <div className="card">
      <h2>Operations · {role}</h2>
      <div className="operation-actions">
        {actions.map(([action, label]) => (
          <button key={action} type="button" disabled={Boolean(running)} onClick={() => run(action)}>
            {running === action ? 'Running…' : label}
          </button>
        ))}
      </div>
      {message && <div className="operation-result">{message}</div>}
    </div>
  );
}

function LogsTable({ logs }) {
  return (
    <div className="card full">
      <h2>Recent Logs</h2>
      {logs.length === 0 ? (
        <div className="empty">No recent log data to display.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Server</th>
              <th>Level</th>
              <th>Message</th>
              <th>Validation</th>
            </tr>
          </thead>
          <tbody>
            {logs.slice(0, 10).map((log) => (
              <tr key={log.id}>
                <td>{new Date(log.timestamp).toLocaleTimeString()}</td>
                <td>{log.server_name}</td>
                <td>
                  <span className={`badge ${log.level}`}>{log.level}</span>
                </td>
                <td>{log.message}</td>
                <td>
                  <span className={`badge ${log.is_valid ? 'valid' : 'invalid'}`}>
                    {log.is_valid ? 'valid' : log.validation_note || 'invalid'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function CpuChart({ servers }) {
  const chartRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const chartInstance = new Chart(canvasRef.current, {
      type: 'bar',
      data: {
        labels: servers.map((server) => server.server_name),
        datasets: [
          {
            label: 'CPU %',
            data: servers.map((server) => server.cpu_percent),
            backgroundColor: servers.map((server) => pctColor(server.cpu_percent)),
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: { color: '#8ea0c6' },
            grid: { color: '#1c2745' },
          },
          x: {
            ticks: { color: '#8ea0c6' },
            grid: { display: false },
          },
        },
      },
    });

    chartRef.current = chartInstance;

    return () => chartInstance.destroy();
  }, [servers]);

  return (
    <div className="card">
      <h2>CPU by Node</h2>
      <div className="chart-wrap">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(() => {
    const saved = sessionStorage.getItem('monitoring_session');
    return saved ? JSON.parse(saved) : null;
  });
  const [servers, setServers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [logs, setLogs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const socketRef = useRef(null);
  const reconnectRef = useRef(null);

  useEffect(() => {
    if (!session) return undefined;

    const loadInitialSnapshot = async () => {
      const snapshot = await fetchSnapshot(session.access_token);
      if (!snapshot) return;

      setServers(snapshot.servers);
      setAlerts(snapshot.alerts);
      setLogs(snapshot.logs);
      setSummary(snapshot.summary);
      setLastUpdate(snapshot.lastUpdate);
    };

    loadInitialSnapshot();

    const connect = () => {
      const socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(session.access_token)}`);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
        if (reconnectRef.current) {
          clearTimeout(reconnectRef.current);
          reconnectRef.current = null;
        }
      };

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type !== 'snapshot') return;

        setServers(payload.servers || []);
        setAlerts(payload.alerts || []);
        setLogs(payload.logs || []);
        setSummary(payload.log_summary || null);
        setLastUpdate(new Date());
      };

      socket.onclose = () => {
        setConnected(false);
        reconnectRef.current = setTimeout(connect, 2000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      if (socketRef.current) socketRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [session]);

  if (!session) {
    return (
      <Login
        onLogin={(result) => {
          sessionStorage.setItem('monitoring_session', JSON.stringify(result));
          setSession(result);
        }}
      />
    );
  }

  return (
    <>
      <header>
        <div>
          <h1>Cloud Monitoring &amp; Automation Dashboard</h1>
          <div className="sub">
            Real-time fleet metrics over WebSocket · alert automation · log validation
            {lastUpdate && <> · updated {lastUpdate.toLocaleTimeString()}</>}
          </div>
        </div>
        <span className={`pill ${connected ? 'ok' : 'down'}`}>
          {connected ? '● Live — WebSocket connected' : '○ Reconnecting…'}
        </span>
        <div className="user-menu">
          <span>{session.user.username} · {session.user.role}</span>
          <button type="button" onClick={() => { sessionStorage.removeItem('monitoring_session'); setSession(null); }}>
            Sign out
          </button>
        </div>
      </header>

      <main>
        <ServerHealth servers={servers} />
        <CpuChart servers={servers} />
        <LogSummary summary={summary} />
        <OperationsPanel role={session.user.role} token={session.access_token} />
        <AlertsPanel alerts={alerts} />
        <LogsTable logs={logs} />
      </main>
    </>
  );
}
