import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function ChartView() {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tradeCount, setTradeCount] = useState(0);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f0f1a' },
        textColor: '#a0a0b0',
      },
      grid: {
        vertLines: { color: '#1a1a2e' },
        horzLines: { color: '#1a1a2e' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: '#2a2a3e',
      },
      timeScale: {
        borderColor: '#2a2a3e',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00d26a',
      downColor: '#ff4757',
      borderDownColor: '#ff4757',
      borderUpColor: '#00d26a',
      wickDownColor: '#ff4757',
      wickUpColor: '#00d26a',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Fetch data
    fetchData(candleSeries, chart);

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  const fetchData = async (candleSeries, chart) => {
    setLoading(true);
    setError('');

    try {
      const [candleRes, tradeRes] = await Promise.all([
        fetch(`${API}/api/candles?timeframe=H1&count=500`),
        fetch(`${API}/api/chart/trades`),
      ]);

      if (!candleRes.ok) {
        throw new Error('Failed to fetch candles');
      }

      const candles = await candleRes.json();
      const trades = tradeRes.ok ? await tradeRes.json() : [];

      if (candles.length === 0) {
        setError('No candle data available');
        setLoading(false);
        return;
      }

      candleSeries.setData(candles);

      // Build trade markers
      const markers = [];
      for (const trade of trades) {
        const isWin = trade.result === 'win';
        const isBuy = trade.direction === 'buy';

        // Entry marker
        if (trade.entry_time) {
          const entryTime = Math.floor(new Date(trade.entry_time).getTime() / 1000);
          markers.push({
            time: entryTime,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: isBuy ? '#00d26a' : '#ff4757',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            text: `${isBuy ? 'BUY' : 'SELL'} ${trade.lot_size || ''}`,
          });
        }

        // Exit marker
        if (trade.exit_time && trade.exit_price) {
          const exitTime = Math.floor(new Date(trade.exit_time).getTime() / 1000);
          const pnlText = trade.pnl_eur != null ? `${trade.pnl_eur > 0 ? '+' : ''}${trade.pnl_eur.toFixed(2)}` : '';
          markers.push({
            time: exitTime,
            position: isBuy ? 'aboveBar' : 'belowBar',
            color: isWin ? '#00d26a' : '#ff4757',
            shape: 'circle',
            text: `EXIT ${pnlText}`,
          });
        }
      }

      // Sort markers by time (required by lightweight-charts)
      markers.sort((a, b) => a.time - b.time);

      if (markers.length > 0) {
        candleSeries.setMarkers(markers);
      }

      setTradeCount(trades.length);
      chart.timeScale().fitContent();
    } catch (e) {
      setError(e.message || 'Failed to load chart data');
    }

    setLoading(false);
  };

  const handleRefresh = () => {
    if (candleSeriesRef.current && chartRef.current) {
      fetchData(candleSeriesRef.current, chartRef.current);
    }
  };

  return (
    <div className="chart-view">
      <div className="chart-header">
        <h3>XAUEUR H1 Chart</h3>
        <div className="chart-controls">
          {tradeCount > 0 && (
            <span className="chart-trade-count">{tradeCount} trades</span>
          )}
          <button className="btn btn-backtest chart-refresh-btn" onClick={handleRefresh}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="chart-loading">Loading chart data...</div>}
      {error && <div className="chart-error">{error}</div>}

      <div ref={chartContainerRef} className="chart-container" />
    </div>
  );
}
