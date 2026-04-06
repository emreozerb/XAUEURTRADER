import React from 'react';

export default function TopBar({ connected, account, botStatus, onToggleSettings, onLogout }) {
  return (
    <div className="top-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <button className="toggle-settings" onClick={onToggleSettings}>Settings</button>
        <div className="connection">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          {connected ? 'MT5 Connected' : 'MT5 Disconnected'}
        </div>
      </div>

      <div className="account-info">
        {account ? (
          <>
            <span>Balance: <strong>{account.balance?.toFixed(2)} {account.currency || 'EUR'}</strong></span>
            <span>Equity: <strong>{account.equity?.toFixed(2)}</strong></span>
            <span>Free Margin: <strong>{account.free_margin?.toFixed(2)}</strong></span>
          </>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>Not connected</span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span className={`bot-status-badge ${botStatus}`}>
          {botStatus.replace('_', ' ')}
        </span>
        <button className="btn-logout" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}
