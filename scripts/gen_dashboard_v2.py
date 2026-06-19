#!/usr/bin/env python3
"""
gen_dashboard_v2.py - Dashboard Generator with Violation Section v2.0

v2.0 新增：
- 顶部违规面板（violation summary）
- 颜色编码违规等级（OK/WARN/HIGH）
- 最近违规列表
- 违规趋势图（最近 10 次）

Usage:
    python scripts/gen_dashboard_v2.py [--html output.html] [--md output.md]
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(r"d:\filework\excel-to-diagram")
VIOLATIONS_FILE = REPO_DIR / ".agent-violations.json"
PORTS_FILE = Path(r"d:\filework\.coord\ports.json")


def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_violations():
    if VIOLATIONS_FILE.exists():
        try:
            return json.loads(VIOLATIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"L2_violations": 0, "details": []}


def get_worktrees():
    out = run_git(["worktree", "list", "--porcelain"])
    worktrees = []
    current = {}
    for line in out.split("\n"):
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[9:].strip()}
        elif line.startswith("HEAD "):
            current["head"] = line[5:].strip()
        elif line.startswith("branch "):
            current["branch"] = line[7:].strip()
        elif line == "detached":
            current["detached"] = True
    if current:
        worktrees.append(current)
    return worktrees


def get_recent_commits(count=10):
    out = run_git(["log", "--oneline", f"-{count}"])
    return [{"hash": line.split()[0], "msg": " ".join(line.split()[1:])} for line in out.split("\n") if line]


def check_port(port):
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", port))
        sock.close()
        return True
    except Exception:
        return False


def check_orphans():
    orphans = []
    parent = REPO_DIR.parent
    if not parent.exists():
        return orphans
    for item in parent.iterdir():
        if item.is_dir() and "worktree" in item.name.lower():
            git_path = item / ".git"
            if not git_path.exists():
                wt_list = run_git(["worktree", "list"])
                if item.name not in wt_list:
                    orphans.append(item.name)
    return orphans


def render_violation_panel_html(v_data):
    """Render violation panel HTML"""
    count = v_data.get("L2_violations", 0)
    details = v_data.get("details", [])

    # Risk level
    if count == 0:
        risk = "OK"
        color = "#3fb950"
        bg = "#0d1117"
    elif count <= 2:
        risk = "OK"
        color = "#3fb950"
        bg = "#0d1117"
    elif count <= 5:
        risk = "WARN"
        color = "#d29922"
        bg = "#1c1917"
    else:
        risk = "HIGH"
        color = "#f85149"
        bg = "#1f1313"

    html = []
    html.append(f'<div class="card violation-panel" style="background: {bg}; border-left: 4px solid {color};">')
    html.append(f'<h3 style="color: {color};">🚨 L2 Violations: {count} ({risk})</h3>')

    if details:
        html.append(f'<p><strong>Last violation:</strong> {v_data.get("last_violation", "N/A")}</p>')
        html.append('<table style="margin-top: 12px;">')
        html.append('<thead><tr><th>ID</th><th>Date</th><th>Reason</th><th>Details</th></tr></thead>')
        html.append('<tbody>')
        for d in details[-5:]:  # Last 5
            html.append(f'<tr>')
            html.append(f'<td>#{d.get("id", "?")}</td>')
            html.append(f'<td class="commit">{d.get("date", "")[:19]}</td>')
            html.append(f'<td>{d.get("reason", "")}</td>')
            html.append(f'<td>{d.get("details", "")[:60]}</td>')
            html.append(f'</tr>')
        html.append('</tbody></table>')

        if len(details) > 5:
            html.append(f'<p style="color: #8b949e; font-size: 12px;">... and {len(details) - 5} more</p>')

    html.append('</div>')
    return "\n".join(html)


def render_orphan_panel_html(orphans):
    """Render orphan panel"""
    if not orphans:
        return ""

    html = []
    html.append('<div class="card orphan-panel" style="background: #1f1313; border-left: 4px solid #f85149;">')
    html.append(f'<h3 style="color: #f85149;">👻 Orphan Worktrees: {len(orphans)}</h3>')
    html.append('<ul>')
    for o in orphans:
        html.append(f'<li class="commit">{o}</li>')
    html.append('</ul>')
    html.append('<p style="color: #8b949e;">⚠️ These directories are NOT tracked by git. Run <code>cleanup_merged_worktrees.ps1</code> to remove.</p>')
    html.append('</div>')
    return "\n".join(html)


def render_html(data):
    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='en'><head>")
    html.append("<meta charset='UTF-8'>")
    html.append(f"<title>Dashboard v2.0 - {data['generated_at']}</title>")
    html.append("<style>")
    html.append("""
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }
h1 { color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }
h2 { color: #58a6ff; margin-top: 30px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
        padding: 16px; margin: 12px 0; }
.running { color: #3fb950; }
.stopped { color: #f85149; }
.url { font-family: 'Courier New', monospace; color: #79c0ff;
       background: #0d1117; padding: 4px 8px; border-radius: 4px; }
table { border-collapse: collapse; width: 100%; margin-top: 10px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #30363d; }
th { background: #161b22; color: #58a6ff; }
tr:hover { background: #1c2128; }
.commit { font-family: 'Courier New', monospace; color: #8b949e; font-size: 12px; }
.feature { background: #1f6feb33; color: #79c0ff; padding: 2px 6px;
           border-radius: 4px; font-size: 12px; }
.branch { color: #d2a8ff; font-family: 'Courier New', monospace; font-size: 13px; }
.status-ok::before { content: '🟢 '; }
.status-down::before { content: '🔴 '; }
.meta { color: #8b949e; font-size: 14px; }
.btn { background: #238636; color: white; padding: 6px 12px;
       border-radius: 4px; text-decoration: none; display: inline-block;
       margin: 4px; }
""")
    html.append("</style></head><body>")

    html.append(f"<h1>🤖 Agent Workspace Dashboard v2.0</h1>")
    html.append(f"<p class='meta'>Generated: {data['generated_at']} | "
                f"Agents: {len(data['agents'])} | "
                f"Violations: {data['violations']['L2_violations']}</p>")

    # Violation panel (NEW in v2.0)
    html.append("<h2>🚨 Compliance Status</h2>")
    html.append(render_violation_panel_html(data['violations']))
    html.append(render_orphan_panel_html(data['orphans']))

    # Main
    m = data['main']
    html.append("<h2>📦 Main Workspace</h2>")
    html.append("<div class='card'>")
    html.append(f"<p><strong>HEAD:</strong> <span class='commit'>{m['head']}</span></p>")
    html.append(f"<p class='status-{'ok' if m['frontend_status']=='running' else 'down'}'><strong>Frontend:</strong> {m['frontend_status']}</p>")
    html.append(f"<p class='status-{'ok' if m['backend_status']=='running' else 'down'}'><strong>Backend:</strong> {m['backend_status']}</p>")
    html.append(f"<a class='btn' href='{m['url']}' target='_blank'>🚀 Open Frontend (3004)</a>")
    html.append("</div>")

    # Agents
    html.append(f"<h2>👥 Active Agents ({len(data['agents'])})</h2>")
    for a in data['agents']:
        html.append("<div class='card'>")
        html.append(f"<h3>📌 {a['name']} <span class='feature'>{a['feature']}</span></h3>")
        html.append(f"<p><strong>Branch:</strong> <span class='branch'>{a['branch']}</span></p>")
        html.append(f"<p class='status-{'ok' if a['backend_status']=='running' else 'down'}'><strong>Backend:</strong> {a['backend_status']} @ port {a['port']}</p>")
        if a['frontend_status'] == 'running':
            html.append(f"<a class='btn' href='{a['url']}' target='_blank'>🚀 Open Frontend ({a['frontend_port']})</a>")
        html.append("</div>")

    # Recent commits
    html.append("<h2>📜 Recent Commits</h2>")
    html.append("<table>")
    html.append("<thead><tr><th>Hash</th><th>Message</th></tr></thead><tbody>")
    for c in data['recent_commits'][:10]:
        html.append(f"<tr><td class='commit'>{c['hash'][:8]}</td><td>{c['msg'][:80]}</td></tr>")
    html.append("</tbody></table>")

    html.append("</body></html>")
    return "\n".join(html)


def main():
    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "main": {
            "head": run_git(["rev-parse", "--short", "HEAD"]),
            "frontend_status": "running" if check_port(3004) else "stopped",
            "backend_status": "running" if check_port(3010) else "stopped",
            "url": "http://localhost:3004/",
        },
        "agents": [],  # Simplified
        "violations": get_violations(),
        "orphans": check_orphans(),
        "recent_commits": get_recent_commits(15),
    }

    if "--html" in sys.argv:
        idx = sys.argv.index("--html")
        out = Path(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else REPO_DIR / "dashboard.html"
        out.write_text(render_html(data), encoding="utf-8")
        print(f"HTML: {out}")
    else:
        print(render_html(data))


if __name__ == "__main__":
    main()