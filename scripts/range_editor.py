#!/usr/bin/env python3
"""Local web UI for editing poker range charts. Run and open http://localhost:8080"""
import json, os, sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import io

ROOT = Path(__file__).parent.parent
RANGES_DIR = ROOT / "data" / "ranges"
CROP_DIR = Path("/tmp/rc_crops")

RANKS = "AKQJT98765432"
PDF_CONFIGS = {
    "6max_100bb_highRake": ["UTG", "MP", "CO", "BTN", "SB"],
    "6max_100bb": ["UTG", "MP", "CO", "BTN", "SB"],
    "6max_40bb": ["UTG", "MP", "CO", "BTN", "SB"],
    "6max_200bb": ["UTG", "MP", "CO", "BTN", "SB"],
    "9max_100bb": ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB"],
    "mtt_100bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_60bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_50bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_40bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_30bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_20bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
    "mtt_10bb": ["UTG", "UTG+1", "MP", "HJ", "CO", "BTN", "SB"],
}

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Range Editor</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui; background: #1a1a2e; color: #eee; display:flex; height:100vh; }
#sidebar { width: 220px; padding: 12px; background: #16213e; overflow-y: auto; }
#sidebar select, #sidebar button { width:100%; margin:4px 0; padding:6px; border-radius:4px; border:1px solid #555; background:#0f3460; color:#eee; font-size:13px; cursor:pointer; }
#sidebar button:hover { background:#1a5276; }
#sidebar button.save { background:#27ae60; font-weight:bold; }
#sidebar button.save:hover { background:#2ecc71; }
#main { flex:1; display:flex; gap:12px; padding:12px; overflow:auto; }
#crop-container { flex:0 0 auto; }
#crop-container img { max-height: calc(100vh - 24px); width: auto; border-radius: 4px; }
#grid-container { flex:0 0 auto; }
table { border-collapse: separate; border-spacing: 2px; }
td { width:52px; height:42px; text-align:center; font-size:11px; font-weight:600; cursor:pointer;
     border-radius:4px; user-select:none; transition: transform 0.1s; color:#fff; text-shadow:0 1px 2px rgba(0,0,0,0.5); }
td:hover { transform:scale(1.08); z-index:1; }
td.raise { background: #e38214; }
td.fold { background: #27819f; }
td.call { background: #40906c; }
td.allin { background: #a41616; }
td.mixed-major { background: linear-gradient(135deg, #e38214 75%, #27819f 25%); }
td.mixed-half { background: linear-gradient(135deg, #e38214 50%, #27819f 50%); }
td.mixed-minor { background: linear-gradient(135deg, #e38214 25%, #27819f 75%); }
td.header { background: #2c3e50; cursor:default; font-size:13px; }
td.header:hover { transform:none; }
#stats { margin-top:10px; font-size:12px; line-height:1.6; color:#aaa; }
#stats b { color:#eee; }
#tool { margin-top:10px; }
#tool label { display:block; margin:3px 0; cursor:pointer; padding:4px 8px; border-radius:4px; font-size:13px; }
#tool label:hover { background:#1a3a5c; }
#tool input[type=radio] { margin-right:6px; }
.active-tool { background:#0f3460 !important; }
#changes { margin-top:8px; font-size:11px; color:#e74c3c; }
</style></head><body>
<div id="sidebar">
  <h3 style="margin:0 0 8px">Range Editor</h3>
  <div id="nav-label" style="font-size:14px;font-weight:bold;margin:8px 0;text-align:center;color:#f39c12"></div>
  <div style="display:flex;gap:4px">
    <button onclick="navPrev()" style="flex:1">← Prev</button>
    <button onclick="navNext()" style="flex:1">Next →</button>
  </div>
  <select id="fmt" onchange="loadPositions()" style="display:none"></select>
  <select id="pos" onchange="loadRange()" style="display:none"></select>
  <div id="tool">
    <label style="font-size:12px;font-weight:bold">Paint tool:</label>
    <label class="active-tool"><input type="radio" name="tool" value="raise" checked> 🟠 Raise</label>
    <label><input type="radio" name="tool" value="fold"> 🔵 Fold</label>
    <label><input type="radio" name="tool" value="call"> 🟢 Call</label>
    <label><input type="radio" name="tool" value="allin"> 🔴 Allin</label>
    <label><input type="radio" name="tool" value="mixed-major"> 🔶 Mixed 75%</label>
    <label><input type="radio" name="tool" value="mixed-half"> 🔶 Mixed 50%</label>
    <label><input type="radio" name="tool" value="mixed-minor"> 🔶 Mixed 25%</label>
  </div>
  <div id="stats"></div>
  <button class="save" onclick="saveRange()" style="margin-top:12px">Save JSON</button>
  <div id="changes"></div>
</div>
<div id="main">
  <div id="crop-container"><img id="crop-img" src=""></div>
  <div id="grid-container"><table id="grid"></table></div>
</div>
<script>
const RANKS = "AKQJT98765432";
const CONFIGS = PLACEHOLDER_CONFIGS;
let cellData = {};  // hand -> action
let originalData = {};
let isDragging = false;

// Build flat list of all (fmt, pos) pairs
const ALL_SLOTS = [];
for(const [fmt, positions] of Object.entries(CONFIGS)) {
  for(const pos of positions) ALL_SLOTS.push({fmt, pos});
}
let currentSlot = 0;

// Init (hidden selects for internal use)
const fmtSel = document.getElementById('fmt');
const posSel = document.getElementById('pos');
Object.keys(CONFIGS).forEach(k => { const o=document.createElement('option'); o.value=k; o.text=k; fmtSel.add(o); });

function navTo(idx) {
  currentSlot = ((idx % ALL_SLOTS.length) + ALL_SLOTS.length) % ALL_SLOTS.length;
  const s = ALL_SLOTS[currentSlot];
  fmtSel.value = s.fmt;
  loadPositions(true);
  posSel.value = s.pos;
  document.getElementById('nav-label').textContent = `${s.fmt} / ${s.pos}  (${currentSlot+1}/${ALL_SLOTS.length})`;
  loadRange();
}
function navPrev() { navTo(currentSlot - 1); }
function navNext() { navTo(currentSlot + 1); }

// Keyboard shortcuts: left/right arrows
document.addEventListener('keydown', (e) => {
  if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT') return;
  if(e.key==='ArrowLeft') navPrev();
  else if(e.key==='ArrowRight') navNext();
});

navTo(0);

// Tool selection
document.querySelectorAll('#tool input[type=radio]').forEach(r => {
  r.addEventListener('change', () => {
    document.querySelectorAll('#tool label').forEach(l => l.classList.remove('active-tool'));
    r.parentElement.classList.add('active-tool');
  });
});

function handAt(r, c) {
  const r1=RANKS[r], r2=RANKS[c];
  if(r<c) return r1+r2+'s';
  if(r>c) return r2+r1+'o';
  return r1+r2;
}

function comboWeight(h) {
  if(h.length===2) return 6;
  return h.endsWith('s') ? 4 : 12;
}

function loadPositions(silent) {
  const fmt = fmtSel.value;
  posSel.innerHTML = '';
  (CONFIGS[fmt]||[]).forEach(p => { const o=document.createElement('option'); o.value=p; o.text=p; posSel.add(o); });
  if(!silent) loadRange();
}

async function loadRange() {
  const fmt=fmtSel.value, pos=posSel.value;
  if(!fmt||!pos) return;
  // Load crop image
  document.getElementById('crop-img').src = `/crop/${fmt}/${pos}`;
  // Load JSON data
  try {
    const resp = await fetch(`/data/${fmt}/${pos}`);
    const data = await resp.json();
    cellData = {};
    // Mark all as fold first
    for(let r=0;r<13;r++) for(let c=0;c<13;c++) cellData[handAt(r,c)]='fold';
    // Apply data
    (data.raise||[]).forEach(h => cellData[h]='raise');
    (data.allin||[]).forEach(h => cellData[h]='allin');
    (data.call||[]).forEach(h => cellData[h]='call');
    const mixed = data.mixed||{};
    if(typeof mixed==='object' && !Array.isArray(mixed)) {
      Object.entries(mixed).forEach(([h,pct]) => {
        if(pct >= 0.625) cellData[h]='mixed-major';
        else if(pct >= 0.375) cellData[h]='mixed-half';
        else cellData[h]='mixed-minor';
      });
    } else {
      (mixed||[]).forEach(h => cellData[h]='mixed-half');
    }
    originalData = {...cellData};
  } catch(e) {
    cellData = {};
    for(let r=0;r<13;r++) for(let c=0;c<13;c++) cellData[handAt(r,c)]='fold';
    originalData = {...cellData};
  }
  renderGrid();
}

function renderGrid() {
  const table = document.getElementById('grid');
  table.innerHTML = '';
  // Header row
  let tr = document.createElement('tr');
  let th = document.createElement('td'); th.className='header'; th.textContent=''; tr.appendChild(th);
  for(let c=0;c<13;c++) { th=document.createElement('td'); th.className='header'; th.textContent=RANKS[c]; tr.appendChild(th); }
  table.appendChild(tr);
  // Data rows
  for(let r=0;r<13;r++) {
    tr = document.createElement('tr');
    th = document.createElement('td'); th.className='header'; th.textContent=RANKS[r]; tr.appendChild(th);
    for(let c=0;c<13;c++) {
      const hand = handAt(r,c);
      const td = document.createElement('td');
      td.textContent = hand;
      td.className = cellData[hand]||'fold';
      td.dataset.hand = hand;
      td.addEventListener('mousedown', (e) => { isDragging=true; paintCell(td); e.preventDefault(); });
      td.addEventListener('mouseenter', () => { if(isDragging) paintCell(td); });
      tr.appendChild(td);
    }
    table.appendChild(tr);
  }
  document.addEventListener('mouseup', ()=>isDragging=false);
  updateStats();
}

function paintCell(td) {
  const tool = document.querySelector('#tool input[type=radio]:checked').value;
  const hand = td.dataset.hand;
  cellData[hand] = tool;
  td.className = tool;
  updateStats();
}

function updateStats() {
  let counts = {raise:0, fold:0, call:0, allin:0, 'mixed-major':0, 'mixed-half':0, 'mixed-minor':0};
  let combos = {raise:0, fold:0, call:0, allin:0, 'mixed-major':0, 'mixed-half':0, 'mixed-minor':0};
  for(const [h,a] of Object.entries(cellData)) { counts[a]=(counts[a]||0)+1; combos[a]=(combos[a]||0)+comboWeight(h); }
  const total = 1326;
  const mxCnt = (counts['mixed-major']||0)+(counts['mixed-half']||0)+(counts['mixed-minor']||0);
  const mxCombo = (combos['mixed-major']||0)+(combos['mixed-half']||0)+(combos['mixed-minor']||0);
  // Effective raise combos: raise + allin + mixed weighted
  const effRaise = (combos.raise||0) + (combos.allin||0) + (combos['mixed-major']||0)*0.75 + (combos['mixed-half']||0)*0.5 + (combos['mixed-minor']||0)*0.25;
  const statsDiv = document.getElementById('stats');
  statsDiv.innerHTML = `
    <b>Hands / Combos:</b><br>
    🟠 Raise: ${counts.raise||0} / ${combos.raise||0} (${((combos.raise||0)/total*100).toFixed(1)}%)<br>
    🔵 Fold: ${counts.fold||0} / ${combos.fold||0} (${((combos.fold||0)/total*100).toFixed(1)}%)<br>
    🟢 Call: ${counts.call||0} / ${combos.call||0} (${((combos.call||0)/total*100).toFixed(1)}%)<br>
    🔴 Allin: ${counts.allin||0} / ${combos.allin||0} (${((combos.allin||0)/total*100).toFixed(1)}%)<br>
    🔶 Mixed: ${mxCnt} / ${mxCombo} (75%:${counts['mixed-major']||0} 50%:${counts['mixed-half']||0} 25%:${counts['mixed-minor']||0})<br>
    <b style="color:#f39c12">Eff. Raise: ${effRaise.toFixed(0)} combos (${(effRaise/total*100).toFixed(1)}%)</b>
  `;
  // Show changes
  let changed = 0;
  for(const h of Object.keys(cellData)) { if(cellData[h]!==originalData[h]) changed++; }
  document.getElementById('changes').textContent = changed ? `${changed} cells changed` : '';
}

async function saveRange() {
  const fmt=fmtSel.value, pos=posSel.value;
  const result = {raise:[], allin:[], call:[], mixed:{}};
  for(const [h,a] of Object.entries(cellData)) {
    if(a==='raise') result.raise.push(h);
    else if(a==='allin') result.allin.push(h);
    else if(a==='call') result.call.push(h);
    else if(a==='mixed-major') result.mixed[h] = 0.75;
    else if(a==='mixed-half') result.mixed[h] = 0.5;
    else if(a==='mixed-minor') result.mixed[h] = 0.25;
  }
  result.pct_raise = +(result.raise.length/169*100).toFixed(2);
  if(result.allin.length) result.pct_allin = +(result.allin.length/169*100).toFixed(2);
  else delete result.allin;
  if(result.call.length) result.pct_call = +(result.call.length/169*100).toFixed(2);
  else delete result.call;
  if(!Object.keys(result.mixed).length) delete result.mixed;

  const resp = await fetch(`/save/${fmt}/${pos}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(result)});
  if(resp.ok) {
    originalData = {...cellData};
    document.getElementById('changes').textContent = 'Saved!';
    document.getElementById('changes').style.color = '#27ae60';
    setTimeout(()=>{document.getElementById('changes').style.color='#e74c3c';}, 2000);
  }
}
</script></body></html>"""


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '/index.html':
            html = HTML.replace('PLACEHOLDER_CONFIGS', json.dumps(PDF_CONFIGS))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())

        elif path.startswith('/crop/'):
            parts = path.split('/')
            fmt, pos = parts[2], parts[3]
            crop_path = CROP_DIR / f"{fmt}_rfi_{pos}.png"
            if not crop_path.exists():
                # Try data/crops
                crop_path = ROOT / "data" / "crops" / f"{fmt}_rfi_{pos}.png"
            if crop_path.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.end_headers()
                self.wfile.write(crop_path.read_bytes())
            else:
                self.send_error(404, f"Crop not found: {crop_path}")

        elif path.startswith('/data/'):
            parts = path.split('/')
            fmt, pos = parts[2], parts[3]
            json_path = RANGES_DIR / fmt / "rfi" / f"{pos}.json"
            if json_path.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json_path.read_bytes())
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{}')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/save/'):
            parts = self.path.split('/')
            fmt, pos = parts[2], parts[3]
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            out_dir = RANGES_DIR / fmt / "rfi"
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / f"{pos}.json", 'w') as f:
                json.dump(data, f)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Range Editor running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
