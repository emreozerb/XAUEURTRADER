import React, { useState, useEffect, useRef, useCallback } from 'react';
import TopBar from './components/TopBar';
import Settings from './components/Settings';
import LiveStatus from './components/LiveStatus';
import ApprovalCard from './components/ApprovalCard';
import TradeCard from './components/TradeCard';
import TradeLog from './components/TradeLog';
import Performance from './components/Performance';
import Backtest from './components/Backtest';
import EmergencyButton from './components/EmergencyButton';

const API = 'http://localhost:8000';

export default function App() {
  const [connected, setConnected] = useState(false);
  const [botStatus, setBotStatus] = useState('stopped');
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [currentPrice, setCurrentPrice] = useState(null);
  const [pendingSignal, setPendingSignal] = useState(null);
  const [trades, setTrades] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [backtestOpen, setBacktestOpen] = useState(false);
  const [trend, setTrend] = useState('unknown');
  const [session, setSession] = useState('');
  const [lastAnalysis, setLastAnalysis] = useState(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [liveWarning, setLiveWarning] = useState(null);
  const wsRef = useRef(null);
  const alertIdRef = useRef(0);

  const addAlert = useCallback((message, level = 'info') => {
    const id = ++alertIdRef.current;
    setAlerts(prev => [...prev.slice(-4), { id, message, level }]);
    setTimeout(() => setAlerts(prev => prev.filter(a => a.id !== id)), 5000);
  }, []);

  // WebSocket connection
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket('ws://localhost:8000/ws');
      ws.onopen = () => { wsRef.current = ws; };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'status') {
          setBotStatus(msg.data.bot_status || botStatus);
          if (msg.data.trend) setTrend(msg.data.trend);
          if (msg.data.session) setSession(msg.data.session);
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
  }, [addAlert, botStatus]);

  // Poll status
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API}/api/status`);
        const data = await res.json();
        setConnected(data.connected);
        setBotStatus(data.bot_status);
        if (data.account) setAccount(data.account);
        if (data.positions) setPositions(data.positions);
        if (data.current_price) setCurrentPrice(data.current_price);
        if (data.pending_signal) setPendingSignal(data.pending_signal);
      } catch { /* backend not ready */ }
    };
    poll();
    const iv = setInterval(poll, 5000);
    return () => clearInterval(iv);
  }, []);

  // Fetch trades & performance
  useEffect(() => {
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
  }, []);

  const handleConnect = async (creds) => {
    try {
      const res = await fetch(`${API}/api/connect`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      });
      const data = await res.json();
      if (data.success) {
        setConnected(true);
        setAccount(data.account_info);
        addAlert('MT5 connected', 'success');
        if (data.is_live) {
          setLiveWarning(true);
        }
      } else {
        addAlert(data.error || 'Connection failed', 'error');
      }
      return data;
    } catch (e) {
      addAlert('Cannot reach backend', 'error');
      return { success: false };
    }
  };

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

  return (
    <div className="app">
      <TopBar connected={connected} account={account} botStatus={botStatus}
        onToggleSettings={() => setSettingsOpen(!settingsOpen)} />

      <div className="main-content">
        <Settings open={settingsOpen} onConnect={handleConnect}
          onSave={handleSaveSettings} onStart={handleStartBot} onStop={handleStopBot}
          botRunning={botStatus !== 'stopped'} connected={connected}
          onBacktest={() => setBacktestOpen(true)} />

        <div className="center-panel">
          <LiveStatus trend={trend} session={session} botStatus={botStatus}
            lastAnalysis={lastAnalysis} currentPrice={currentPrice} />

          {pendingSignal && (
            <ApprovalCard signal={pendingSignal} onApprove={handleApprove} />
          )}

          {positions.map(pos => (
            <TradeCard key={pos.ticket} position={pos} />
          ))}

          <TradeLog trades={trades} />
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
              <button className="btn btn-reject" onClick={() => { setLiveWarning(false); fetch(`${API}/api/disconnect`, { method: 'POST' }); setConnected(false); }}>
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
