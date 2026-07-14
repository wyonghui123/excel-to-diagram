"""run_security_audit.py - 统一安全审计入口 [V007.67 2026-07-14]
聚合 L2/L4/L5/L7 静态扫描结果, 一键生成安全报告

依据 .trae/rules/remote-execution-simplicity.md (V3):
- L1 禁止 HTTP 127.0.0.1 自调用 log_service
- L2 禁止 base64 + bash -c (yonaa 无 SSH, 必须 HTTP+token+明文)
- L4 禁止 0.0.0.0 绑定 (内网隔离)
- L5 禁止 bash 解密 + 多层嵌套 (木马行为启发式)
- L7 服务器密码不留痕 / 不备份到服务器 / 一次性使用

用法:
  python run_security_audit.py
  python run_security_audit.py --paths tools/ docs/
  python run_security_audit.py --json
  python run_security_audit.py --strict
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# 添加当前目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from check_listen_bind_audit import scan_dir as scan_listen
from check_credential_leak import scan_dir as scan_credential
from check_unsafe_patterns import scan_dir as scan_unsafe


# L6: 各服务端口的安全评估
L6_SERVICE_SECURITY = {
    "9101 (log_service)": {
        "current_measures": [
            "✓ 时变 token (sha256:hour[:16])",
            "✓ 路径白名单 (ALLOWED_DIRS)",
            "✓ 黑名单 (rm -rf, dd, mkfs)",
            "✓ 超时 (default 30s)",
            "✓ 输出截断 (50KB stdout)",
        ],
        "missing": [
            "✗ rate_limit 限流",
            "✗ 路径遍历深度限制 (../)",
            "✗ 请求体大小限制",
        ],
        "priority": "P1",
    },
    "9200 (core_service)": {
        "current_measures": [
            "✓ HTTPS-only",
            "✓ 时变 token",
            "✓ SQL 注入防护 (参数化查询)",
        ],
        "missing": [
            "✗ 验证限流",
            "✗ 请求体大小限制",
        ],
        "priority": "P2",
    },
    "9204 (dbops_service)": {
        "current_measures": [
            "✓ DB 操作走 token",
        ],
        "missing": [
            "✗ 路径白名单",
            "✗ 命令白名单",
            "✗ 限流",
            "✗ 超时",
        ],
        "priority": "P0 (DB 直写, 高危)",
    },
}


def run_all_audits(paths: List[str], strict: bool = False) -> Dict:
    """运行所有审计"""
    start = time.time()
    results = {
        "version": "V007.67",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "paths": paths,
        "audits": {},
        "l6_service_security": L6_SERVICE_SECURITY,
        "duration_sec": 0,
    }

    # L4: 0.0.0.0 绑定审计
    findings_listen = []
    for p in paths:
        path = Path(p)
        if path.exists():
            findings_listen.extend(scan_listen(path))
    results["audits"]["L4_listen_bind"] = {
        "count": len(findings_listen),
        "by_severity": _count_severity(findings_listen),
        "findings": findings_listen[:50],  # top 50
    }

    # L7: 密码留痕
    findings_cred = []
    for p in paths:
        path = Path(p)
        if path.exists():
            findings_cred.extend(scan_credential(path))
    results["audits"]["L7_credential_leak"] = {
        "count": len(findings_cred),
        "by_severity": _count_severity(findings_cred),
        "findings": findings_cred[:50],
    }

    # L2/L5: 不安全模式
    findings_unsafe = []
    for p in paths:
        path = Path(p)
        if path.exists():
            findings_unsafe.extend(scan_unsafe(path))
    results["audits"]["L2_L5_unsafe_patterns"] = {
        "count": len(findings_unsafe),
        "by_severity": _count_severity(findings_unsafe),
        "findings": findings_unsafe[:50],
    }

    # Total
    results["total_findings"] = (
        results["audits"]["L4_listen_bind"]["count"]
        + results["audits"]["L7_credential_leak"]["count"]
        + results["audits"]["L2_L5_unsafe_patterns"]["count"]
    )

    results["duration_sec"] = round(time.time() - start, 2)
    return results


def _count_severity(findings: List[Dict]) -> Dict[str, int]:
    """统计严重级别"""
    by_sev = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        sev = f.get("severity", "?")
        by_sev[sev] = by_sev.get(sev, 0) + 1
    return by_sev


def print_report(results: Dict, strict: bool = False):
    """打印人类可读报告"""
    print("=" * 70)
    print(f"  远程执行 + 安全审计报告 (V3)")
    print(f"  范围: {', '.join(results['paths'])}")
    print(f"  时间: {results['timestamp']}")
    print(f"  耗时: {results['duration_sec']}s")
    print("=" * 70)
    print()

    # L4
    l4 = results["audits"]["L4_listen_bind"]
    print(f"[L4] 0.0.0.0 绑定审计 (外网穿透防护)")
    print(f"     总数: {l4['count']} | P0: {l4['by_severity']['P0']} | "
          f"P1: {l4['by_severity']['P1']} | P2: {l4['by_severity']['P2']}")
    if l4["count"] > 0:
        for f in l4["findings"][:5]:
            print(f"     {f['severity']} {f['file']}:{f['line']}  {f['pattern']}")
        if l4["count"] > 5:
            print(f"     ... +{l4['count']-5} more (use --json for full list)")
    print()

    # L7
    l7 = results["audits"]["L7_credential_leak"]
    print(f"[L7] 密码留痕审计 (凭据保护)")
    print(f"     总数: {l7['count']} | P0: {l7['by_severity']['P0']} | "
          f"P1: {l7['by_severity']['P1']} | P2: {l7['by_severity']['P2']}")
    if l7["count"] > 0:
        for f in l7["findings"][:5]:
            print(f"     {f['severity']} {f['file']}:{f['line']}  {f['pattern']}")
        if l7["count"] > 5:
            print(f"     ... +{l7['count']-5} more")
    print()

    # L2/L5
    l25 = results["audits"]["L2_L5_unsafe_patterns"]
    print(f"[L2+L5] 不安全模式审计 (base64+bash 反模式)")
    print(f"     总数: {l25['count']} | P0: {l25['by_severity']['P0']} | "
          f"P1: {l25['by_severity']['P1']} | P2: {l25['by_severity']['P2']}")
    if l25["count"] > 0:
        for f in l25["findings"][:5]:
            print(f"     {f['severity']} {f['file']}:{f['line']}  {f['pattern']}")
        if l25["count"] > 5:
            print(f"     ... +{l25['count']-5} more")
    print()

    # L6: 服务端口安全
    print("[L6] 服务端口安全评估")
    for port, info in results["l6_service_security"].items():
        print(f"     {port} [{info['priority']}]")
        for m in info["current_measures"]:
            print(f"        {m}")
        for m in info["missing"]:
            print(f"        {m}")
    print()

    # Total
    print("=" * 70)
    print(f"  总结: {results['total_findings']} 个发现")
    if strict:
        print(f"  --strict 模式: P0+P1+P2 任一非零即视为失败")
    else:
        print(f"  默认模式: 仅 P0 视为失败 (P1/P2 建议修复)")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="统一安全审计入口 (L2+L4+L5+L7)")
    parser.add_argument("--paths", nargs="*", default=["tools/", "docs/"],
                        help="扫描路径 (默认 tools/ docs/)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式 (P1+P2 也算失败)")
    args = parser.parse_args()

    results = run_all_audits(args.paths, strict=args.strict)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_report(results, strict=args.strict)

    # Exit code
    total_p0 = sum(
        results["audits"][k]["by_severity"]["P0"]
        for k in results["audits"]
    )
    if total_p0 > 0:
        sys.exit(1)
    if args.strict:
        total_other = sum(
            results["audits"][k]["by_severity"].get("P1", 0)
            + results["audits"][k]["by_severity"].get("P2", 0)
            for k in results["audits"]
        )
        if total_other > 0:
            sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()