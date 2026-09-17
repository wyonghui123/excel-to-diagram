"""
wt 启动时间探测 - 自适应超时 (R8)

原理：
- 第一次启动 wt 后端，测量真实启动时间 T_real
- 把 T_real 上浮 20% 后写回 paths.json → self_verify.backend_startup_timeout
- 后续启动使用自适应超时，避免 false-fail 或 慢启动浪费 token

用法：
  python scripts/_wt_startup_probe.py <wt-name>        # 探测 + 学习 + 写入
  python scripts/_wt_startup_probe.py <wt-name> --reset   # 重置为默认 60s
  python scripts/_wt_startup_probe.py <wt-name> --show    # 仅查看当前值

安装 (可选):
  添加到 agent-bootstrap 自动跑一次
"""
import argparse, json, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _ports_sync import load_ports  # 用 port registry 解析端口


def measure_startup(wt_name: str) -> float:
    """测量 wt 后端启动时间，返回秒"""
    ports = load_ports()
    backend_port = None
    for p_str, info in ports.get('allocated', {}).items():
        if info.get('owner') == wt_name:
            backend_port = int(p_str)
            break
    if not backend_port:
        # 在 persistent 段找
        for p_str, info in ports.get('persistent', {}).items():
            if info.get('owner') == wt_name:
                backend_port = info.get('backend_port') or int(p_str)
                break
    if not backend_port:
        print(f'  [ERROR] wt {wt_name} 未注册端口')
        return -1

    cmd = [sys.executable, str(Path(__file__).parent / '_wt_service.py'),
           'start-be', wt_name]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        print(f'  [WARN] 启动失败: {r.stderr[:200]}')
        return -1

    elapsed = time.time() - t0
    print(f'  [OK] {wt_name} 后端启动用时: {elapsed:.1f}s')

    # 健康检查确认
    try:
        req = urllib.request.Request(f'http://localhost:{backend_port}/api/v1/health')
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f'  [OK] /api/v1/health 返回 {resp.status}')
    except Exception as e:
        print(f'  [WARN] 启动后健康检查失败: {e}')

    return elapsed


def update_paths(wt_name: str, measured_seconds: float, margin: float = 1.2):
    """更新 paths.json 的 self_verify 超时配置"""
    paths_file = Path(r'D:/filework/.coord/paths.json')

    sys.path.insert(0, str(Path(__file__).parent))
    from _config_backup import backup as _backup
    _backup(str(paths_file))

    paths = json.loads(paths_file.read_text(encoding='utf-8'))
    sv_cfg = paths.setdefault('self_verify', {
        'backend_startup_timeout': 60,
        'frontend_startup_timeout': 30,
        'api_smoke_endpoints': ['/api/v1/health', '/api/v1/products'],
    })

    old = sv_cfg.get('backend_startup_timeout', 60)
    new = max(60, int(measured_seconds * margin))
    if new < 30:
        new = 60  # 保底 60s, 不要太快导致误判

    sv_cfg['backend_startup_timeout'] = new
    # 记录每个 wt 的历史测量（可分析分布）
    history = sv_cfg.setdefault('startup_history', [])
    history.append({
        'wt_name': wt_name,
        'measured_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'seconds': round(measured_seconds, 1),
        'configured_timeout': new,
    })
    # 保留最近 20 条
    if len(history) > 20:
        sv_cfg['startup_history'] = history[-20:]

    paths_file.write_text(json.dumps(paths, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  ✓ paths.json: backend_startup_timeout: {old} -> {new}')


def show_current():
    """查看当前配置"""
    paths_file = Path(r'D:/filework/.coord/paths.json')
    paths = json.loads(paths_file.read_text(encoding='utf-8'))
    sv_cfg = paths.get('self_verify', {})
    print(f'  当前配置:')
    print(f'    backend_startup_timeout:  {sv_cfg.get("backend_startup_timeout")}s')
    print(f'    frontend_startup_timeout: {sv_cfg.get("frontend_startup_timeout")}s')
    print(f'    api_smoke_endpoints: {len(sv_cfg.get("api_smoke_endpoints", []))} 个')
    history = sv_cfg.get('startup_history', [])
    if history:
        print(f'  最近启动历史 (最近 {len(history)} 条):')
        for h in history[-5:]:
            print(f'    {h["wt_name"]}: {h["seconds"]}s, timeout={h["configured_timeout"]}s ({h["measured_at"]})')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('wt_name', nargs='?', help='wt 名称')
    p.add_argument('--reset', action='store_true', help='重置为默认 60s')
    p.add_argument('--show', action='store_true', help='仅查看当前配置')
    p.add_argument('--margin', type=float, default=1.2, help='测量值 * margin = 配置值 (默认 1.2)')
    args = p.parse_args()

    if args.show or not args.wt_name:
        show_current()
        if not args.wt_name:
            return

    if args.reset:
        paths_file = Path(r'D:/filework/.coord/paths.json')
        from _config_backup import backup as _backup
        _backup(str(paths_file))
        paths = json.loads(paths_file.read_text(encoding='utf-8'))
        sv_cfg = paths.setdefault('self_verify', {})
        sv_cfg['backend_startup_timeout'] = 60
        paths_file.write_text(json.dumps(paths, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'  ✓ 重置为 60s')
        return

    elapsed = measure_startup(args.wt_name)
    if elapsed < 0:
        return 1
    update_paths(args.wt_name, elapsed, args.margin)


if __name__ == '__main__':
    main()
