import React, { useState } from 'react';

export default function Settings({ open, onSave, onStart, onStop, botRunning, connected, onBacktest }) {
  const [risk, setRisk] = useState(2);
  const [mode, setMode] = useState('approval');
  const [maxPos, setMaxPos] = useState(1);

  const handleSave = () => {
    onSave({
      risk_per_trade_pct: risk,
      lot_size_mode: mode,
      max_concurrent_positions: maxPos,
    });
  };

  return (
    <div className={`settings-panel ${open ? '' : 'collapsed'}`}>
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
