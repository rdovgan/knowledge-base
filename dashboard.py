import json
import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

MODULES = [
    "mbp-utils", "redis", "parent-dal", "dataaccesslayer",
    "core-module", "channel-integration", "channel-batch-jobs",
    "web-messages", "mbp"
]

RAG_DIR = Path("/home/r.dovgan/cakb/rag")
LOG_FILE = Path("/home/r.dovgan/cakb/logs/pipeline.log")


def get_module_state(module: str) -> dict:
    state_file = RAG_DIR / module / ".state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except:
            pass
    return {"status": "pending", "completed_pages": [], "failed_pages": []}


def get_last_logs(n: int = 20) -> list:
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text().splitlines()
    return [l for l in lines[-200:] if any(x in l for x in
            ["INFO", "ERROR", "WARNING", "completed", "approved",
             "rejected", "failed", "Generating", "Explorer", "chunk"])
            and "LiteLLM" not in l and "Wrapper" not in l
            and "litellm" not in l][-n:]


def is_running() -> tuple:
    import subprocess
    result = subprocess.run(
        ["pgrep", "-f", "run_pipeline.py"],
        capture_output=True, text=True
    )
    pid = result.stdout.strip().split('\n')[0] if result.stdout.strip() else None
    return bool(pid), pid


def get_total_pages() -> int:
    if not RAG_DIR.exists():
        return 0
    return len([f for f in RAG_DIR.rglob("*.md")
                if f.name not in ("index.md", "README.md", "wiki_structure_proposal.md")])


@app.get("/api/status")
def api_status():
    running, pid = is_running()
    modules_data = []
    for m in MODULES:
        state = get_module_state(m)
        modules_data.append({
            "name": m,
            "status": state.get("status", "pending"),
            "completed": len(state.get("completed_pages", [])),
            "failed": len(state.get("failed_pages", [])),
            "completed_pages": state.get("completed_pages", []),
            "failed_pages": state.get("failed_pages", []),
            "completed_at": state.get("completed_at", ""),
        })
    return {
        "running": running,
        "pid": pid,
        "total_pages": get_total_pages(),
        "updated_at": datetime.now().isoformat(),
        "modules": modules_data,
        "logs": get_last_logs(30),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MBP RAG Pipeline</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }
  h1 { font-size: 22px; font-weight: 600; color: #fff; margin-bottom: 4px; }
  .subtitle { color: #888; font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .card { background: #1a1d27; border-radius: 12px; padding: 20px; border: 1px solid #2a2d3a; }
  .card-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .card-value { font-size: 32px; font-weight: 700; color: #fff; }
  .card-value.green { color: #4ade80; }
  .card-value.yellow { color: #fbbf24; }
  .card-value.red { color: #f87171; }
  .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .dot-green { background: #4ade80; box-shadow: 0 0 8px #4ade80; animation: pulse 2s infinite; }
  .dot-red { background: #f87171; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
  .modules { background: #1a1d27; border-radius: 12px; border: 1px solid #2a2d3a; margin-bottom: 24px; overflow: hidden; }
  .modules-header { padding: 16px 20px; border-bottom: 1px solid #2a2d3a; font-weight: 600; font-size: 14px; }
  .module-row { display: grid; grid-template-columns: 180px 130px 80px 80px 1fr; align-items: center; padding: 12px 20px; border-bottom: 1px solid #1e2130; transition: background .15s; }
  .module-row:last-child { border-bottom: none; }
  .module-row:hover { background: #1e2130; }
  .module-name { font-weight: 500; font-size: 14px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .badge-completed { background: #14532d; color: #4ade80; }
  .badge-in_progress { background: #1e3a5f; color: #60a5fa; }
  .badge-pending { background: #1f2937; color: #9ca3af; }
  .badge-failed { background: #450a0a; color: #f87171; }
  .pages-count { font-size: 13px; color: #9ca3af; }
  .pages-count span { color: #4ade80; font-weight: 600; }
  .pages-count .fail { color: #f87171; }
  .progress-bar { height: 6px; background: #2a2d3a; border-radius: 3px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 3px; transition: width .5s; }
  .logs { background: #1a1d27; border-radius: 12px; border: 1px solid #2a2d3a; overflow: hidden; }
  .logs-header { padding: 16px 20px; border-bottom: 1px solid #2a2d3a; font-weight: 600; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
  .logs-body { padding: 16px 20px; font-family: monospace; font-size: 12px; max-height: 320px; overflow-y: auto; }
  .log-line { padding: 2px 0; color: #9ca3af; line-height: 1.6; }
  .log-line.info { color: #9ca3af; }
  .log-line.error { color: #f87171; }
  .log-line.warning { color: #fbbf24; }
  .log-line.success { color: #4ade80; }
  .updated { font-size: 12px; color: #555; }
  .col-header { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: .5px; padding: 8px 20px; display: grid; grid-template-columns: 180px 130px 80px 80px 1fr; border-bottom: 1px solid #2a2d3a; }
</style>
</head>
<body>
<h1>🚀 MBP RAG Pipeline</h1>
<p class="subtitle" id="updated">Loading...</p>

<div class="grid">
  <div class="card">
    <div class="card-label">Pipeline Status</div>
    <div class="card-value" id="pipeline-status">—</div>
  </div>
  <div class="card">
    <div class="card-label">Total Wiki Pages</div>
    <div class="card-value green" id="total-pages">—</div>
  </div>
  <div class="card">
    <div class="card-label">Modules Done</div>
    <div class="card-value" id="modules-done">—</div>
  </div>
</div>

<div class="modules">
  <div class="modules-header">📦 Modules</div>
  <div class="col-header">
    <span>Module</span><span>Status</span><span>Pages</span><span>Failed</span><span>Progress</span>
  </div>
  <div id="modules-list"></div>
</div>

<div class="logs">
  <div class="logs-header">
    <span>📋 Pipeline Logs</span>
    <span class="updated" id="log-updated"></span>
  </div>
  <div class="logs-body" id="logs-body"></div>
</div>

<script>
const MAX_PAGES = { 'mbp-utils':8, 'redis':13, 'parent-dal':10,
  'dataaccesslayer':15, 'core-module':25, 'channel-integration':20,
  'channel-batch-jobs':15, 'web-messages':10, 'mbp':40 };

function logClass(line) {
  if (line.includes('ERROR')) return 'error';
  if (line.includes('WARNING') || line.includes('needs human')) return 'warning';
  if (line.includes('approved') || line.includes('completed') || line.includes('✅')) return 'success';
  return 'info';
}

async function refresh() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    // Header
    const running = d.running;
    document.getElementById('pipeline-status').innerHTML =
      `<span class="status-dot ${running ? 'dot-green' : 'dot-red'}"></span>${running ? 'Running' : 'Stopped'}`;
    document.getElementById('pipeline-status').className = 'card-value ' + (running ? 'green' : 'red');
    document.getElementById('total-pages').textContent = d.total_pages;
    document.getElementById('updated').textContent = 'Updated: ' + new Date(d.updated_at).toLocaleTimeString();

    const done = d.modules.filter(m => m.status === 'completed').length;
    document.getElementById('modules-done').textContent = done + ' / ' + d.modules.length;

    // Modules
    const list = document.getElementById('modules-list');
    list.innerHTML = d.modules.map(m => {
      const max = MAX_PAGES[m.name] || 10;
      const pct = Math.min(100, Math.round((m.completed / max) * 100));
      const color = m.status === 'completed' ? '#4ade80' :
                    m.status === 'in_progress' ? '#60a5fa' :
                    m.status === 'failed' ? '#f87171' : '#374151';
      return `<div class="module-row">
        <div class="module-name">${m.name}</div>
        <div><span class="badge badge-${m.status}">${m.status.replace('_',' ')}</span></div>
        <div class="pages-count"><span>${m.completed}</span></div>
        <div class="pages-count"><span class="${m.failed > 0 ? 'fail' : ''}">${m.failed}</span></div>
        <div>
          <div class="progress-bar">
            <div class="progress-fill" style="width:${pct}%;background:${color}"></div>
          </div>
        </div>
      </div>`;
    }).join('');

    // Logs
    const logsEl = document.getElementById('logs-body');
    const wasAtBottom = logsEl.scrollHeight - logsEl.clientHeight <= logsEl.scrollTop + 10;
    logsEl.innerHTML = d.logs.map(l =>
      `<div class="log-line ${logClass(l)}">${l}</div>`
    ).join('');
    if (wasAtBottom) logsEl.scrollTop = logsEl.scrollHeight;
    document.getElementById('log-updated').textContent = new Date().toLocaleTimeString();

  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
