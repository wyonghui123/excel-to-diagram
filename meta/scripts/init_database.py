# -*- coding: utf-8 -*-
"""
数据库初始化脚本

创建所有元数据表的SQLite数据库

安全保护：
1. 需要 --force 参数才能删除已存在的数据库
2. 删除前自动备份数据库
"""

import sys
import os
import sqlite3
import json
import shutil
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from meta.core.schema_generator import SchemaGenerator
from meta.core.datasource import get_data_source


def backup_database(db_path: str) -> str:
    """备份数据库，返回备份文件路径"""
    if not os.path.exists(db_path):
        return None

    os.makedirs('backups', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'backups/architecture_{timestamp}.db'

    shutil.copy2(db_path, backup_path)
    print(f"  [备份] 已备份到: {backup_path}")

    backup_size = os.path.getsize(backup_path) / 1024
    print(f"  [备份] 大小: {backup_size:.2f} KB")

    return backup_path


def init_database(force: bool = False):
    db_path = 'meta/architecture.db'
    abs_db_path = os.path.abspath(db_path)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if os.path.exists(db_path):
        if not force:
            print(f"\n{'='*60}")
            print(f"[WARNING]  警告: 数据库已存在")
            print(f"   路径: {abs_db_path}")
            print(f"\n直接运行将删除现有数据库！")
            print(f"\n安全选项:")
            print(f"   1. 使用 --force 参数: python init_database.py --force")
            print(f"   2. 脚本将自动备份现有数据库到 backups/ 目录")
            print(f"{'='*60}\n")
            response = input("是否继续删除并重建数据库? (输入 'yes' 确认): ")
            if response.lower() != 'yes':
                print("操作已取消")
                return None
            print()

        print(f"准备初始化数据库: {db_path}")

        backup_path = backup_database(db_path)
        if backup_path:
            print(f"删除旧数据库: {db_path}")
            os.remove(db_path)
        else:
            print(f"未找到现有数据库，将创建新数据库")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    sql_statements = [
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT,
            description TEXT,
            is_current INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            domain_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (domain_id) REFERENCES domains(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            sub_domain_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (sub_domain_id) REFERENCES sub_domains(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            service_module_id INTEGER,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (service_module_id) REFERENCES service_modules(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL,
            source_bo_id INTEGER NOT NULL,
            target_bo_id INTEGER NOT NULL,
            source_code TEXT,
            target_code TEXT,
            code TEXT,
            relation_code TEXT,
            relation_type TEXT,
            relation_desc TEXT,
            created_at TEXT,
            created_by TEXT,
            updated_by TEXT,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (source_bo_id) REFERENCES business_objects(id),
            FOREIGN KEY (target_bo_id) REFERENCES business_objects(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER,
            action TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id TEXT,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS enum_types (
            id VARCHAR(200) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            category VARCHAR(200) NOT NULL,
            mutability VARCHAR(200) NOT NULL,
            dimension_schema TEXT,
            description TEXT,
            created_at DATETIME
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS enum_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enum_type_id VARCHAR(200) NOT NULL,
            code VARCHAR(200) NOT NULL,
            name VARCHAR(200) NOT NULL,
            name_en VARCHAR(200),
            dimensions TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_system INTEGER DEFAULT 0,
            parent_code VARCHAR(200),
            metadata TEXT,
            created_at DATETIME,
            FOREIGN KEY (enum_type_id) REFERENCES enum_types(id),
            UNIQUE(enum_type_id, code)
        )
        """,
    ]

    for sql in sql_statements:
        cursor.execute(sql)

    conn.commit()
    conn.close()

    print(f"[OK] 数据库初始化完成: {db_path}")
    return db_path


def init_relation_enums(db_path: str = None):
    """
    初始化关系类型枚举

    包括：
    - relation_type: 关系类型枚举（含维度定义）
    - relation_category: 关系分类枚举

    注意：所有枚举定义统一在 meta/scripts/migrate_enums.py 的 ENUM_DIMENSION_CONFIG 中维护，
    model 类定义在 meta/core/models.py 中。本函数委托给 migrate_enums() 确保一致性。
    """
    if db_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        db_path = os.path.join(project_root, 'meta', 'architecture.db')

    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        print(f"  请先运行 init_database() 创建数据库")
        return None

    from meta.scripts.migrate_enums import migrate_enums
    result = migrate_enums(db_path)

    print("-" * 40)
    print(f"关系类型枚举初始化完成! (类型创建: {result['types_created']}, 值创建: {result['values_created']})")
    return db_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='数据库初始化脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python init_database.py                  # 安全模式，会提示确认
  python init_database.py --force         # 强制模式，直接删除并重建
  python init_database.py --yes           # 静默模式，自动确认
        """
    )
    parser.add_argument('--force', '-f', action='store_true',
                        help='强制模式: 直接删除现有数据库，无需确认')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='静默模式: 自动确认所有提示')

    args = parser.parse_args()

    force_mode = args.force or args.yes

    db_path = init_database(force=force_mode)
    if db_path:
        init_relation_enums(db_path)
