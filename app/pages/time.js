import Head from 'next/head'
import { useEffect, useState } from 'react'

const KALSHI_HOST = process.env.NEXT_PUBLIC_KALSHI_HOST || 'https://api.elections.kalshi.com'
const LOCAL_API = process.env.NEXT_PUBLIC_LOCAL_API || 'http://127.0.0.1:4242'
const REFRESH_MS = 15000

function fmt$(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `$${n.toFixed(2)}`
}
function fmtPct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(1)}¢`
}
function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export default function TimePage() {
  const [positions, setPositions] = useState([])
  const [fills, setFills] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [posRes, fillsRes] = await Promise.all([
          fetch(`${LOCAL_API}/api/portfolio`).catch(() => null),
          fetch(`${LOCAL_API}/api/fills?limit=200`).catch(() => null),
        ])
        if (!alive) return

        let positionsData = []
        let fillsData = []

        if (posRes && posRes.ok) {
          const posJson = await posRes.json()
          positionsData = Array.isArray(posJson.positions) ? posJson.positions : []
          if (posJson.cash !== undefined) {
            positionsData = [
              ...positionsData,
              {
                ticker: '__cash__',
                side: 'cash',
                count: 1,
                avg_price: Number(posJson.cash),
                current_price: Number(posJson.cash),
                pnl: 0,
                status: 'open',
                created_time: new Date().toISOString(),
              },
            ]
          }
        }

        if (fillsRes && fillsRes.ok) {
          const fillsJson = await fillsRes.json()
          fillsData = Array.isArray(fillsJson.fills) ? fillsJson.fills : []
        }

        if (positionsData.length === 0 && fillsData.length === 0) {
          setError('No position or fill data available yet.')
        }

        setPositions(positionsData)
        setFills(fillsData)
        setLastUpdated(new Date())
      } catch (e) {
        if (!alive) return
        setError(e?.message || 'Failed to load timeline data')
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()
    const id = setInterval(load, REFRESH_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const openPositions = positions.filter(p => p.status === 'open' || !p.status)
  const closedPositions = positions.filter(p => p.status === 'closed')

  return (
    <>
      <Head>
        <title>time.somacosf.com — Position Timelines</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>{`
          :root {
            --bg: #050508;
            --bg2: #0a0b12;
            --panel: #0f1019;
            --border: #1b1d2a;
            --text: #e6e6f0;
            --muted: #7a7f96;
            --amber: #FF9000;
            --cyan: #00CCDD;
            --green: #00DD66;
            --red: #ff4d4d;
            --blue: #4d8eff;
          }
          * { box-sizing: border-box; }
          html, body {
            margin: 0;
            background: var(--bg);
            color: var(--text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
            -webkit-font-smoothing: antialiased;
          }
          header {
            position: sticky;
            top: 0;
            z-index: 10;
            background: rgba(5,5,8,0.85);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--border);
            padding: 14px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            flex-wrap: wrap;
          }
          .brand {
            display: flex;
            align-items: center;
            gap: 12px;
          }
          .brand-mark {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--amber);
            box-shadow: 0 0 12px var(--amber);
          }
          .brand h1 {
            margin: 0;
            font-size: 14px;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--amber);
          }
          .metrics {
            display: flex;
            gap: 18px;
            flex-wrap: wrap;
          }
          .metric {
            display: flex;
            flex-direction: column;
            gap: 2px;
          }
          .metric-label {
            font-size: 10px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--muted);
          }
          .metric-value {
            font-size: 13px;
            color: var(--cyan);
          }
          main {
            padding: 20px 24px 40px;
            max-width: 1400px;
            margin: 0 auto;
          }
          .section {
            margin-bottom: 28px;
          }
          .section-title {
            font-size: 11px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--muted);
            margin: 0 0 12px;
          }
          .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
          }
          .card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
          }
          .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
          }
          .ticker {
            font-size: 12px;
            color: var(--text);
            word-break: break-word;
          }
          .badge {
            font-size: 10px;
            padding: 3px 7px;
            border-radius: 999px;
            border: 1px solid;
            white-space: nowrap;
            text-transform: uppercase;
            letter-spacing: 0.08em;
          }
          .badge-open {
            color: var(--green);
            border-color: var(--green);
            background: rgba(0,221,102,0.08);
          }
          .badge-closed {
            color: var(--muted);
            border-color: var(--muted);
            background: rgba(122,127,150,0.08);
          }
          .badge-cash {
            color: var(--amber);
            border-color: var(--amber);
            background: rgba(255,144,0,0.08);
          }
          .row {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            font-size: 11px;
          }
          .label {
            color: var(--muted);
          }
          .value {
            color: var(--text);
            text-align: right;
          }
          .value-profit {
            color: var(--green);
          }
          .value-loss {
            color: var(--red);
          }
          .timeline {
            margin-top: 4px;
            display: flex;
            flex-direction: column;
            gap: 6px;
          }
          .timeline-bar-wrap {
            height: 8px;
            border-radius: 999px;
            background: var(--bg2);
            overflow: hidden;
          }
          .timeline-bar {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--cyan), var(--blue));
          }
          .timeline-bar.profit {
            background: linear-gradient(90deg, var(--green), var(--cyan));
          }
          .timeline-bar.loss {
            background: linear-gradient(90deg, var(--red), var(--amber));
          }
          .fill-list {
            margin-top: 6px;
            display: flex;
            flex-direction: column;
            gap: 6px;
          }
          .fill-row {
            display: flex;
            justify-content: space-between;
            gap: 8px;
            font-size: 10px;
            color: var(--muted);
            border-top: 1px dashed var(--border);
            padding-top: 6px;
          }
          .fill-row .fill-action {
            color: var(--text);
          }
          .empty {
            padding: 24px;
            text-align: center;
            color: var(--muted);
            font-size: 12px;
          }
          .footer {
            padding: 0 24px 30px;
            max-width: 1400px;
            margin: 0 auto;
            color: var(--muted);
            font-size: 11px;
          }
        `}</style>
      </Head>
      <header>
        <div className="brand">
          <div className="brand-mark" />
          <h1>time.somacosf.com — Position Timelines</h1>
        </div>
        <div className="metrics">
          <div className="metric">
            <div className="metric-label">Positions</div>
            <div className="metric-value">{openPositions.length + closedPositions.length}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Open</div>
            <div className="metric-value">{openPositions.length}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Closed</div>
            <div className="metric-value">{closedPositions.length}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Fills</div>
            <div className="metric-value">{fills.length}</div>
          </div>
          <div className="metric">
            <div className="metric-label">Updated</div>
            <div className="metric-value">
              {lastUpdated ? lastUpdated.toLocaleTimeString('en-US', { hour12: false }) : '—'}
            </div>
          </div>
        </div>
      </header>
      <main>
        <section className="section">
          <h2 className="section-title">Open Positions</h2>
          {openPositions.length === 0 ? (
            <div className="card">
              <div className="empty">No open positions.</div>
            </div>
          ) : (
            <div className="grid">
              {openPositions.map((p, i) => {
                const entryPrice = Number(p.avg_price || 0)
                const currentPrice = Number(p.current_price || 0)
                const count = Number(p.count || 0)
                const notional = entryPrice * count
                const pnl = Number(p.pnl || 0)
                const pnlClass = pnl > 0 ? 'value-profit' : pnl < 0 ? 'value-loss' : 'value'
                const progress = entryPrice > 0 ? Math.min(100, Math.max(0, (currentPrice / entryPrice) * 100)) : 0
                return (
                  <div className="card" key={`${p.ticker}-${i}`}>
                    <div className="card-header">
                      <div className="ticker">{p.ticker}</div>
                      <span className="badge badge-open">open</span>
                    </div>
                    <div className="row">
                      <div className="label">Side</div>
                      <div className="value">{p.side || '—'}</div>
                    </div>
                    <div className="row">
                      <div className="label">Count</div>
                      <div className="value">{count.toFixed(2)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Entry</div>
                      <div className="value">{fmtPct(entryPrice)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Mark</div>
                      <div className="value">{fmtPct(currentPrice)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Notional</div>
                      <div className="value">{fmt$(notional)}</div>
                    </div>
                    <div className="row">
                      <div className="label">P&L</div>
                      <div className={`value ${pnlClass}`}>{fmt$(pnl)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Opened</div>
                      <div className="value">{fmtTime(p.created_time)}</div>
                    </div>
                    <div className="timeline">
                      <div className="timeline-bar-wrap">
                        <div
                          className={`timeline-bar ${pnl > 0 ? 'profit' : pnl < 0 ? 'loss' : ''}`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        <section className="section">
          <h2 className="section-title">Closed Positions</h2>
          {closedPositions.length === 0 ? (
            <div className="card">
              <div className="empty">No closed positions.</div>
            </div>
          ) : (
            <div className="grid">
              {closedPositions.map((p, i) => {
                const entryPrice = Number(p.avg_price || 0)
                const exitPrice = Number(p.current_price || 0)
                const count = Number(p.count || 0)
                const pnl = Number(p.pnl || 0)
                const pnlClass = pnl > 0 ? 'value-profit' : pnl < 0 ? 'value-loss' : 'value'
                return (
                  <div className="card" key={`${p.ticker}-closed-${i}`}>
                    <div className="card-header">
                      <div className="ticker">{p.ticker}</div>
                      <span className="badge badge-closed">closed</span>
                    </div>
                    <div className="row">
                      <div className="label">Side</div>
                      <div className="value">{p.side || '—'}</div>
                    </div>
                    <div className="row">
                      <div className="label">Count</div>
                      <div className="value">{count.toFixed(2)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Entry</div>
                      <div className="value">{fmtPct(entryPrice)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Exit</div>
                      <div className="value">{fmtPct(exitPrice)}</div>
                    </div>
                    <div className="row">
                      <div className="label">P&L</div>
                      <div className={`value ${pnlClass}`}>{fmt$(pnl)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Opened</div>
                      <div className="value">{fmtTime(p.created_time)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Closed</div>
                      <div className="value">{fmtTime(p.closed_time)}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        <section className="section">
          <h2 className="section-title">Recent Fills</h2>
          {fills.length === 0 ? (
            <div className="card">
              <div className="empty">No fills recorded.</div>
            </div>
          ) : (
            <div className="grid">
              {fills.slice(0, 50).map((f, i) => {
                const action = String(f.action || '').toLowerCase()
                const side = String(f.outcome_side || '').toLowerCase()
                const price = Number(f.price_dollars || 0)
                const count = Number(f.count_fp || 0)
                const fee = Number(f.fee_dollars || 0)
                return (
                  <div className="card" key={`fill-${i}`}>
                    <div className="card-header">
                      <div className="ticker">{f.market_ticker || f.ticker || '—'}</div>
                      <span className="badge badge-open">{action} {side}</span>
                    </div>
                    <div className="row">
                      <div className="label">Price</div>
                      <div className="value">{fmtPct(price)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Count</div>
                      <div className="value">{count.toFixed(2)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Fee</div>
                      <div className="value">{fmt$(fee)}</div>
                    </div>
                    <div className="row">
                      <div className="label">Time</div>
                      <div className="value">{fmtTime(f.created_time)}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </main>
      <div className="footer">
        Data source: local API at {LOCAL_API} · Auto-refresh {REFRESH_MS / 1000}s · Cash and portfolio values shown as-is from exchange response.
      </div>
    </>
  )
}
