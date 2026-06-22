#!/usr/bin/env python3
"""
auto_status.py - 自动状态感知工具 (V3.5 P4)

功能：
1. 检测 session_start_status.json 是否存在/新鲜
2. 如果不存在（续接会话），自动生成
3. 检测后端/前端/sandbox 健康状态
4. 写一个 combined_status.json 给 AI 读取

使用：
    python auto_status.py          # 检查并刷新
    python auto_status.py --watch  # 监控模式（每 60s 刷新）

输出：
    .trae/debug/session_start_status.json (V3.5 hook 输出)
    .trae/debug/combined_status.json    (本工具输出，更详细)
"""
import sys
import json
import argparse
import time
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


PROJECT_ROOT = Path("D:/filework/excel-to-diagram")
DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
SESSION_STATUS_FILE = DEBUG_DIR / "session_start_status.json"
COMBINED_STATUS_FILE = DEBUG_DIR / "combined_status.json"


def check_port(port: int) -> dict:
    """检查端口是否在监听"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | Select-Object LocalPort,OwningProcess | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                if data:
                    return {"status": "alive", "port": port, "pid": data.get("OwningProcess") if isinstance(data, dict) else data[0].get("OwningProcess")}
            except json.JSONDecodeError:
                pass
        return {"status": "dead", "port": port}
    except Exception as e:
        return {"status": "error", "port": port, "error": str(e)}


def check_session_status_fresh() -> dict:
    """检查 session_start_status.json 是否新鲜（< 10 分钟）"""
    if not SESSION_STATUS_FILE.exists():
        return {"exists": False, "fresh": False, "reason": "not_found"}

    try:
        stat = SESSION_STATUS_FILE.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age_minutes = (datetime.now() - mtime).total_seconds() / 60
        return {
            "exists": True,
            "fresh": age_minutes < 10,
            "age_minutes": round(age_minutes, 1),
            "mtime": mtime.isoformat(),
        }
    except Exception as e:
        return {"exists": True, "fresh": False, "error": str(e)}


def read_session_status() -> dict:
    """读取 session_start_status.json"""
    if not SESSION_STATUS_FILE.exists():
        return {}
    try:
        with open(SESSION_STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def run_sandbox_health_quick() -> dict:
    """快速 sandbox 健康检查（不重新运行 sandbox_health.py）"""
    # 用 cached health report if exists & fresh
    queries_dir = DEBUG_DIR / "queries"
    if queries_dir.exists():
        reports = sorted(queries_dir.glob("sandbox_health_report_*.json"), reverse=True)
        if reports:
            latest = reports[0]
            age_minutes = (time.time() - latest.stat().st_mtime) / 60
            if age_minutes < 5:
                try:
                    with open(latest, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data["cached"] = True
                        data["cache_age_minutes"] = round(age_minutes, 1)
                        return data
                except Exception:
                    pass

    # 否则重新跑 sandbox_health.py
    try:
        result = subprocess.run(
            ["python", str(PROJECT_ROOT / "scripts" / "debug" / "sandbox_health.py")],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT)
        )
        return {
            "raw_output": result.stdout[:500] if result.stdout else "",
            "stderr": result.stderr[:200] if result.stderr else "",
            "exit_code": result.returncode,
            "fresh_check": True,
        }
    except Exception as e:
        return {"error": str(e)}


def generate_combined_status() -> dict:
    """生成 combined status"""
    session_fresh = check_session_status_fresh()
    session_data = read_session_status()

    combined = {
        "timestamp": datetime.now().isoformat(),
        "session_status": {
            "fresh": session_fresh,
            "data": session_data,
        },
        "services": {
            "backend": check_port(3010),
            "frontend": check_port(3004),
        },
        "sandbox": run_sandbox_health_quick(),
        "tips": [],
    }

    # 智能提示
    if not session_fresh.get("fresh", False):
        combined["tips"].append({
            "level": "warn",
            "message": "SessionStart hook 未触发或 status.json 不新鲜（续接会话时常见）",
            "action": "继续工作，下次 SessionStart 时会自动跑 hook"
        })

    if combined["services"]["backend"]["status"] != "alive":
        combined["tips"].append({
            "level": "error",
            "message": "Backend (3010) 未运行",
            "action": "python scripts/debug/safe_query.py restart backend"
        })

    if combined["services"]["frontend"]["status"] != "alive":
        combined["tips"].append({
            "level": "error",
            "message": "Frontend (3004) 未运行",
            "action": "python scripts/debug/safe_query.py restart frontend"
        })

    sandbox_state = combined["sandbox"].get("overall_state", "UNKNOWN")
    if sandbox_state == "BLOCKED":
        combined["tips"].append({
            "level": "critical",
            "message": "Sandbox 完全阻断",
            "action": "建议重启 Trae IDE"
        })
    elif sandbox_state == "DEGRADED":
        combined["tips"].append({
            "level": "info",
            "message": "Sandbox 部分功能受影响",
            "action": "优先使用 safe-output 模式"
        })

    return combined


def main():
    parser = argparse.ArgumentParser(description="Auto status 感知工具")
    parser.add_argument("--watch", action="store_true", help="监控模式")
    parser.add_argument("--interval", type=int, default=60, help="监控间隔（秒）")
    parser.add_argument("--safe-output", action="store_true", help="sandbox-safe 输出")
    args = parser.parse_args()

    if args.watch:
        print(f"[WATCH] Monitoring every {args.interval}s. Ctrl+C to stop.")
        try:
            while True:
                status = generate_combined_status()
                with open(COMBINED_STATUS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(status, f, ensure_ascii=False, indent=2)
                print(f"[{status['timestamp']}] Backend: {status['services']['backend']['status']} | Frontend: {status['services']['frontend']['status']} | Sandbox: {status['sandbox'].get('overall_state', 'UNKNOWN')}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n[WATCH] Stopped.")
            return 0

    # 一次性生成
    status = generate_combined_status()

    if args.safe_output:
        # sandbox-safe: 写文件 + 短消息到 stdout
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = DEBUG_DIR / "queries" / f"combined_status_{timestamp}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        print(f"[SAFE_OUTPUT] {out_path}")
        # 同时写 combined_status.json 作为最新状态缓存
        with open(COMBINED_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        return 0

    # 默认：直接输出
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())