"""
PEC Load Estimator — Flask / Vercel version
==========================================
Vercel-deployable Python app using Flask.
Streamlit cannot run on Vercel (it needs persistent WebSockets);
Flask works as a serverless function — one HTTP request per calculation.

Deployment:
  1. Copy the `vercel/` folder to a new Git repo.
  2. Push to GitHub, then import at https://vercel.com/new
  3. Vercel detects Python automatically — no extra steps needed.
"""

from flask import Flask, request, render_template_string

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DATA TABLES  (Philippine Electrical Code reference data)
# ─────────────────────────────────────────────────────────────────────────────

# Table t9 — Single-Phase AC Motor Full-Load Currents (Amperes)
# Key = horsepower string  |  Value = {voltage: full_load_amps}
MOTOR_TABLE = {
    "1/6":  {115: 4.4,  200: 2.5,  208: 2.4,  230: 2.2},
    "1/4":  {115: 5.8,  200: 3.3,  208: 3.2,  230: 2.9},
    "1/3":  {115: 7.2,  200: 4.1,  208: 4.0,  230: 3.6},
    "1/2":  {115: 9.8,  200: 5.6,  208: 5.4,  230: 4.9},
    "3/4":  {115: 13.8, 200: 7.9,  208: 7.6,  230: 6.9},
    "1":    {115: 16,   200: 9.2,  208: 8.8,  230: 8.0},
    "1.5":  {115: 20,   200: 11.5, 208: 11.0, 230: 10.0},
    "2":    {115: 24,   200: 13.8, 208: 13.2, 230: 12.0},
    "3":    {115: 34,   200: 19.6, 208: 18.7, 230: 17.0},
    "5":    {115: 56,   200: 32.2, 208: 30.8, 230: 28.0},
    "7.5":  {115: 80,   200: 46.0, 208: 44.0, 230: 40.0},
    "10":   {115: 100,  200: 57.5, 208: 55.0, 230: 50.0},
}

# Table t8 — Cooking Appliance Demand Factors (indexed by number of units, 1-based)
# COL_A : fixed kW demand for large appliances (> 8.75 kW each)
# COL_B : demand factor % for small appliances  (≤ 3.5 kW each)
# COL_C : demand factor % for medium appliances (3.5 – 8.75 kW each)
COL_A = [0, 8,  11, 14, 17, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
         31, 32, 33, 34, 35, 36, 37, 38, 39, 40]
COL_B = [0, 80, 75, 70, 66, 62, 59, 56, 53, 51, 49, 47, 45, 43, 41, 40,
         39, 38, 37, 36, 35, 34, 33, 32, 31, 30]
COL_C = [0, 80, 65, 55, 50, 45, 43, 40, 36, 35, 34, 32, 32, 32, 32, 32,
         28, 28, 28, 28, 28, 26, 26, 26, 26, 26]


# ─────────────────────────────────────────────────────────────────────────────
# CALCULATION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def calc_lighting(connected_va: float) -> float:
    """
    General Lighting — Dwelling Units  [PEC Table 2.20.3.3]
    3-tier demand factor rule:
      Tier 1 — First    3,000 VA  → 100%
      Tier 2 — Next   117,000 VA  →  35%  (VA 3,001 – 120,000)
      Tier 3 — Over   120,000 VA  →  25%
    Example: 5,000 VA  →  3,000 + (5,000 − 3,000) × 0.35  =  3,700 VA demand
    """
    if connected_va <= 3_000:
        return connected_va                                      # Tier 1: 100 %
    elif connected_va <= 120_000:
        return 3_000 + (connected_va - 3_000) * 0.35            # Tier 2: 35 %
    else:
        # Tier 3: 25 % on anything above 120,000 VA
        return 3_000 + 117_000 * 0.35 + (connected_va - 120_000) * 0.25


def calc_cooking(qty: int, va_per_unit: float) -> float:
    """
    Fixed Cooking Appliances  [PEC Table 2.20.3.16 / t8]
    Column selection is based on the individual appliance kW rating:
      < 3.5 kW  → Column B percentage of total connected load
      ≤ 8.75 kW → Column C percentage of total connected load
      > 8.75 kW → Column A fixed kW value (converted to VA)
    Table supports up to 25 appliances; qty is capped at 25.
    """
    if qty == 0 or va_per_unit == 0:
        return 0.0
    qty = min(qty, 25)
    kw = va_per_unit / 1000
    if kw < 3.5:
        return va_per_unit * qty * (COL_B[qty] / 100)
    elif kw <= 8.75:
        return va_per_unit * qty * (COL_C[qty] / 100)
    else:
        return COL_A[qty] * 1000


def calc_dryer(qty: int, va_per_unit: float) -> float:
    """
    Clothes Dryers  [PEC Table 2.20.3.6 / t6]
    PEC minimum rating is 5,000 VA per dryer.
    If the nameplate is lower, use 5,000 VA as the floor.
    Demand = max(5,000, nameplate_VA) × quantity   (100 % demand factor)
    """
    if qty == 0:
        return 0.0
    return max(5_000, va_per_unit) * qty


def calc_motor(hp_str: str, volts: int) -> float:
    """
    Largest Motor Load  [PEC Rule]
    The largest motor is sized at 125 % of its Full-Load Current (FLC).
    Demand VA = FLC (Amperes) × Voltage × 1.25
    FLC values come from Table t9 (MOTOR_TABLE).
    """
    if not hp_str or hp_str == "none":
        return 0.0
    amps = MOTOR_TABLE[hp_str][volts]
    return amps * volts * 1.25


# ─────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE — Calculator + Reference Tables tabs (pure CSS/JS tabs)
# ─────────────────────────────────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PEC Load Estimator</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root { --primary:#2563eb; --primary-hover:#1d4ed8; --accent:#059669;
            --bg:#f8fafc; --card:#fff; --border:#e2e8f0; --text:#1e293b; }
    * { box-sizing:border-box; }
    body { font-family:'Inter',sans-serif; background:var(--bg); color:var(--text);
           margin:0; padding:0 0 60px; }

    /* ── Nav bar ── */
    .navbar { background:rgba(255,255,255,.9); backdrop-filter:blur(10px);
              border-bottom:1px solid var(--border); padding:12px 20px;
              display:flex; justify-content:space-between; align-items:center;
              position:sticky; top:0; z-index:100; }
    .navbar h1 { margin:0; font-size:1.1rem; color:var(--primary); }

    /* ── Tab strip ── */
    .tabs { display:flex; gap:4px; padding:20px 16px 0;
            max-width:750px; margin:0 auto; }
    .tab-btn { padding:9px 20px; border:none; border-radius:8px 8px 0 0;
               font-family:'Inter',sans-serif; font-size:.9rem; font-weight:600;
               cursor:pointer; background:var(--border); color:var(--text);
               border-bottom:3px solid transparent; transition:all .2s; }
    .tab-btn.active { background:var(--card); color:var(--primary);
                      border-bottom:3px solid var(--primary);
                      box-shadow:0 -2px 8px rgba(0,0,0,.06); }

    /* ── Tab panels ── */
    .tab-panel { display:none; max-width:750px; margin:0 auto; padding:0 16px; }
    .tab-panel.active { display:block; }

    /* ── Cards ── */
    .card { background:var(--card); border:1px solid var(--border); border-radius:14px;
            padding:22px; margin-bottom:18px; margin-top:18px;
            box-shadow:0 2px 8px rgba(0,0,0,.05); }
    h3 { margin:0 0 14px; font-size:1rem; display:flex; align-items:center; gap:8px; }

    /* ── Form elements ── */
    label { font-size:.72rem; text-transform:uppercase; letter-spacing:.05em;
            font-weight:700; color:var(--primary); display:block; margin-bottom:5px; }
    input, select { width:100%; padding:10px 12px; border:2px solid var(--border);
                    border-radius:8px; font-size:1rem; outline:none;
                    background:#fff; color:var(--text); }
    input:focus, select:focus { border-color:var(--primary); }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .result { margin-top:12px; background:rgba(5,150,105,.1); color:var(--accent);
              padding:7px 12px; border-radius:7px; font-weight:700; font-size:.85rem; }

    /* ── Buttons ── */
    button[type=submit] { background:var(--primary); color:#fff; border:none;
                          border-radius:8px; padding:13px 28px; font-size:1rem;
                          font-weight:600; cursor:pointer; width:100%; margin-top:4px;
                          font-family:'Inter',sans-serif; transition:background .2s; }
    button[type=submit]:hover { background:var(--primary-hover); }

    /* ── Total bar ── */
    .total-bar { background:var(--primary); color:#fff; border-radius:14px;
                 padding:18px 24px; display:flex; justify-content:space-between;
                 align-items:center; font-weight:700; margin-top:12px;
                 box-shadow:0 6px 20px rgba(37,99,235,.35); }
    .total-bar .amt { font-size:1.5rem; }

    /* ── Reference tables ── */
    .table-selector { width:100%; padding:10px 12px; border:2px solid var(--border);
                      border-radius:8px; font-size:1rem; margin-bottom:18px;
                      font-family:'Inter',sans-serif; }
    .ref-table-wrap { overflow-x:auto; border-radius:10px;
                      border:1px solid var(--border); display:none; }
    .ref-table-wrap.show { display:block; }
    table { width:100%; border-collapse:collapse; font-size:.85rem; }
    th { background:var(--bg); color:var(--primary); font-weight:700;
         padding:10px 12px; border-bottom:2px solid var(--border); text-align:left; }
    td { padding:9px 12px; border-bottom:1px solid var(--border); }
    tr:last-child td { border-bottom:none; }

    /* ── PEC note ── */
    .pec-note { background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px;
                padding:12px 16px; font-size:.82rem; color:#1e40af; margin-top:18px; }
    .pec-note strong { display:block; margin-bottom:4px; }

    @media(max-width:520px) { .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>

<!-- Nav bar -->
<div class="navbar">
  <h1>⚡ PEC Load Estimator</h1>
  <span style="font-size:.8rem;color:#64748b;">PEC 2017 · Article 2.20</span>
</div>

<!-- Tab strip -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('calc', this)">📋 Calculator</button>
  <button class="tab-btn"        onclick="switchTab('admin', this)">⚙️ Reference Tables</button>
</div>

<!-- ═══════════════════════════ TAB 1: CALCULATOR ═══════════════════════════ -->
<div id="tab-calc" class="tab-panel active">
  <form method="POST">

    <!-- 1. General Lighting -->
    <div class="card">
      <h3>💡 1. General Lighting</h3>
      <p style="font-size:.8rem;color:#64748b;margin:0 0 12px;">
        PEC Table 2.20.3.3 — 100% on first 3,000 VA · 35% next 117,000 VA · 25% above 120,000 VA
      </p>
      <label>Total Connected VA</label>
      <input type="number" name="lighting_va" value="{{ form.lighting_va }}"
             min="0" step="100" placeholder="e.g. 5000">
      {% if results %}
      <div class="result">Demand: {{ "{:,.0f}".format(results.d_lighting) }} VA</div>
      {% endif %}
    </div>

    <!-- 2. Fixed Appliances (Cooking) -->
    <div class="card">
      <h3>🍳 2. Fixed Appliances (Cooking)</h3>
      <p style="font-size:.8rem;color:#64748b;margin:0 0 12px;">
        PEC Table 2.20.3.16 — demand factor from Col A / B / C based on unit kW rating
      </p>
      <div class="row">
        <div>
          <label>Quantity</label>
          <input type="number" name="qty_fixed" value="{{ form.qty_fixed }}"
                 min="0" max="25" placeholder="0">
        </div>
        <div>
          <label>VA per Unit</label>
          <input type="number" name="fixed_va" value="{{ form.fixed_va }}"
                 min="0" step="100" placeholder="0">
        </div>
      </div>
      {% if results %}
      <div class="result">Demand: {{ "{:,.0f}".format(results.d_fixed) }} VA</div>
      {% endif %}
    </div>

    <!-- 3. Clothes Dryers -->
    <div class="card">
      <h3>🧺 3. Clothes Dryers</h3>
      <p style="font-size:.8rem;color:#64748b;margin:0 0 12px;">
        PEC Table 2.20.3.6 — minimum 5,000 VA per dryer; 100% demand factor
      </p>
      <div class="row">
        <div>
          <label>Quantity</label>
          <input type="number" name="qty_dryer" value="{{ form.qty_dryer }}"
                 min="0" placeholder="0">
        </div>
        <div>
          <label>VA per Unit</label>
          <input type="number" name="dryer_va" value="{{ form.dryer_va }}"
                 min="0" step="100" placeholder="5000">
        </div>
      </div>
      {% if results %}
      <div class="result">Demand: {{ "{:,.0f}".format(results.d_dryer) }} VA</div>
      {% endif %}
    </div>

    <!-- 4. Largest Motor Load -->
    <div class="card">
      <h3>🌀 4. Largest Motor Load</h3>
      <p style="font-size:.8rem;color:#64748b;margin:0 0 12px;">
        PEC Rule — Demand = FLC × Voltage × 1.25 (125% of full-load current)
      </p>
      <div class="row">
        <div>
          <label>Horsepower (HP)</label>
          <select name="motor_hp">
            <option value="none">— None —</option>
            {% for hp in motor_options %}
            <option value="{{ hp }}" {{ 'selected' if form.motor_hp == hp }}>
              {{ hp }} HP
            </option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label>Voltage (V)</label>
          <select name="motor_volts">
            {% for v in volt_options %}
            <option value="{{ v }}" {{ 'selected' if form.motor_volts == v|string }}>
              {{ v }} V
            </option>
            {% endfor %}
          </select>
        </div>
      </div>
      {% if results %}
      <div class="result">Demand: {{ "{:,.2f}".format(results.d_motor) }} VA</div>
      {% endif %}
    </div>

    <button type="submit">CALCULATE DEMAND</button>

    {% if results %}
    <div class="total-bar">
      <span>TOTAL DEMAND</span>
      <span class="amt">{{ "{:,.2f}".format(results.total) }} VA</span>
    </div>
    {% endif %}

    <div class="pec-note">
      <strong>📖 PEC Standard Reference</strong>
      Based on PEC 2017, Part 1, Article 2.20 — Feeder and Service Load Calculations for Dwelling Units.
    </div>

  </form>
</div>

<!-- ═══════════════════════════ TAB 2: REFERENCE TABLES ══════════════════════ -->
<div id="tab-admin" class="tab-panel">
  <div class="card">
    <h3>⚙️ Reference Tables</h3>
    <label>Select Table to View</label>
    <select class="table-selector" onchange="showTable(this.value)">
      <option value="none">— Choose Table —</option>
      <option value="motor">Single-Phase AC Motors (Table t9)</option>
      <option value="lighting">Lighting Demand Factors (Table 2.20.3.3)</option>
      <option value="dryer">Clothes Dryers (Table 2.20.3.6 / t6)</option>
      <option value="cooking">Cooking Appliances (Table 2.20.3.16 / t8)</option>
    </select>

    <!-- Motor table -->
    <div id="ref-motor" class="ref-table-wrap">
      <table>
        <thead><tr><th>HP</th><th>115 V</th><th>200 V</th><th>208 V</th><th>230 V</th></tr></thead>
        <tbody>
          {% for hp, v in motor_table.items() %}
          <tr>
            <td>{{ hp }}</td>
            <td>{{ v[115] }}</td><td>{{ v[200] }}</td>
            <td>{{ v[208] }}</td><td>{{ v[230] }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Lighting demand factors -->
    <div id="ref-lighting" class="ref-table-wrap">
      <table>
        <thead><tr><th>Portion of Lighting Load (VA)</th><th>Demand Factor</th></tr></thead>
        <tbody>
          <tr><td>First 3,000 VA</td><td>100%</td></tr>
          <tr><td>Next 117,000 VA (3,001 – 120,000)</td><td>35%</td></tr>
          <tr><td>Over 120,000 VA</td><td>25%</td></tr>
        </tbody>
      </table>
      <p style="font-size:.78rem;color:#64748b;padding:8px 12px;">
        Source: PEC 2017 Table 2.20.3.3 — applies to general illumination in dwelling units.
        Small appliance and laundry branch-circuit loads may be included.
      </p>
    </div>

    <!-- Clothes dryer table -->
    <div id="ref-dryer" class="ref-table-wrap">
      <table>
        <thead><tr><th>Number of Dryers</th><th>Demand Factor</th></tr></thead>
        <tbody>
          <tr><td>1 – 4</td><td>100%</td></tr>
          <tr><td>5</td><td>80%</td></tr>
          <tr><td>6</td><td>70%</td></tr>
          <tr><td>7</td><td>65%</td></tr>
          <tr><td>8</td><td>60%</td></tr>
          <tr><td>9</td><td>55%</td></tr>
          <tr><td>10 +</td><td>50%</td></tr>
        </tbody>
      </table>
      <p style="font-size:.78rem;color:#64748b;padding:8px 12px;">
        Minimum load per dryer = 5,000 VA (PEC Rule). This calculator uses 100% demand factor
        regardless of quantity — conservative approach for residential estimation.
      </p>
    </div>

    <!-- Cooking appliances table -->
    <div id="ref-cooking" class="ref-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Qty</th>
            <th>Col A — Max Demand (kW)<br><small>(&gt; 8.75 kW units)</small></th>
            <th>Col B — Demand Factor<br><small>(&lt; 3.5 kW units)</small></th>
            <th>Col C — Demand Factor<br><small>(3.5 – 8.75 kW units)</small></th>
          </tr>
        </thead>
        <tbody>
          {% for i in range(1, 26) %}
          <tr>
            <td>{{ i }}</td>
            <td>{{ col_a[i] }} kW</td>
            <td>{{ col_b[i] }}%</td>
            <td>{{ col_c[i] }}%</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

  </div>
</div>

<script>
  // Tab switching — show/hide tab panels and highlight active button
  function switchTab(name, btn) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    btn.classList.add('active');
  }

  // Reference table switcher — show the selected table div
  function showTable(val) {
    ['motor','lighting','dryer','cooking'].forEach(id => {
      document.getElementById('ref-' + id).classList.remove('show');
    });
    if (val !== 'none') {
      document.getElementById('ref-' + val).classList.add('show');
    }
  }

  // If the page loaded with results (POST), keep Calculator tab visible
  // (it's the default active tab so no extra work needed)
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_FORM = {
    "lighting_va": 0,
    "qty_fixed":   0,
    "fixed_va":    0,
    "qty_dryer":   0,
    "dryer_va":    5000,
    "motor_hp":    "none",
    "motor_volts": "230",
}


@app.route("/", methods=["GET", "POST"])
def index():
    """
    GET  — show blank form.
    POST — read inputs, run PEC calculations, render results inline.
    """
    results = None
    form = dict(DEFAULT_FORM)

    if request.method == "POST":
        form["lighting_va"] = request.form.get("lighting_va", 0)
        form["qty_fixed"]   = request.form.get("qty_fixed", 0)
        form["fixed_va"]    = request.form.get("fixed_va", 0)
        form["qty_dryer"]   = request.form.get("qty_dryer", 0)
        form["dryer_va"]    = request.form.get("dryer_va", 5000)
        form["motor_hp"]    = request.form.get("motor_hp", "none")
        form["motor_volts"] = request.form.get("motor_volts", "230")

        d_lighting = calc_lighting(float(form["lighting_va"] or 0))
        d_fixed    = calc_cooking(int(form["qty_fixed"] or 0), float(form["fixed_va"] or 0))
        d_dryer    = calc_dryer(int(form["qty_dryer"] or 0), float(form["dryer_va"] or 0))
        d_motor    = calc_motor(form["motor_hp"], int(form["motor_volts"]))

        class R:
            pass
        r = R()
        for k, v in {"d_lighting": d_lighting, "d_fixed": d_fixed,
                     "d_dryer": d_dryer, "d_motor": d_motor,
                     "total": d_lighting + d_fixed + d_dryer + d_motor}.items():
            setattr(r, k, v)
        results = r

    return render_template_string(
        HTML,
        form=form,
        results=results,
        motor_options=list(MOTOR_TABLE.keys()),
        motor_table=MOTOR_TABLE,
        volt_options=[115, 200, 208, 230],
        col_a=COL_A,
        col_b=COL_B,
        col_c=COL_C,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
