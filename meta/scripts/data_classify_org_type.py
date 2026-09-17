"""
[Phase 1] org_type 分类审查脚本

执行后输出 review 文件, 人工 review 后用 --apply 真正应用
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db-path', default='meta/architecture.db')
    parser.add_argument(
        '--review-file',
        default='meta/architecture.db.org_type_review.txt'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='真正应用 (默认只生成 review)'
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"[ABORT] DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT id, code, name, org_type FROM orgs ORDER BY id"
    )
    orgs = cur.fetchall()

    lines = []
    lines.append('org_type 分类审查报告')
    lines.append('=' * 80)
    lines.append(f'{"ID":<6} {"org_type":<12} {"code":<40} {"name":<30}')
    lines.append('-' * 80)

    needs_review = []
    for org_id, code, name, current_type in orgs:
        # 检查是否含可疑关键词 (需人工判断)
        text = f'{code or ""} {name or ""}'.lower()
        suspicious = False
        recommended = None

        # personal 已被正确分类, 跳过
        if current_type == 'personal':
            continue

        if (code and code.startswith('personal_group_user_')
                and current_type != 'personal'):
            suspicious = True
            recommended = 'personal'
        elif (any(kw in text for kw in ['部门', '部', '处', '科'])
                and current_type not in ['department']):
            suspicious = True
            recommended = 'department'
        elif (any(kw in text for kw in ['组', '团队'])
                and current_type not in ['team']):
            suspicious = True
            recommended = 'team'

        if suspicious:
            needs_review.append(
                (org_id, code, name, current_type, recommended)
            )
            code_str = (code[:38] if code else '').ljust(40)
            name_str = (name[:28] if name else '').ljust(30)
            lines.append(
                f'{org_id:<6} {current_type:<12} {code_str} {name_str}  '
                f'⚠ 建议: {recommended}'
            )

    lines.append('=' * 80)
    lines.append(
        f'共 {len(orgs)} 个 org, {len(needs_review)} 个需 review'
    )

    review_text = '\n'.join(lines)
    Path(args.review_file).write_text(review_text, encoding='utf-8')

    print(review_text)
    print(f'\n审查报告已写入: {args.review_file}')

    if args.apply and needs_review:
        for org_id, code, name, current_type, recommended in needs_review:
            if recommended:
                conn.execute(
                    "UPDATE orgs SET org_type = ? WHERE id = ?",
                    (recommended, org_id)
                )
        conn.commit()
        print(f'已应用 {len(needs_review)} 个 org_type 修改')
    elif needs_review:
        print(f'\n请人工 review, 确认后用 --apply 应用')
    else:
        print(f'\n所有 org_type 分类正确, 无需调整')


if __name__ == '__main__':
    main()
