"""V007.86d fix_bat_encoding.py - 修复 .bat 文件编码 (ASCII + LF)

V007.86d 教训 (V007.86c):
- .bat 文件有中文 + CRLF → PowerShell GBK decode 失败 → exit 9009
- 修复: 改 ASCII only (用英文), 改 CRLF → LF

V007.86d fix 工具:
- 扫描所有 .bat/.cmd
- 报告中文 / CRLF / BOM
- 转换中文 → 英文 placeholder (e.g. 测试 -> [TEST])
- 转换 CRLF → LF
- 去掉 BOM
"""
import re
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# Common Chinese -> English placeholder mapping
CN_TO_EN = {
    # 测试 / 跑 / 检查
    '测试': 'test', '运行': 'run', '检查': 'check', '执行': 'exec',
    '失败': 'fail', '成功': 'success', '状态': 'status', '结果': 'result',
    # 类型
    '类型': 'type', '单元': 'unit', '集成': 'integration', '性能': 'perf',
    '所有': 'all', '默认': 'default', '仅运行': 'only-run', '覆盖率': 'coverage',
    # 数量 / 范围
    '全量': 'full', '只': 'only', '的': '', '跑': 'run',
    # 完成 / 报告
    '完成': 'done', '完': 'done', '生成': 'gen', '报告': 'report',
    '并': 'and', '生': 'gen', '成': 'gen', '告': '',
    # 选项 / 用法
    '选项': 'option', '用法': 'usage', '无参数': 'no-arg', '参数': 'arg',
    '根据': 'based-on', '决定': 'decide', '持续': 'continuous', '监控': 'monitor',
    '查看': 'view', '重跑': 'rerun', '智能': 'smart', '快捷方式': 'shortcut',
    '版本': 'version', '脚本': 'script', '运行测试': 'run-tests',
    # 标点
    '（': '(', '）': ')', '，': ',', '。': '.', '：': ':',
    # 通用
    '强制使用最佳实践': 'force-best-practice',
    '报告已生成': 'report-generated',
}


def cn_to_en(text: str) -> str:
    """Convert Chinese to English placeholder (sort by length, longest first)"""
    # Sort by length to avoid partial replacements
    for cn, en in sorted(CN_TO_EN.items(), key=lambda x: -len(x[0])):
        text = text.replace(cn, en)
    return text


def fix_bat_file(filepath: str, dry_run: bool = False) -> dict:
    """Fix a single .bat file

    Returns:
        {
          'bom_removed': bool,
          'crlf_to_lf': int (count of CRLF -> LF),
          'cn_to_en_count': int (chars converted),
          'original_size': int,
          'fixed_size': int,
        }
    """
    result = {
        'bom_removed': False,
        'crlf_to_lf': 0,
        'cn_to_en_count': 0,
        'original_size': 0,
        'fixed_size': 0,
    }

    if not os.path.exists(filepath):
        print(f'  [SKIP] File not found: {filepath}')
        return result

    with open(filepath, 'rb') as f:
        data = f.read()

    result['original_size'] = len(data)

    # 1. Remove UTF-8 BOM
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
        result['bom_removed'] = True

    # 2. CRLF -> LF
    crlf_count = data.count(b'\r\n')
    if crlf_count > 0:
        data = data.replace(b'\r\n', b'\n')
        result['crlf_to_lf'] = crlf_count

    # 3. Chinese -> English
    try:
        text = data.decode('utf-8')
    except Exception:
        text = data.decode('gbk', errors='replace')

    # Count CJK before
    cjk_count_before = len(re.findall(
        r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
        r'\uac00-\ud7af\u3040-\u309f\u30a0-\u30ff]', text
    ))

    text_fixed = cn_to_en(text)

    # Count CJK after
    cjk_count_after = len(re.findall(
        r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
        r'\uac00-\ud7af\u3040-\u309f\u30a0-\u30ff]', text_fixed
    ))

    result['cn_to_en_count'] = cjk_count_before - cjk_count_after

    if not dry_run:
        # Write back as UTF-8 (no BOM, LF)
        with open(filepath, 'wb') as f:
            f.write(text_fixed.encode('utf-8'))

    result['fixed_size'] = len(text_fixed.encode('utf-8'))

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='V007.86d Fix .bat Encoding (ASCII + LF, CN -> EN)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('targets', nargs='+', help='Files to fix')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change, don\'t write')
    args = parser.parse_args()

    print('=' * 60)
    print('V007.86d Fix .bat Encoding')
    print('=' * 60)
    print()

    for filepath in args.targets:
        print(f'--- {filepath} ---')
        result = fix_bat_file(filepath, dry_run=args.dry_run)

        if result['bom_removed']:
            print(f'  [FIX] Removed UTF-8 BOM')
        if result['crlf_to_lf'] > 0:
            print(f'  [FIX] CRLF -> LF: {result["crlf_to_lf"]} occurrences')
        if result['cn_to_en_count'] > 0:
            print(f'  [FIX] CN -> EN: {result["cn_to_en_count"]} chars')
        if (not result['bom_removed']
            and result['crlf_to_lf'] == 0
            and result['cn_to_en_count'] == 0):
            print(f'  [OK] No fixes needed')

        print(f'  Size: {result["original_size"]} -> {result["fixed_size"]} bytes')
        print()

    if args.dry_run:
        print('*** DRY RUN - no changes written ***')


if __name__ == '__main__':
    main()
