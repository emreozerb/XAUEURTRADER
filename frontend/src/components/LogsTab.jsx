import React, { useState, useEffect, useRef } from 'react';

const FILTERS = ['ALL', 'ERROR', 'WARNING', 'INFO'];

function fmtTime(iso) {
  if (!iso) return '--:--:--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-GB', { hour12: false });
  } catch {
    return iso.slice(11, 19) || '--';
  }
}

export default function LogsTab({ logs = [] }) {
  const [filter, setFilter] = useState('ALL');
  const bottomRef = useRef(null);
  const containerRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const visible = filter === 'ALL'
    ? logs
    : logs.filter(l => (l.level || 'info').toUpperCase() === filter);

  // Auto-scroll to bottom when new entries arrive (only if already near bottom)
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs.length, autoScroll]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAutoScroll(nearBottom);
  };

  return (
    <div className="logs-tab">
      <div className="logs-toolbar">
        <div className="logs-filters">
          {FILTERS.map(f => (
            <button
              key={f}
              className={`log-filter-btn ${filter === f ? 'active' : ''} filter-${f.toLowerCase()}`}
              onClick={() => setFilter(f)}
            >
              {f}
              {f !== 'ALL' && (
                <span className="log-filter-count">
                  {logs.filter(l => (l.level || 'info').toUpperCase() === f).length}
                </span>
              )}
            </button>
          ))}
        </div>
        <span className="logs-count">{visible.length} entries</span>
      </div>

      <div className="logs-container" ref={containerRef} onScroll={handleScroll}>
        {visible.length === 0 ? (
          <div className="logs-empty">No log entries yet — start the bot to see live output.</div>
        ) : (
          <table className="log-table">
            <thead>
              <tr>
                <th style={{ width: 80 }}>Time</th>
                <th style={{ width: 72 }}>Level</th>
                <th style={{ width: 90 }}>Source</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((entry, i) => {
                const level = (entry.level || 'info').toLowerCase();
                return (
                  <tr key={i} className={`log-row log-row-${level}`}>
                    <td className="log-time">{fmtTime(entry.timestamp)}</td>
                    <td><span className={`log-level-badge level-${level}`}>{level.toUpperCase()}</span></td>
                    <td><span className="log-source-badge">{entry.source || '—'}</span></td>
                    <td className="log-message">{entry.message}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div ref={bottomRef} />
      </div>

      {!autoScroll && (
        <button
          className="logs-scroll-btn"
          onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }}
        >
          ↓ Jump to latest
        </button>
      )}
    </div>
  );
}
