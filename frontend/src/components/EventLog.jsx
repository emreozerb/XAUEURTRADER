import React, { useState } from 'react';

const LEVEL_COLORS = {
  error:   { color: 'var(--accent-red)',    bg: 'rgba(255,71,87,0.10)'  },
  warning: { color: 'var(--accent-orange)', bg: 'rgba(255,165,2,0.10)'  },
  success: { color: 'var(--accent-green)',  bg: 'rgba(0,210,106,0.08)'  },
  info:    { color: 'var(--accent-blue)',   bg: 'rgba(77,171,247,0.08)' },
};

const SOURCE_LABELS = {
  mt5:       'MT5',
  bot:       'Bot',
  trade:     'Trade',
  signal:    'Signal',
  risk:      'Risk',
  ai:        'AI',
  approval:  'Approval',
  emergency: 'Emergency',
  system:    'System',
};

const LEVEL_ICONS = { error: '✕', warning: '⚠', success: '✓', info: 'ℹ' };

export default function EventLog({ events }) {
  const [filter, setFilter] = useState('all');

  const filtered = filter === 'all'
    ? events
    : events.filter(e => e.level === filter);

  return (
    <div className="trade-log" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Event Log</h3>
        <div style={{ display: 'flex', gap: 6 }}>
          {['all', 'error', 'warning', 'success', 'info'].map(lvl => (
            <button
              key={lvl}
              onClick={() => setFilter(lvl)}
              style={{
                padding: '3px 10px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                background: filter === lvl
                  ? (LEVEL_COLORS[lvl]?.bg || 'var(--bg-tertiary)')
                  : 'transparent',
                color: filter === lvl
                  ? (LEVEL_COLORS[lvl]?.color || 'var(--text-primary)')
                  : 'var(--text-muted)',
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', padding: '16px 0' }}>No events yet.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 400, overflowY: 'auto' }}>
          {filtered.map(evt => {
            const style = LEVEL_COLORS[evt.level] || LEVEL_COLORS.info;
            const icon  = LEVEL_ICONS[evt.level] || 'ℹ';
            const ts    = evt.timestamp
              ? new Date(evt.timestamp).toLocaleString(undefined, {
                  month: 'short', day: '2-digit',
                  hour: '2-digit', minute: '2-digit', second: '2-digit',
                })
              : '—';
            const sourceLabel = SOURCE_LABELS[evt.source] || evt.source || '';

            return (
              <div
                key={evt.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '22px 140px 70px 1fr',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 10px',
                  borderRadius: 5,
                  background: style.bg,
                  border: `1px solid ${style.color}22`,
                  fontSize: 12,
                }}
              >
                <span style={{ color: style.color, fontWeight: 700, fontSize: 13 }}>{icon}</span>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: 11 }}>{ts}</span>
                <span style={{
                  color: style.color,
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  background: `${style.color}22`,
                  borderRadius: 3,
                  padding: '1px 5px',
                  textAlign: 'center',
                }}>
                  {sourceLabel}
                </span>
                <span style={{ color: 'var(--text-primary)' }}>{evt.message}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
