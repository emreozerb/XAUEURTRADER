import React, { useState } from 'react';

export default function ApprovalCard({ signal, onApprove }) {
  const [manualLot, setManualLot] = useState('');
  const dir = signal.direction;
  const confClass = signal.confidence >= 80 ? 'confidence-high' : 'confidence-medium';

  return (
    <div className={`signal-card ${dir}`}>
      <div className="signal-header">
        <span className={`signal-direction ${dir}`}>{dir.toUpperCase()}</span>
        <span className={`confidence-badge ${confClass}`}>{signal.confidence}%</span>
      </div>

      <div className="signal-details">
        <div className="detail">
          <span className="label">Entry Price</span>
          <span className="val">{signal.entry_price?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Stop Loss</span>
          <span className="val">{signal.stop_loss?.toFixed(2)} ({signal.sl_pips?.toFixed(1)} pips)</span>
        </div>
        <div className="detail">
          <span className="label">Take Profit</span>
          <span className="val">{signal.take_profit?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Risk:Reward</span>
          <span className="val">1:{signal.risk_reward?.toFixed(2)}</span>
        </div>
        <div className="detail">
          <span className="label">Lot Size</span>
          <span className="val">{signal.lot_size}</span>
        </div>
        <div className="detail">
          <span className="label">Risk</span>
          <span className="val" style={{ color: 'var(--accent-orange)' }}>
            {signal.risk_eur?.toFixed(2)} EUR ({signal.risk_pct?.toFixed(1)}%)
          </span>
        </div>
      </div>

      <div className="reasoning">{signal.reasoning}</div>

      <div style={{ marginBottom: 12 }}>
        <div className="field">
          <label>Manual Lot Override (optional)</label>
          <input type="number" step="0.01" value={manualLot}
            onChange={e => setManualLot(e.target.value)} placeholder={signal.lot_size} />
        </div>
      </div>

      <div className="approval-buttons">
        <button className="btn btn-approve"
          onClick={() => onApprove(true, manualLot ? parseFloat(manualLot) : null)}>
          Approve
        </button>
        <button className="btn btn-reject" onClick={() => onApprove(false)}>
          Reject
        </button>
      </div>
    </div>
  );
}
