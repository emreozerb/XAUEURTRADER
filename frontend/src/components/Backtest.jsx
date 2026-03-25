import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function Backtest({ onClose, apiUrl, addAlert }) {
  const [period, setPeriod] = useState(3);
  const [balance, setBalance] = useState(10000);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);

  const runBacktest = async () => {
    setRunning(true);
    setResults(null);
    try {
      const res = await fetch(`${apiUrl}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period_months: period, starting_balance: balance }),
      });
      if (!res.ok) {
        const err = await res.json();
        addAlert(err.detail || 'Backtest failed', 'error');
        setRunning(false);
        return;
      }
      const data = await res.json();
      if (data.error) {
        addAlert(data.error, 'error');
      } else {
        setResults(data);
      }
    } catch {
      addAlert('Backtest request failed', 'error');
    }
    setRunning(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Backtest</h2>

        <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>Period</label>
            <select value={period} onChange={e => setPeriod(parseInt(e.target.value))}>
              <option value={1}>1 Month</option>
              <option value={3}>3 Months</option>
              <option value={6}>6 Months</option>
              <option value={12}>12 Months</option>
            </select>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>Starting Balance (EUR)</label>
            <input type="number" value={balance} onChange={e => setBalance(parseFloat(e.target.value))} />
          </div>
        </div>

        <button className="btn btn-connect" onClick={runBacktest} disabled={running}>
          {running ? 'Running...' : 'Run Backtest'}
        </button>

        {results && (
          <>
            <div className="backtest-results">
              <div className="stat">
                <div className="stat-label">Total Trades</div>
                <div className="stat-value">{results.total_trades}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Win Rate</div>
                <div className="stat-value">{results.win_rate}%</div>
              </div>
              <div className="stat">
                <div className="stat-label">Net P&L</div>
                <div className="stat-value" style={{ color: results.net_pnl_eur >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  {results.net_pnl_eur >= 0 ? '+' : ''}{results.net_pnl_eur?.toFixed(2)} EUR
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Net Pips</div>
                <div className="stat-value">{results.net_pips?.toFixed(1)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Max Drawdown</div>
                <div className="stat-value" style={{ color: 'var(--accent-red)' }}>
                  {results.max_drawdown_eur?.toFixed(2)} ({results.max_drawdown_pct}%)
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Profit Factor</div>
                <div className="stat-value">{results.profit_factor}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Best Trade</div>
                <div className="stat-value" style={{ color: 'var(--accent-green)' }}>
                  +{results.best_trade_pips?.toFixed(1)} pips
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Worst Trade</div>
                <div className="stat-value" style={{ color: 'var(--accent-red)' }}>
                  {results.worst_trade_pips?.toFixed(1)} pips
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Final Balance</div>
                <div className="stat-value">{results.final_balance?.toFixed(2)}</div>
              </div>
            </div>

            {results.equity_curve && results.equity_curve.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <h3 style={{ marginBottom: 12 }}>Equity Curve</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={results.equity_curve}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3e" />
                    <XAxis dataKey="time" tick={false} stroke="#6a6a7a" />
                    <YAxis stroke="#6a6a7a" />
                    <Tooltip
                      contentStyle={{ background: '#1a1a2e', border: '1px solid #2a2a3e', color: '#e0e0e0' }}
                      formatter={(val) => [`${val.toFixed(2)} EUR`, 'Balance']}
                    />
                    <Line type="monotone" dataKey="balance" stroke="#4dabf7" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            <p className="disclaimer">
              Backtest results are based on historical data and do not guarantee future performance.
              Market conditions change. Use backtesting to validate strategy logic, not to predict profits.
            </p>
          </>
        )}

        <button className="btn btn-backtest" onClick={onClose} style={{ marginTop: 16 }}>Close</button>
      </div>
    </div>
  );
}
