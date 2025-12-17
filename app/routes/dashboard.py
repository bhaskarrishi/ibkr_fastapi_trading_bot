from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from app.services.broadcaster import broadcaster
from app.services.pnl import compute_pnl_by_ticker, compute_daily_realized_pnl
from app.database import SessionLocal
from app.models.trade import Trade
import json
import logging

router = APIRouter(prefix="/dashboard", tags=["Dashboard"]) 

AUTH_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ALGO TRADER - Sign In</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; display:flex; align-items:center; justify-content:center; }
    .card { width: 420px; border: 1px solid #e0e0e0; padding: 24px; border-radius: 8px; box-shadow: 0 6px 16px rgba(0,0,0,0.06); }
    h2 { margin-top: 0 }
    label { display:block; margin-top: 12px }
    input { width:100%; padding:8px; box-sizing:border-box; margin-top:6px }
    button { margin-top: 12px; padding: 8px 12px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold }
    .btn-primary { background: #2b6cb0; color: white; padding: 12px 16px; font-size: 1.0em; width: 100%; box-sizing: border-box }
    .btn-primary:hover { background: #1f4d7f }
    .btn-secondary { background: #f0f0f0; color: #333; padding: 8px 12px; font-size: 0.95em }
    .btn-secondary:hover { background: #e0e0e0 }
    .small { font-size: 0.9em; color:#666 }
    .signup-section { margin-bottom: 16px; text-align: center }
    .signup-section p { margin: 8px 0; color: #666 }
  </style>
</head>
<body>
  <div class="card">
    <div class="signup-section">
      <h3 style="margin-top: 0">New to ALGO TRADER?</h3>
      <a href="/dashboard/signup" style="text-decoration: none">
        <button class="btn-primary">Create Account</button>
      </a>
      <p>Sign up to get started trading</p>
    </div>
    <hr style="margin: 20px 0" />
    <div>
      <h3>Sign In to Your Account</h3>
      <label>User ID <input id="in_id" placeholder="user id"/></label>
      <label>Password <input id="in_pwd" type="password" placeholder="password"/></label>
      <button id="signinBtn" class="btn-secondary" style="width: 100%">Sign In</button>
      <div id="msg" class="small" style="margin-top: 8px"></div>
    </div>
  </div>

  <script>
    function showMsg(m) { const el = document.getElementById('msg'); el.textContent = m }
    document.getElementById('signinBtn').addEventListener('click', () => {
      const id = document.getElementById('in_id').value.trim()
      const pwd = document.getElementById('in_pwd').value
      const stored = JSON.parse(localStorage.getItem('bt_user') || 'null')
      if (!stored || stored.id !== id || stored.pwd !== pwd) { showMsg('Invalid credentials'); return }
      // persist auth marker
      localStorage.setItem('bt_auth', JSON.stringify({ id }))
      window.location = '/dashboard/'
    })
  </script>
</body>
</html>
"""

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Trading Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background: #f9f9f9 }
    .header { display:flex; align-items:center; justify-content:space-between; gap: 12px; background: white; padding: 12px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1) }
    .left, .right { display:flex; gap: 12px; align-items:center }
    .center { text-align:center; flex: 1 }
    .center .bot { display:inline-flex; align-items:center; gap:8px; font-weight:700; font-size:1.2em }
    table { border-collapse: collapse; width: 100%; background: white }
    th, td { padding: 8px; border: 1px solid #ddd; text-align: left }
    th { background: #f4f4f4; font-weight: bold }
    .negative { color: red }
    .positive { color: green }
    .new { background: #fff6cf; transition: background 0.5s ease; }
    .muted { color:#666; font-size: 0.85em }
    .btn { padding:6px 10px; cursor:pointer; background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px }
    .btn:hover { background: #e0e0e0 }
    .btn-danger { background: #ffebee; color: #c62828 }
    .tabs { display: flex; gap: 8px; margin: 20px 0; border-bottom: 1px solid #ddd }
    .tab-btn { padding: 8px 16px; background: #f0f0f0; border: none; cursor: pointer; border-radius: 4px 4px 0 0; border-bottom: 3px solid transparent }
    .tab-btn.active { background: white; border-bottom-color: #2b6cb0 }
    .tab-content { display: none; background: white; padding: 16px; border-radius: 4px; margin-bottom: 20px }
    .tab-content.active { display: block }
    .account-box { display: flex; gap: 20px; justify-content: flex-end; align-items: center }
    .account-item { text-align: right }
    .account-item .label { font-size: 0.85em; color: #666 }
    .account-item .value { font-weight: bold; font-size: 1.1em; color: #2b6cb0 }
    .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 900px }
    .setting-group { background: #f9f9f9; padding: 12px; border-radius: 4px; border: 1px solid #e0e0e0 }
    .setting-group label { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; font-weight: bold }
    .setting-group input { width: 100%; padding: 6px; margin-top: 4px; box-sizing: border-box; border: 1px solid #ddd; border-radius: 4px }
    .setting-group input[type="checkbox"] { width: auto }
    .setting-group .checkbox-label { display: flex; gap: 8px; align-items: center; cursor: pointer }
    .filters { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 12px; align-items: flex-end }
    .filters input, .filters select { padding: 6px; border: 1px solid #ccc; border-radius: 4px }
  </style>
</head>
<body>
  <div class="header">
    <div class="left">
      <span class="muted">User:</span> <strong id="userDisplay">-</strong>
      <button id="logoutBtn" class="btn">Sign Out</button>
    </div>
    <div class="center">
      <div class="bot">
        <svg width="36" height="36" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <rect x="3" y="7" width="18" height="12" rx="2" fill="#2b6cb0" />
          <rect x="7" y="3" width="10" height="6" rx="1" fill="#2b6cb0" />
          <circle cx="8.5" cy="11" r="1.1" fill="#fff" />
          <circle cx="15.5" cy="11" r="1.1" fill="#fff" />
        </svg>
        ALGO TRADER
      </div>
    </div>
    <div class="right">
      <div class="account-box">
        <div class="account-item">
          <div class="label">Account Balance</div>
          <div class="value" id="acctBalance">-</div>
        </div>
        <div class="account-item">
          <div class="label">Invested</div>
          <div class="value" id="acctInvested">-</div>
        </div>
        <div class="account-item">
          <div class="label">Available Cash</div>
          <div class="value" id="acctCash">-</div>
        </div>
      </div>
      <button id="refreshBtn" class="btn">Refresh</button>
      <span id="refreshStatus" style="margin-left:8px;color:#666"></span>
      <button id="filterRejected" class="btn">Show only rejected</button>
      <button id="resetBtn" class="btn btn-danger">Force Reset</button>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" data-tab="trades">Trades & PnL</button>
    <button class="tab-btn" data-tab="settings">Settings</button>
    <button class="tab-btn" data-tab="charts">Charts</button>
  </div>

  <div id="trades" class="tab-content active">
    <div style="margin:12px 0;">
      <strong>Daily realized PnL:</strong> <span id="daily">-</span>
    </div>
    <h3>Tickers - Position Summary with P/L</h3>
    <table id="tbl">
      <thead><tr><th>Symbol</th><th>Position (Outstanding)</th><th>Last Price (Exec)</th><th>Realized P/L</th><th>Unrealized P/L</th><th>Cumulative P/L</th></tr></thead>
      <tbody id="body"></tbody>
    </table>

    <h3>Recent Trades</h3>
    <div class="filters">
      <label>Symbol <input id="filterSymbol" placeholder="e.g. AAPL" /></label>
      <label>Order type
        <select id="filterSide">
          <option value="">All</option>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
        </select>
      </label>
      <label>Start <input id="filterStart" type="datetime-local" /></label>
      <label>End <input id="filterEnd" type="datetime-local" /></label>
      <button id="clearFilters" class="btn">Clear Filters</button>
    </div>
    <table id="trades_tbl">
      <thead><tr><th>ID</th><th>Time</th><th>Symbol</th><th>Order type</th><th>Qty</th><th>Price (Exec)</th><th>Status</th></tr></thead>
      <tbody id="trades_body"></tbody>
    </table>
  </div>

  <div id="settings" class="tab-content">
    <h3>Risk Management Settings</h3>
    <div class="settings-grid">
      <div class="setting-group">
        <label>Max Qty Per Order <input id="s_max_qty" type="number" min="1" /></label>
      </div>
      <div class="setting-group">
        <label>Max Notional Per Order <input id="s_max_notional" type="number" min="100" step="100" /></label>
      </div>
      <div class="setting-group">
        <label>Max Orders Per Minute <input id="s_max_opm" type="number" min="1" /></label>
      </div>
      <div class="setting-group">
        <label>Max Daily Loss <input id="s_max_daily_loss" type="number" min="0" step="100" /></label>
      </div>
      <div class="setting-group">
        <label>Max Trades Per Day <input id="s_max_trades_day" type="number" min="1" /></label>
      </div>
      <div class="setting-group">
        <label>Max Total Position Notional <input id="s_max_total_notional" type="number" min="1000" step="1000" /></label>
      </div>
      <div class="setting-group">
        <label>Max Position Per Symbol <input id="s_max_pos_symbol" type="number" min="1" /></label>
      </div>
      <div class="setting-group">
        <label>Min Buying Power <input id="s_min_buying_power" type="number" min="0" step="100" /></label>
      </div>
      <div class="setting-group">
        <label class="checkbox-label"><input id="s_rth_only" type="checkbox" /> Only Trade During RTH (9:30-16:00 ET)</label>
      </div>
      <div class="setting-group">
        <label class="checkbox-label"><input id="s_subscribe" type="checkbox" /> Subscribe to strategy (allow webhooks)</label>
      </div>
      <div class="setting-group">
        <label class="checkbox-label"><input id="s_enable_validation" type="checkbox" /> Enable signal validation (market data confirmation)</label>
      </div>
    </div>
    <button id="settingsSaveBtn" class="btn" style="margin-top: 12px">Save Settings</button>
    <span id="settingsStatus" style="margin-left: 8px; color: #666"></span>
  </div>

  <div id="charts" class="tab-content">
    <h3>Performance Charts</h3>
    <div style="margin-bottom:12px;">Net P/L per symbol over time (realized)</div>
    <canvas id="chartSymbols" width="900" height="320" style="background:white; border:1px solid #e0e0e0; border-radius:4px"></canvas>
    <div style="margin:16px 0 8px;">Total daily net P/L</div>
    <canvas id="chartDaily" width="900" height="320" style="background:white; border:1px solid #e0e0e0; border-radius:4px"></canvas>
    <div id="chartsStatus" class="muted" style="margin-top:8px;"></div>
  </div>

  <script>
    // Simple client-side auth: redirect to /auth if not authenticated
    function ensureAuth() {
      const auth = localStorage.getItem('bt_auth')
      if (!auth) { window.location = '/auth'; return false }
      const user = JSON.parse(localStorage.getItem('bt_user') || '{}')
      document.getElementById('userDisplay').textContent = user.id || 'Unknown'
      return true
    }

    // Fetch account info
    function fetchAccountInfo() {
      fetch('/dashboard/api/account-info').then(r => r.json()).then(d => {
        document.getElementById('acctBalance').textContent = '$' + d.account_balance.toFixed(2)
        document.getElementById('acctInvested').textContent = '$' + d.invested_amount.toFixed(2)
        document.getElementById('acctCash').textContent = '$' + d.available_cash.toFixed(2)
      }).catch(e => console.log('Could not fetch account info'))
    }

    // Fetch PnL and trades directly from DB-backed API and render
    function fetchPnl() {
      if (!ensureAuth()) return;
      fetch('/dashboard/api/pnl').then(r => r.json()).then(d => {
        const formatCurrency = (v) => {
          if (v === null || v === undefined) return '-'
          const num = parseFloat(v)
          return '$' + num.toFixed(2)
        }
        const formatCurrencyClass = (v) => {
          if (v === null || v === undefined) return ''
          return v < 0 ? 'negative' : 'positive'
        }
        
        // Format daily P/L
        const dailyPnl = parseFloat(d.daily_realized)
        const dailyClass = dailyPnl < 0 ? 'negative' : 'positive'
        document.getElementById('daily').innerHTML = `<span class='${dailyClass}'>${formatCurrency(dailyPnl)}</span>`

        const tbl = document.getElementById('body')
        tbl.innerHTML = ''
        d.tickers.forEach(t => {
          const tr = document.createElement('tr')
          tr.innerHTML = `
            <td>${t.symbol}</td>
            <td>${t.position}</td>
            <td>${formatCurrency(t.last_price)}</td>
            <td class='${formatCurrencyClass(t.realized)}'>${formatCurrency(t.realized)}</td>
            <td class='${formatCurrencyClass(t.unrealized)}'>${formatCurrency(t.unrealized)}</td>
            <td class='${formatCurrencyClass(t.cumulative)}'>${formatCurrency(t.cumulative)}</td>
          `
          tbl.appendChild(tr)
        })

        // Store recent trades (including rejected/error trades) and render with filters
        allTrades = d.trades || []
        const topId = allTrades.length ? allTrades[0].id : null
        const highlightNew = (lastTopTradeId !== null && topId !== null && topId !== lastTopTradeId)
        lastTopTradeId = topId
        applyFilter(highlightNew)
      })
    }

    // Load settings from API
    function loadSettings() {
      fetch('/dashboard/api/settings').then(r => r.json()).then(d => {
        document.getElementById('s_max_qty').value = d.max_qty_per_order
        document.getElementById('s_max_notional').value = d.max_notional_per_order
        document.getElementById('s_max_opm').value = d.max_orders_per_minute
        document.getElementById('s_max_daily_loss').value = d.max_daily_loss
        document.getElementById('s_max_trades_day').value = d.max_trades_per_day
        document.getElementById('s_max_total_notional').value = d.max_total_position_notional
        document.getElementById('s_max_pos_symbol').value = d.max_position_per_symbol
        document.getElementById('s_min_buying_power').value = d.min_buying_power_required
        document.getElementById('s_rth_only').checked = d.only_trade_during_rth
        document.getElementById('s_subscribe').checked = d.subscribe_to_strategy
        document.getElementById('s_enable_validation').checked = d.enable_signal_validation
      })
    }

    // Simple canvas line renderer
    function drawSeries(canvasId, seriesList, opts={}) {
      const canvas = document.getElementById(canvasId)
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0,0,canvas.width,canvas.height)
      if (!seriesList || !seriesList.length) {
        ctx.fillStyle = '#666'
        ctx.fillText('No data', 10, 20)
        return
      }
      const padding = 40
      let xs = [], ys = []
      seriesList.forEach(s => { s.data.forEach(p => { xs.push(p.x); ys.push(p.y) }) })
      const minX = Math.min(...xs), maxX = Math.max(...xs)
      const minY = Math.min(...ys), maxY = Math.max(...ys)
      const xSpan = (maxX - minX) || 1
      const ySpan = (maxY - minY) || 1

      // axes
      ctx.strokeStyle = '#ccc'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(padding, padding/2); ctx.lineTo(padding, canvas.height - padding); ctx.lineTo(canvas.width - padding/2, canvas.height - padding); ctx.stroke()

      const colors = ['#2b6cb0','#e67e22','#16a085','#8e44ad','#c0392b','#2c3e50']
      seriesList.forEach((s, idx) => {
        ctx.strokeStyle = colors[idx % colors.length]
        ctx.beginPath()
        s.data.forEach((p, i) => {
          const x = padding + ((p.x - minX)/xSpan) * (canvas.width - padding*1.5)
          const y = canvas.height - padding - ((p.y - minY)/ySpan) * (canvas.height - padding*1.5)
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
        })
        ctx.stroke()
        // legend
        ctx.fillStyle = colors[idx % colors.length]
        ctx.fillRect(canvas.width - padding + 4, padding + idx*16, 10, 10)
        ctx.fillStyle = '#333'
        ctx.fillText(s.label, canvas.width - padding + 18, padding + idx*16 + 10)
      })

      // labels
      ctx.fillStyle = '#555'; ctx.font = '12px Arial'
      ctx.fillText((opts.xLabel || 'time'), canvas.width/2 - 20, canvas.height - 8)
      ctx.save(); ctx.translate(12, canvas.height/2 + 20); ctx.rotate(-Math.PI/2); ctx.fillText(opts.yLabel || 'value', 0,0); ctx.restore()
    }

    async function fetchCharts() {
      const statusEl = document.getElementById('chartsStatus')
      try {
        statusEl.textContent = 'Loading charts...'
        const r = await fetch('/dashboard/api/charts')
        const d = await r.json()
        // per symbol series
        const perSymbol = []
        Object.keys(d.per_symbol || {}).forEach(sym => {
          const arr = d.per_symbol[sym].map(p => ({ x: new Date(p.t).getTime(), y: p.v }))
          if (arr.length) perSymbol.push({ label: sym, data: arr })
        })
        drawSeries('chartSymbols', perSymbol, { xLabel: 'time', yLabel: 'P/L' })

        // daily series
        const daily = (d.daily || []).map(p => ({ x: new Date(p.day).getTime(), y: p.v }))
        drawSeries('chartDaily', [{ label: 'Daily P/L', data: daily }], { xLabel: 'day', yLabel: 'P/L' })
        statusEl.textContent = ''
      } catch (e) {
        statusEl.textContent = 'Failed to load charts'
      }
    }

    // Save settings
    document.getElementById('settingsSaveBtn').addEventListener('click', async () => {
      const body = {
        max_qty_per_order: document.getElementById('s_max_qty').value,
        max_notional_per_order: document.getElementById('s_max_notional').value,
        max_orders_per_minute: document.getElementById('s_max_opm').value,
        max_daily_loss: document.getElementById('s_max_daily_loss').value,
        max_trades_per_day: document.getElementById('s_max_trades_day').value,
        max_total_position_notional: document.getElementById('s_max_total_notional').value,
        max_position_per_symbol: document.getElementById('s_max_pos_symbol').value,
        min_buying_power_required: document.getElementById('s_min_buying_power').value,
        only_trade_during_rth: document.getElementById('s_rth_only').checked,
        subscribe_to_strategy: document.getElementById('s_subscribe').checked,
        enable_signal_validation: document.getElementById('s_enable_validation').checked,
      }
      const r = await fetch('/dashboard/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })
      const j = await r.json()
      const statusEl = document.getElementById('settingsStatus')
      if (j.status === 'ok') {
        statusEl.textContent = 'Settings saved!'
        setTimeout(() => { statusEl.textContent = '' }, 2500)
      } else {
        statusEl.textContent = 'Error: ' + (j.reason || 'unknown')
      }
    })

    // Keep track of top trade id to highlight newly-arrived trades
    let allTrades = []
    let lastTopTradeId = null

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'))
        document.querySelectorAll('.tab-btn').forEach(tb => tb.classList.remove('active'))
        btn.classList.add('active')
        document.getElementById(btn.dataset.tab).classList.add('active')
        if (btn.dataset.tab === 'charts') fetchCharts()
      })
    })

    // Refresh button
    const refreshBtn = document.getElementById('refreshBtn')
    const refreshStatus = document.getElementById('refreshStatus')
    async function doRefresh() {
      try {
        refreshBtn.disabled = true
        refreshBtn.textContent = 'Refreshing...'
        refreshStatus.textContent = ''
        await fetchPnl()
        await fetchAccountInfo()
        refreshStatus.textContent = 'Refreshed'
        setTimeout(() => { refreshStatus.textContent = '' }, 2500)
      } catch (e) {
        refreshStatus.textContent = 'Error'
      } finally {
        refreshBtn.disabled = false
        refreshBtn.textContent = 'Refresh'
      }
    }
    refreshBtn.addEventListener('click', () => doRefresh())

    // Force Reset button - calls backend to clear DB
    const resetBtn = document.getElementById('resetBtn')
    resetBtn.addEventListener('click', async () => {
      if (!confirm('Force reset will delete ALL trades. Are you sure?')) return;
      resetBtn.disabled = true
      resetBtn.textContent = 'Resetting...'
      try {
        const r = await fetch('/dashboard/api/reset', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ confirm: true }) })
        const j = await r.json()
        if (j.status === 'ok') {
          alert('Database reset, deleted ' + j.deleted + ' trades')
          await fetchPnl()
        } else {
          alert('Reset failed: ' + (j.reason || 'unknown'))
        }
      } catch (e) {
        alert('Reset error: ' + e)
      } finally {
        resetBtn.disabled = false
        resetBtn.textContent = 'Force Reset'
      }
    })

    // Sign out
    const logoutBtn = document.getElementById('logoutBtn')
    logoutBtn.addEventListener('click', () => { localStorage.removeItem('bt_auth'); window.location = '/auth' })

    // Filters
    const filterSymbol = document.getElementById('filterSymbol')
    const filterSide = document.getElementById('filterSide')
    const filterStart = document.getElementById('filterStart')
    const filterEnd = document.getElementById('filterEnd')
    const clearFiltersBtn = document.getElementById('clearFilters')

    let filterRejectedActive = false
    const filterBtn = document.getElementById('filterRejected')
    function applyFilter(highlightNew = false) {
      const tbody = document.getElementById('trades_body')
      tbody.innerHTML = ''

      const sym = filterSymbol.value.trim().toUpperCase()
      const side = filterSide.value
      const startVal = filterStart.value
      const endVal = filterEnd.value
      const startTs = startVal ? Date.parse(startVal) : null
      const endTs = endVal ? Date.parse(endVal) : null

      const filtered = (allTrades || []).filter(trade => {
        const statusText = (trade.status || '').toLowerCase()
        if (filterRejectedActive && statusText.startsWith('filled')) return false
        if (sym && !(trade.symbol || '').toUpperCase().includes(sym)) return false
        if (side && trade.side !== side) return false
        const ts = Date.parse(trade.timestamp)
        if (startTs && (!ts || ts < startTs)) return false
        if (endTs && (!ts || ts > endTs)) return false
        return true
      })

      filtered.forEach((trade, idx) => {
        const tr = document.createElement('tr')
        const td = (v) => `<td>${v}</td>`
        const statusText = trade.status || ''
        if (!(statusText.toLowerCase().startsWith('filled'))) {
          tr.classList.add('negative')
        }
        tr.innerHTML = td(trade.id) + td(trade.timestamp) + td(trade.symbol) + td(trade.side) + td(trade.qty) + td(trade.price) + td(statusText)
        tbody.appendChild(tr)
      })

      if (highlightNew && filtered.length) {
        const firstRow = tbody.querySelector('tr')
        if (firstRow) {
          firstRow.classList.add('new')
          firstRow.scrollIntoView({ behavior: 'smooth', block: 'start' })
          setTimeout(() => { firstRow.classList.remove('new') }, 4000)
        }
      }

      filterBtn.textContent = filterRejectedActive ? 'Show all trades' : 'Show only rejected'
    }

    filterSymbol.addEventListener('input', () => applyFilter())
    filterSide.addEventListener('change', () => applyFilter())
    filterStart.addEventListener('change', () => applyFilter())
    filterEnd.addEventListener('change', () => applyFilter())
    clearFiltersBtn.addEventListener('click', () => {
      filterSymbol.value = ''
      filterSide.value = ''
      filterStart.value = ''
      filterEnd.value = ''
      filterRejectedActive = false
      applyFilter()
    })
    filterBtn.addEventListener('click', () => { filterRejectedActive = !filterRejectedActive; applyFilter() })

    // Fetch on load (after filters exist)
    fetchPnl()
    fetchAccountInfo()
    loadSettings()
  </script>
</body>
</html>
"""

@router.get("/", response_class=HTMLResponse)
async def dashboard_index():
    return HTML

@router.get('/api/pnl')
async def api_pnl():
    db = SessionLocal()
    try:
        tickers = compute_pnl_by_ticker(db)
        tickers_list = list(tickers.values())
        daily = compute_daily_realized_pnl(db)
        # compute per-trade pnl mapping for filled trades
        from app.services.pnl import compute_trade_pnls
        trade_pnls = compute_trade_pnls(db)

        # include recent trades (including rejected/error statuses)
        recent = []
        rows = db.query(Trade).order_by(Trade.timestamp.desc()).limit(50).all()
        for t in rows:
            pnl_entry = trade_pnls.get(t.id)
            pnl_val = pnl_entry['net'] if pnl_entry is not None else None
            recent.append({
                'id': t.id,
                'timestamp': t.timestamp.isoformat() if t.timestamp else '',
                'symbol': t.symbol,
                'side': t.side,
                'qty': t.qty,
                'price': t.executed_price if t.executed_price is not None else t.price,  # Show executed price
                'pnl': pnl_val,
                'status': t.status,
            })
        return JSONResponse({"tickers": tickers_list, "daily_realized": daily, "trades": recent})
    finally:
        db.close()

SIGNUP_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ALGO TRADER - Sign Up</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; display:flex; align-items:center; justify-content:center; }
    .card { width: 420px; border: 1px solid #e0e0e0; padding: 24px; border-radius: 8px; box-shadow: 0 6px 16px rgba(0,0,0,0.06); }
    h2 { margin-top: 0 }
    label { display:block; margin-top: 12px }
    input { width:100%; padding:8px; box-sizing:border-box; margin-top:6px }
    button { margin-top: 12px; padding: 8px 12px }
    .small { font-size: 0.9em; color:#666 }
  </style>
</head>
<body>
  <div class="card">
    <h2>ALGO TRADER - Sign Up</h2>
    <div>
      <label>User ID <input id="su_id" placeholder="choose a user id"/></label>
      <label>Password <input id="su_pwd" type="password" placeholder="choose a password"/></label>
      <button id="signupBtn">Sign Up</button>
      <div class="small" id="msg">After sign up you'll be redirected to Sign In.</div>
      <div class="small" style="margin-top:8px"><a href="/dashboard/auth">Go to Sign In</a></div>
    </div>
  </div>

  <script>
    function showMsg(m) { const el = document.getElementById('msg'); el.textContent = m }
    document.getElementById('signupBtn').addEventListener('click', () => {
      const id = document.getElementById('su_id').value.trim()
      const pwd = document.getElementById('su_pwd').value
      if (!id || !pwd) { showMsg('Please provide id and password'); return }
      localStorage.setItem('bt_user', JSON.stringify({ id, pwd }))
      showMsg('Sign up saved — redirecting to Sign In...')
      setTimeout(() => { window.location = '/dashboard/auth' }, 900)
    })
  </script>
</body>
</html>
"""

@router.get('/signup', response_class=HTMLResponse)
async def signup_page():
    return SIGNUP_HTML

@router.get("/auth", response_class=HTMLResponse)
async def auth_page():
    return AUTH_HTML

@router.post('/api/reset')
async def api_reset():
    db = SessionLocal()
    try:
        deleted = db.query(Trade).delete()
        db.commit()
        logging.info("Database reset performed; deleted %s trades", deleted)
        return JSONResponse({"status": "ok", "deleted": deleted})
    except Exception as e:
        db.rollback()
        logging.exception("Failed to reset DB")
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)
    finally:
        db.close()

@router.get('/api/charts')
async def api_charts():
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(Trade.status.like('Filled%')).order_by(Trade.timestamp).all()
        from app.services.pnl import compute_trade_pnls
        tpnls = compute_trade_pnls(db)

        per_symbol = {}
        daily = {}
        for t in trades:
            real = tpnls.get(t.id, {}).get('realized', 0.0)
            sym = t.symbol
            ts_iso = t.timestamp.isoformat()
            if sym not in per_symbol:
                per_symbol[sym] = []
            cum_prev = per_symbol[sym][-1]['v'] if per_symbol[sym] else 0.0
            cum_now = round(cum_prev + real, 6)
            per_symbol[sym].append({'t': ts_iso, 'v': cum_now})

            day_key = t.timestamp.date().isoformat()
            daily[day_key] = round(daily.get(day_key, 0.0) + real, 6)

        daily_series = [{'day': k, 'v': v} for k, v in sorted(daily.items())]
        return JSONResponse({"per_symbol": per_symbol, "daily": daily_series})
    finally:
        db.close()

# WebSocket endpoints removed — dashboard now reads directly from the DB on refresh

@router.get('/api/settings')
async def get_settings():
    db = SessionLocal()
    try:
        from app.models.settings import TradeSettings
        from sqlalchemy.exc import OperationalError
        try:
            setting = db.query(TradeSettings).first()
        except OperationalError:
            # attempt to recreate table if schema mismatch
            from app.database import Base, engine
            Base.metadata.drop_all(bind=engine, tables=[TradeSettings.__table__])
            Base.metadata.create_all(bind=engine, tables=[TradeSettings.__table__])
            setting = db.query(TradeSettings).first()
        if not setting:
            setting = TradeSettings()
            db.add(setting)
            db.commit()
        return JSONResponse({
            "max_qty_per_order": setting.max_qty_per_order,
            "max_notional_per_order": setting.max_notional_per_order,
            "max_orders_per_minute": setting.max_orders_per_minute,
            "max_daily_loss": setting.max_daily_loss,
            "max_trades_per_day": setting.max_trades_per_day,
            "max_total_position_notional": setting.max_total_position_notional,
            "max_position_per_symbol": setting.max_position_per_symbol,
            "only_trade_during_rth": setting.only_trade_during_rth,
            "min_buying_power_required": setting.min_buying_power_required,
            "subscribe_to_strategy": getattr(setting, 'subscribe_to_strategy', True),
            "enable_signal_validation": getattr(setting, 'enable_signal_validation', True),
        })
    finally:
        db.close()

@router.post('/api/settings')
async def update_settings(body: dict):
    db = SessionLocal()
    try:
        from app.models.settings import TradeSettings
        from sqlalchemy import func
        from sqlalchemy.exc import OperationalError
        try:
            setting = db.query(TradeSettings).first()
        except OperationalError:
            from app.database import Base, engine
            Base.metadata.drop_all(bind=engine, tables=[TradeSettings.__table__])
            Base.metadata.create_all(bind=engine, tables=[TradeSettings.__table__])
            setting = db.query(TradeSettings).first()
        if not setting:
            setting = TradeSettings()
        
        # Update fields if provided
        if 'max_qty_per_order' in body:
            setting.max_qty_per_order = int(body['max_qty_per_order'])
        if 'max_notional_per_order' in body:
            setting.max_notional_per_order = float(body['max_notional_per_order'])
        if 'max_orders_per_minute' in body:
            setting.max_orders_per_minute = int(body['max_orders_per_minute'])
        if 'max_daily_loss' in body:
            setting.max_daily_loss = float(body['max_daily_loss'])
        if 'max_trades_per_day' in body:
            setting.max_trades_per_day = int(body['max_trades_per_day'])
        if 'max_total_position_notional' in body:
            setting.max_total_position_notional = float(body['max_total_position_notional'])
        if 'max_position_per_symbol' in body:
            setting.max_position_per_symbol = int(body['max_position_per_symbol'])
        if 'only_trade_during_rth' in body:
            setting.only_trade_during_rth = bool(body['only_trade_during_rth'])
        if 'min_buying_power_required' in body:
            setting.min_buying_power_required = float(body['min_buying_power_required'])
        if 'subscribe_to_strategy' in body:
            setting.subscribe_to_strategy = bool(body['subscribe_to_strategy'])
        if 'enable_signal_validation' in body:
            setting.enable_signal_validation = bool(body['enable_signal_validation'])
        
        db.add(setting)
        db.commit()
        logging.info("Trade settings updated")
        return JSONResponse({"status": "ok", "message": "Settings saved"})
    except Exception as e:
        db.rollback()
        logging.exception("Failed to update settings")
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)
    finally:
        db.close()

@router.get('/api/account-info')
async def get_account_info():
    """Return mock account info. In production, fetch from IBKR."""
    return JSONResponse({
        "account_balance": 100000.0,
        "invested_amount": 15250.50,
        "available_cash": 84749.50,
        "buying_power": 169499.0,
        "margin_used": 0.0,
    })
