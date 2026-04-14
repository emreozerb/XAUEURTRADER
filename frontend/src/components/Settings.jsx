import React, { useState } from 'react';

export default function Settings({ open, onSave, onStart, onStop, botRunning, connected, onBacktest }) {
  const [risk, setRisk] = useState(5);

  const handleSave = () => {
    onSave({ risk_per_trade_pct: risk });
  };

  return (
    <div className={`settings-panel ${open ? '' : 'collapsed'}`}>
      <h3>Risk Settings</h3>
      <div className="field">
        <label>Risk Per Trade</label>
        <div className="risk-display">{risk}%</div>
        <input type="range" min="1" max="10" step="0.5" value={risk}
          onChange={e => setRisk(parseFloat(e.target.value))} />
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
