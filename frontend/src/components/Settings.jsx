import React, { useState } from 'react';

export default function Settings({ open, onConnect, onSave, onStart, onStop, botRunning, connected, onBacktest }) {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [server, setServer] = useState('');
  const [symbol, setSymbol] = useState('XAUEUR');
  const [anthropicKey, setAnthropicKey] = useState('');
  const [finnhubKey, setFinnhubKey] = useState('');
  const [risk, setRisk] = useState(2);
  const [mode, setMode] = useState('approval');
  const [maxPos, setMaxPos] = useState(1);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    setConnecting(true);
    await onConnect({ account: parseInt(account), password, server, symbol });
    setConnecting(false);
  };

  const handleSave = () => {
    onSave({
      risk_per_trade_pct: risk,
      lot_size_mode: mode,
      max_concurrent_positions: maxPos,
      anthropic_api_key: anthropicKey,
      finnhub_api_key: finnhubKey,
    });
  };

  return (
    <div className={`settings-panel ${open ? '' : 'collapsed'}`}>
      <h3>MT5 Connection</h3>
      <div className="field">
        <label>Account Number</label>
        <input type="text" value={account} onChange={e => setAccount(e.target.value)} placeholder="12345678" />
      </div>
      <div className="field">
        <label>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      </div>
      <div className="field">
        <label>Server</label>
        <input type="text" value={server} onChange={e => setServer(e.target.value)} placeholder="BrokerName-Demo" />
      </div>
      <div className="field">
        <label>Symbol Name</label>
        <input type="text" value={symbol} onChange={e => setSymbol(e.target.value)} />
      </div>
      <button className="btn btn-connect" onClick={handleConnect} disabled={connecting || connected}>
        {connecting ? 'Connecting...' : connected ? 'Connected' : 'Connect to MT5'}
      </button>

      <h3>API Keys</h3>
      <div className="field">
        <label>Anthropic API Key</label>
        <input type="password" value={anthropicKey} onChange={e => setAnthropicKey(e.target.value)} placeholder="sk-ant-..." />
      </div>
      <div className="field">
        <label>Finnhub API Key</label>
        <input type="text" value={finnhubKey} onChange={e => setFinnhubKey(e.target.value)} />
      </div>

      <h3>Risk Settings</h3>
      <div className="field">
        <label>Risk Per Trade</label>
        <div className="risk-display">{risk}%</div>
        <input type="range" min="1" max="5" step="0.5" value={risk}
          onChange={e => setRisk(parseFloat(e.target.value))} />
      </div>
      <div className="field">
        <label>Lot Size Mode</label>
        <select value={mode} onChange={e => setMode(e.target.value)}>
          <option value="auto">Auto</option>
          <option value="approval">Approval (Recommended)</option>
          <option value="manual">Manual</option>
        </select>
      </div>
      <div className="field">
        <label>Max Concurrent Positions</label>
        <select value={maxPos} onChange={e => setMaxPos(parseInt(e.target.value))}>
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
        </select>
      </div>

      <button className="btn btn-connect" onClick={handleSave}>Save Settings</button>

      <div style={{ marginTop: 24 }}>
        {!botRunning ? (
          <button className="btn btn-start" onClick={onStart} disabled={!connected}>
            Start Bot
          </button>
        ) : (
          <button className="btn btn-stop" onClick={onStop}>Stop Bot</button>
        )}
      </div>

      <button className="btn btn-backtest" onClick={onBacktest} disabled={!connected}
        style={{ marginTop: 16 }}>
        Run Backtest
      </button>
    </div>
  );
}
