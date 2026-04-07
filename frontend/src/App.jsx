import React, { useState, useEffect, useRef, useCallback } from 'react';
import LoginScreen from './components/LoginScreen';
import TopBar from './components/TopBar';
import Settings from './components/Settings';
import LiveStatus from './components/LiveStatus';
import ApprovalCard from './components/ApprovalCard';
import TradeCard from './components/TradeCard';
import TradeLog from './components/TradeLog';
import Performance from './components/Performance';
import Backtest from './components/Backtest';
import EmergencyButton from './components/EmergencyButton';
import ChartView from './components/ChartView';
import EventLog from './components/EventLog';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function App() {
  const [loggedIn, setLoggedIn] = useState(() => {
    return localStorage.getItem('xaueur_logged_in') === 'true';
  });
  const [connected, setConnected] = useState(false);
  const [botStatus, setBotStatus] = useState('stopped');
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [currentPrice, setCurrentPrice] = useState(null);
  const [pendingSignal, setPendingSignal] = useState(null);
  const [trades, setTrades] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [backtestOpen, setBacktestOpen] = useState(false);
  const [trend, setTrend] = useState('unknown');
  const [marketMode, setMarketMode] = useState('');
  const [session, setSession] = useState('');
  const [sessionDisplay, setSessionDisplay] = useState('');
  const [lastAnalysis, setLastAnalysis] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [confirmClose, setConfirmClose] = useState(false);
  const [liveWarning, setLiveWarning] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [events, setEvents] = useState([]);
  const wsRef = useRef(null);
  const alertIdRef = useRef(0);

  const addAlert = useCallback((message, level = 'info') => {
    const id = ++alertIdRef.current;
    setAlerts(prev => [...prev.slice(-4), { id, message, level }]);
    setTimeout(() => setAlerts(prev => prev.filter(a => a.id !== id)), 5000);
  }, []);

  // Handle login
  const handleLogin = async (creds) => {
    try {
      const res = await fetch(`${API}/api/connect`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      });
      const data = await res.json();
      if (data.success) {
        setConnected(true);
        setAccount(data.account_info);
        setLoggedIn(true);
        localStorage.setItem('xaueur_logged_in', 'true');
        addAlert('MT5 connected', 'success');
        if (data.is_live) {
          setLiveWarning(true);
        }
      }
      return data;
    } catch (e) {
      return { success: false, error: 'Cannot reach backend' };
    }
  };

  // Handle logout
  const handleLogout = async () => {
    try {
      await fetch(`${API}/api/bot/stop`, { method: 'POST' });
      await fetch(`${API}/api/disconnect`, { method: 'POST' });
    } catch { /* ignore */ }
    setLoggedIn(false);
    setConnected(false);
    setBotStatus('stopped');
    setAccount(null);
    setPositions([]);
    setPendingSignal(null);
    localStorage.removeItem('xaueur_logged_in');
  };

  // WebSocket connection (only when logged in)
  useEffect(() => {
    if (!loggedIn) return;
    const connect = () => {
      const ws = new WebSocket(`ws://${new URL(API).host}/ws`);
      ws.onopen = () => { wsRef.current = ws; };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'status') {
          setBotStatus(msg.data.bot_status || botStatus);
          if (msg.data.error_message !== undefined) setErrorMessage(msg.data.error_message);
          if (msg.data.trend) setTrend(msg.data.trend);
          if (msg.data.market_mode) setMarketMode(msg.data.market_mode);
          if (msg.data.session) setSession(msg.data.session);
          if (msg.data.session_display) setSessionDisplay(msg.data.session_display);
          if (msg.data.last_analysis) setLastAnalysis(msg.data.last_analysis);
        } else if (msg.type === 'signal') {
          setPendingSignal(msg.data);
        } else if (msg.type === 'trade_update') {
          if (msg.data.positions) setPositions(msg.data.positions);
          if (msg.data.account) setAccount(msg.data.account);
        } else if (msg.type === 'alert') {
          addAlert(msg.data.message, msg.data.level);
        }
      };
      ws.onclose = () => { setTimeout(connect, 3000); };
      ws.onerror = () => { ws.close(); };
    };
    connect();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, [addAlert, botStatus, loggedIn]);

  // Poll status (only when logged in)
  useEffect(() => {
    if (!loggedIn) return;
    const poll = async () => {
      try {
        const res = await fetch(`${API}/api/status`);
        const data = await res.json();
        setConnected(data.connected);
        setBotStatus(data.bot_status);
        if (data.error_message !== undefined) setErrorMessage(data.error_message);
        if (data.account) setAccount(data.account);
        if (data.positions) setPositions(data.positions);
        if (data.current_price) setCurrentPrice(data.current_price);
        if (data.pending_signal) setPendingSignal(data.pending_signal);
      } catch { /* backend not ready */ }
    };
    poll();
    const iv = setInterval(poll, 5000);
    return () => clearInterval(iv);
  }, [loggedIn]);

  // Fetch trades & performance (only when logged in)
  useEffect(() => {
    if (!loggedIn) return;
    const fetchData = async () => {
      try {
        const [tRes, pRes] = await Promise.all([
          fetch(`${API}/api/trades`), fetch(`${API}/api/performance`)
        ]);
        setTrades(await tRes.json());
        setPerformance(await pRes.json());
      } catch { /* */ }
    };
    fetchData();
    const iv = setInterval(fetchData, 15000);
    return () => clearInterval(iv);
  }, [loggedIn]);

  // Fetch event log
  useEffect(() => {
    if (!loggedIn) return;
    const fetchEvents = async () => {
      try {
        const res = await fetch(`${API}/api/events`);
        if (res.ok) setEvents(await res.json());
      } catch { /* backend not ready */ }
    };
    fetchEvents();
    const iv = setInterval(fetchEvents, 10000);
    return () => clearInterval(iv);
  }, [loggedIn]);

  const handleSaveSettings = async (s) => {
    try {
      await fetch(`${API}/api/settings`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(s),
      });
      addAlert('Settings saved', 'success');
    } catch { addAlert('Failed to save settings', 'error'); }
  };

  const handleStartBot = async () => {
    try {
      const res = await fetch(`${API}/api/bot/start`, { method: 'POST' });
      const data = await res.json();
      if (data.success) { setBotStatus('running'); addAlert('Bot started', 'success'); }
      else addAlert(data.detail || 'Failed to start', 'error');
    } catch { addAlert('Failed to start bot', 'error'); }
  };

  const handleStopBot = async () => {
    try {
      await fetch(`${API}/api/bot/stop`, { method: 'POST' });
      setBotStatus('stopped');
    } catch { addAlert('Failed to stop bot', 'error'); }
  };

  const handleApprove = async (approved, manualLot) => {
    try {
      const res = await fetch(`${API}/api/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, manual_lot: manualLot }),
      });
      const data = await res.json();
      setPendingSignal(null);
      if (!approved) addAlert('Signal rejected', 'info');
      else if (data.success) addAlert('Trade executed', 'success');
      else addAlert(data.error || data.detail || 'Trade failed', 'error');
    } catch { addAlert('Approval failed', 'error'); }
  };

  const handleEmergencyClose = async () => {
    try {
      await fetch(`${API}/api/emergency-close`, { method: 'POST' });
      setBotStatus('stopped');
      setPositions([]);
      setConfirmClose(false);
      addAlert('All positions closed', 'error');
    } catch { addAlert('Emergency close failed!', 'error'); }
  };

  // Show login screen if not logged in
  if (!loggedIn) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <TopBar connected={connected} account={account} botStatus={botStatus}
        errorMessage={errorMessage}
        onToggleSettings={() => setSettingsOpen(!settingsOpen)}
        onLogout={handleLogout} />

      <div className="main-content">
        <Settings open={settingsOpen}
          onSave={handleSaveSettings} onStart={handleStartBot} onStop={handleStopBot}
          botRunning={botStatus !== 'stopped'} connected={connected}
          onBacktest={() => setBacktestOpen(true)} />

        <div className="center-panel">
          <div className="tab-bar">
            <button className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}>Dashboard</button>
            <button className={`tab-btn ${activeTab === 'chart' ? 'active' : ''}`}
              onClick={() => setActiveTab('chart')}>Chart</button>
            <button
              className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
              onClick={() => setActiveTab('logs')}
              style={{ position: 'relative' }}
            >
              Logs
              {events.some(e => e.level === 'error') && activeTab !== 'logs' && (
                <span style={{
                  position: 'absolute', top: 6, right: 4,
                  width: 7, height: 7, borderRadius: '50%',
                  background: 'var(--accent-red)', display: 'inline-block',
                }} />
              )}
            </button>
          </div>

          {activeTab === 'dashboard' && (
            <>
              {botStatus === 'error' && errorMessage && (
                <div style={{
                  margin: '12px 16px 0',
                  padding: '12px 16px',
                  borderRadius: 7,
                  background: 'rgba(255,71,87,0.10)',
                  border: '1px solid rgba(255,71,87,0.45)',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                }}>
                  <span style={{ fontSize: 20, lineHeight: 1, color: 'var(--accent-red)', flexShrink: 0 }}>⚠</span>
                  <div>
                    <div style={{ color: 'var(--accent-red)', fontWeight: 700, fontSize: 13, marginBottom: 4 }}>
                      Bot stopped — error
                    </div>
                    <div style={{ color: 'var(--text-primary)', fontSize: 13 }}>{errorMessage}</div>
                    <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 6 }}>
                      Fix the issue, then press <strong>Start Bot</strong> to resume.
                    </div>
                  </div>
                </div>
              )}

              <LiveStatus trend={trend} marketMode={marketMode} session={session}
                sessionDisplay={sessionDisplay} botStatus={botStatus}
                lastAnalysis={lastAnalysis} currentPrice={currentPrice} />

              {pendingSignal && (
                <ApprovalCard signal={pendingSignal} onApprove={handleApprove} />
              )}

              {positions.map(pos => (
                <TradeCard key={pos.ticket} position={pos} />
              ))}

              <TradeLog trades={trades} />
            </>
          )}

          {activeTab === 'chart' && (
            <ChartView />
          )}

          {activeTab === 'logs' && (
            <div style={{ padding: 16 }}>
              <EventLog events={events} />
            </div>
          )}
        </div>
      </div>

      <Performance data={performance} />

      <EmergencyButton onClick={() => setConfirmClose(true)} />

      {/* Alerts */}
      <div className="alerts">
        {alerts.map(a => (
          <div key={a.id} className={`alert ${a.level}`}>{a.message}</div>
        ))}
      </div>

      {/* Emergency confirm */}
      {confirmClose && (
        <div className="confirm-overlay">
          <div className="confirm-dialog">
            <p>Close all open positions immediately?</p>
            <div className="buttons">
              <button className="btn btn-reject" onClick={handleEmergencyClose}>Yes, Close All</button>
              <button className="btn btn-backtest" onClick={() => setConfirmClose(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Live account warning */}
      {liveWarning && (
        <div className="confirm-overlay">
          <div className="confirm-dialog" style={{ borderColor: 'var(--accent-orange)' }}>
            <p style={{ color: 'var(--accent-orange)', fontWeight: 800, fontSize: 20 }}>
              WARNING: LIVE ACCOUNT
            </p>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              You are connected to a LIVE trading account. Real money is at risk.
            </p>
            <div className="buttons">
              <button className="btn btn-approve" onClick={() => setLiveWarning(false)}>
                I understand, continue
              </button>
              <button className="btn btn-reject" onClick={() => { setLiveWarning(false); handleLogout(); }}>
                Disconnect
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Backtest modal */}
      {backtestOpen && (
        <Backtest onClose={() => setBacktestOpen(false)} apiUrl={API} addAlert={addAlert} />
      )}
    </div>
  );
}
