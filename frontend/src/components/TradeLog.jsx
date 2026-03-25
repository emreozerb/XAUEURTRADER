import React, { useState } from 'react';

export default function TradeLog({ trades }) {
  const [expandedId, setExpandedId] = useState(null);

  if (!trades || trades.length === 0) {
    return (
      <div className="trade-log">
        <h3>Trade History</h3>
        <p style={{ color: 'var(--text-muted)', padding: 20 }}>No trades yet.</p>
      </div>
    );
  }

  return (
    <div className="trade-log">
      <h3>Trade History</h3>
      <table className="trade-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Dir</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>SL</th>
            <th>Lot</th>
            <th>Pips</th>
            <th>P&L</th>
            <th>Conf</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map(t => (
            <React.Fragment key={t.id}>
              <tr className={t.result === 'win' ? 'win' : t.result === 'loss' ? 'loss' : ''}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}>
                <td>{t.entry_timestamp ? new Date(t.entry_timestamp).toLocaleDateString() : '—'}</td>
                <td className={t.direction === 'buy' ? 'direction-buy' : 'direction-sell'}>
                  {t.direction?.toUpperCase()}
                </td>
                <td>{t.entry_price?.toFixed(2)}</td>
                <td>{t.exit_price?.toFixed(2) || '—'}</td>
                <td>{t.stop_loss?.toFixed(2)}</td>
                <td>{t.lot_size}</td>
                <td className={t.pips >= 0 ? 'pnl-positive' : 'pnl-negative'}>
                  {t.pips != null ? (t.pips >= 0 ? '+' : '') + t.pips.toFixed(1) : '—'}
                </td>
                <td className={t.pnl_eur >= 0 ? 'pnl-positive' : 'pnl-negative'}>
                  {t.pnl_eur != null ? (t.pnl_eur >= 0 ? '+' : '') + t.pnl_eur.toFixed(2) : '—'}
                </td>
                <td>{t.ai_confidence || '—'}%</td>
                <td>{t.exit_reason || '—'}</td>
              </tr>
              {expandedId === t.id && t.ai_reasoning && (
                <tr>
                  <td colSpan={10} style={{ background: 'var(--bg-primary)', padding: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
                    {t.ai_reasoning}
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
