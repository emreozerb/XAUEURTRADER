import React, { useState } from 'react';

export default function LoginScreen({ onLogin }) {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [server, setServer] = useState('');
  const [symbol, setSymbol] = useState('XAUEUR');
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!account || !password || !server) {
      setError('All fields are required');
      return;
    }
    setError('');
    setConnecting(true);
    const result = await onLogin({ account: parseInt(account), password, server, symbol });
    setConnecting(false);
    if (!result.success) {
      setError(result.error || 'Connection failed. Is MT5 running?');
    }
  };

  return (
    <div className="login-overlay">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">XAUEUR</div>
          <div className="login-subtitle">AI Trading Bot</div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>MT5 Account Number</label>
            <input type="text" value={account} onChange={e => setAccount(e.target.value)}
              placeholder="12345678" autoFocus />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <div className="field">
            <label>Server</label>
            <input type="text" value={server} onChange={e => setServer(e.target.value)}
              placeholder="BrokerName-Demo" />
          </div>
          <div className="field">
            <label>Symbol Name</label>
            <input type="text" value={symbol} onChange={e => setSymbol(e.target.value)} />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button className="btn btn-start login-btn" type="submit" disabled={connecting}>
            {connecting ? 'Connecting...' : 'Connect to MT5'}
          </button>
        </form>
      </div>
    </div>
  );
}
