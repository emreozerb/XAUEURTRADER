import React from 'react';

export default function Performance({ data }) {
  if (!data) return null;

  const pnlClass = data.net_pnl_eur >= 0 ? 'pnl-positive' : 'pnl-negative';

  return (
    <div className="performance-footer">
      <div className="perf-item">
        <div className="perf-label">Total Trades</div>
        <div className="perf-value">{data.total_trades}</div>
      </div>
      <div className="perf-item">
        <div className="perf-label">Win Rate</div>
        <div className="perf-value">{data.win_rate}%</div>
      </div>
      <div className="perf-item">
        <div className="perf-label">Net P&L</div>
        <div className={`perf-value ${pnlClass}`}>
          {data.net_pnl_eur >= 0 ? '+' : ''}{data.net_pnl_eur?.toFixed(2)} EUR
        </div>
      </div>
      <div className="perf-item">
        <div className="perf-label">Avg R:R</div>
        <div className="perf-value">{data.avg_rr?.toFixed(2) || '—'}</div>
      </div>
      <div className="perf-item">
        <div className="perf-label">Max Drawdown</div>
        <div className="perf-value" style={{ color: 'var(--accent-red)' }}>
          {data.max_drawdown_eur?.toFixed(2)} EUR ({data.max_drawdown_pct}%)
        </div>
      </div>
    </div>
  );
}
