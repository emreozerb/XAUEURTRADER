import React from 'react';

export default function TradeCard({ position }) {
  const dir = position.direction;
  const pnl = position.pnl || 0;
  const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

  const pips = dir === 'buy'
    ? position.current_price - position.entry_price
    : position.entry_price - position.current_price;

  return (
    <div className="trade-card">
      <div className="signal-header">
        <span className={`signal-direction ${dir}`}>{dir.toUpperCase()} POSITION</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          #{position.ticket}
        </span>
      </div>

      <div className={`pnl-live ${pnlClass}`}>
        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} EUR ({pips >= 0 ? '+' : ''}{pips.toFixed(2)} pips)
      </div>

      <div className="signal-details">
        <div className="detail">
          <span className="label">Entry</span>
          <span className="val">{position.entry_price?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Current</span>
          <span className="val">{position.current_price?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Stop Loss</span>
          <span className="val">{position.sl?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Take Profit</span>
          <span className="val">{position.tp?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Lot Size</span>
          <span className="val">{position.lot_size}</span>
        </div>
        <div className="detail">
          <span className="label">Swap</span>
          <span className="val">{position.swap?.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
