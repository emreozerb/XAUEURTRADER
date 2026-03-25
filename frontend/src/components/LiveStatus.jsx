import React from 'react';

const SESSION_LABELS = {
  london: 'London',
  london_newyork: 'London / New York',
  new_york: 'New York',
  asian: 'Asian',
};

const STATUS_LABELS = {
  stopped: 'Bot stopped',
  running: 'Watching for signals',
  analyzing: 'Analyzing H1 close...',
  awaiting_approval: 'Signal detected — awaiting approval',
  paused: 'Bot paused',
};

export default function LiveStatus({ trend, session, botStatus, lastAnalysis, currentPrice }) {
  const trendClass = trend === 'uptrend' ? 'trend-up' : trend === 'downtrend' ? 'trend-down' : 'trend-sideways';
  const trendIcon = trend === 'uptrend' ? '▲' : trend === 'downtrend' ? '▼' : '◆';
  const trendLabel = trend === 'uptrend' ? 'UPTREND' : trend === 'downtrend' ? 'DOWNTREND' : trend === 'sideways' ? 'SIDEWAYS' : 'UNKNOWN';

  return (
    <div className="live-status">
      <div className="status-card">
        <div className="label">4H Trend</div>
        <div className={`value ${trendClass}`}>
          {trendIcon} {trendLabel}
        </div>
      </div>

      <div className="status-card">
        <div className="label">Session</div>
        <div className="value" style={{ fontSize: 20 }}>
          {SESSION_LABELS[session] || session || '—'}
        </div>
      </div>

      <div className="status-card">
        <div className="label">Price</div>
        <div className="value" style={{ fontSize: 22 }}>
          {currentPrice ? currentPrice.bid?.toFixed(2) : '—'}
          {currentPrice && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
              spread: {currentPrice.spread?.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      <div className="status-card" style={{ gridColumn: '1 / -1' }}>
        <div className="label">AI Status</div>
        <div className="value" style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
          {STATUS_LABELS[botStatus] || botStatus}
          {lastAnalysis && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 12 }}>
              Last analysis: {new Date(lastAnalysis).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
