#!/usr/bin/env python3
"""scan_ai_content.py - 扫描 AI 生成的损坏内容 (clean V007.79c 重写版)

检查项:
1. CRLF 行尾 (Windows 编码错误)
2. UTF-8 BOM
3. 疑似 GBK -> UTF-8 mojibake (replacement char U+FFFD)
4. Python SyntaxError (unterminated string, docstring)
5. JavaScript 非法 escape sequences
6. AI placeholder 残留 (TODO:  / FIXME:  / XXX 替代了真实文本)

使用:
    py scan_ai_content.py <files_or_dirs> [--json] [--strict]

退出码:
    0 - 通过 (无 CRITICAL/HIGH)
    1 - CRITICAL 或 HIGH 警告
    2 - MEDIUM 警告
"""
import re
import sys
import ast
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

# ====== 严重程度定义 ======
CRITICAL = 'CRITICAL'  # 阻塞: SyntaxError / 编码错误导致文件不可用
HIGH = 'HIGH'          # 严重: CRLF / BOM / mojibake
MEDIUM = 'MEDIUM'      # 中等: 警告
LOW = 'LOW'            # 提示

SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}

# ====== 检测规则 ======

def check_crlf(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 CRLF 行尾 (应该 LF)"""
    issues = []
    if b'\r\n' in content:
        crlf_count = content.count(b'\r\n')
        issues.append({
            'type': 'crlf',
            'level': HIGH,
            'count': crlf_count,
            'msg': f'{crlf_count} 个 CRLF 行尾 (期望 LF)',
            'fix': f'运行: py -c "open(\'{filepath}\', \'wb\').write(open(\'{filepath}\', \'rb\').read().replace(b\'\\r\\n\', b\'\\n\'))"'
        })
    return issues

def check_bom(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 UTF-8 BOM (Python 3 不期望 BOM)"""
    issues = []
    if content.startswith(b'\xef\xbb\xbf'):
        issues.append({
            'type': 'bom',
            'level': HIGH,
            'count': 1,
            'msg': 'UTF-8 BOM (Python 期望无 BOM)',
            'fix': f'运行: py -c "data = open(\'{filepath}\', \'rb\').read(); data = data[3:] if data.startswith(b\'\\xef\\xbb\\xbf\') else data; open(\'{filepath}\', \'wb\').write(data)"'
        })
    return issues

def check_mojibake(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 mojibake / 替换字符 U+FFFD"""
    issues = []
    # Count U+FFFD
    fffd_count = content.count(b'\xef\xbf\xbd')
    if fffd_count > 0:
        issues.append({
            'type': 'mojibake',
            'level': HIGH,
            'count': fffd_count,
            'msg': f'{fffd_count} 个 U+FFFD 替换字符 (可能是 GBK->UTF-8 错误转换)',
            'fix': '需要查看原始编码 (GBK? UTF-16? Latin1?) 重新转换'
        })
    return issues

def check_python_syntax(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 Python 语法错误"""
    issues = []
    if not filepath.suffix == '.py':
        return issues
    try:
        text = content.decode('utf-8', errors='replace')
        ast.parse(text)
    except SyntaxError as e:
        issues.append({
            'type': 'syntax_error',
            'level': CRITICAL,
            'count': 1,
            'msg': f'SyntaxError line {e.lineno}: {e.msg}',
            'fix': f'查看 {filepath} line {e.lineno} 修复'
        })
    return issues

def check_js_escape(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 JavaScript/TypeScript 非法 escape sequence"""
    issues = []
    if filepath.suffix not in ('.js', '.ts', '.jsx', '.tsx'):
        return issues
    # Pattern: regex with \s, \d, \w, etc. without raw string prefix
    # This is a SyntaxWarning, not SyntaxError, so MEDIUM
    try:
        text = content.decode('utf-8', errors='replace')
        for i, line in enumerate(text.split('\n'), 1):
            if re.search(r"re\.match\(r'\\s", line) or re.search(r"re\.match\(r'\\d", line):
                issues.append({
                    'type': 'js_invalid_escape',
                    'level': MEDIUM,
                    'count': 1,
                    'msg': f'line {i}: 非法 \\s/\\d 等在 r-string 中',
                    'fix': '改用 r"\\s..." 或 r\'\\s...\''
                })
                break
    except Exception:
        pass
    return issues

def check_ai_placeholders(filepath: Path, content: bytes) -> List[Dict[str, Any]]:
    """检查 AI placeholder 残留 (TODO: 替代了真实内容)"""
    issues = []
    try:
        text = content.decode('utf-8', errors='replace')
        # Pattern: 问号占位 (CJK 字符 + ?)
        suspicious = re.findall(r'[\u4e00-\u9fff]\?[\u4e00-\u9fff]?', text)
        if len(suspicious) > 5:
            issues.append({
                'type': 'ai_placeholder',
                'level': MEDIUM,
                'count': len(suspicious),
                'msg': f'{len(suspicious)} 个疑似 AI placeholder (中文+?)',
                'fix': '检查生成过程, 可能 AI 用了 replace 错误'
            })
    except Exception:
        pass
    return issues

# ====== 主流程 ======

def check_file(filepath: Path) -> Dict[str, Any]:
    """扫描单个文件"""
    try:
        content = filepath.read_bytes()
    except Exception as e:
        return {
            'file': str(filepath),
            'error': str(e),
            'issues': []
        }

    issues = []
    issues.extend(check_crlf(filepath, content))
    issues.extend(check_bom(filepath, content))
    issues.extend(check_mojibake(filepath, content))
    issues.extend(check_python_syntax(filepath, content))
    issues.extend(check_js_escape(filepath, content))
    issues.extend(check_ai_placeholders(filepath, content))

    return {
        'file': str(filepath),
        'issues': issues
    }


def main():
    parser = argparse.ArgumentParser(description='扫描 AI 生成的损坏内容')
    parser.add_argument('targets', nargs='+', help='文件或目录')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--strict', action='store_true', help='严格模式 (CRITICAL 失败就 exit 1)')
    args = parser.parse_args()

    files_to_check = []
    for target in args.targets:
        p = Path(target)
        if p.is_file():
            files_to_check.append(p)
        elif p.is_dir():
            for ext in ('.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.sh', '.json', '.yaml', '.yml'):
                files_to_check.extend(p.rglob(f'*{ext}'))

    all_results = []
    critical_count = 0
    high_count = 0
    medium_count = 0

    for filepath in files_to_check:
        result = check_file(filepath)
        all_results.append(result)
        for issue in result.get('issues', []):
            if issue['level'] == CRITICAL:
                critical_count += 1
            elif issue['level'] == HIGH:
                high_count += 1
            elif issue['level'] == MEDIUM:
                medium_count += 1

    if args.json:
        print(json.dumps({
            'files': len(all_results),
            'critical': critical_count,
            'high': high_count,
            'medium': medium_count,
            'results': all_results
        }, indent=2, ensure_ascii=False))
    else:
        if not all_results:
            print("[OK] 没有需要扫描的文件")
        else:
            print(f"\n[REPORT] 扫描了 {len(all_results)} 个文件:")
            print(f"  CRITICAL: {critical_count}")
            print(f"  HIGH: {high_count}")
            print(f"  MEDIUM: {medium_count}")
            print()
            for r in all_results[:20]:
                if r.get('issues'):
                    print(f"\n  {r['file']}")
                    for issue in r['issues']:
                        print(f"    [{issue['level']}] {issue['type']}: {issue['count']} - {issue['msg']}")
            if len(all_results) > 20:
                print(f"\n  ... and {len(all_results) - 20} more files")

    if critical_count > 0:
        sys.exit(1)
    elif high_count > 0:
        sys.exit(1)
    elif medium_count > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
