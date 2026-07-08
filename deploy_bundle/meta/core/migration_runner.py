# -*- coding: utf-8 -*-
"""
数据库迁移运行器

提供数据库迁移脚本的执行和管理功能：
- 执行 SQL 迁移脚本
- 记录迁移历史
- 支持可重复执行（幂等性）
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name VARCHAR(255) NOT NULL UNIQUE,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64)
);
"""


class MigrationRunner:
    """数据库迁移运行器"""
    
    def __init__(self, data_source, migrations_dir: str = None):
        """
        初始化迁移运行器
        
        Args:
            data_source: 数据源实例
            migrations_dir: 迁移脚本目录路径
        """
        self.data_source = data_source
        self.migrations_dir = migrations_dir or self._get_default_migrations_dir()
    
    def _get_default_migrations_dir(self) -> str:
        """获取默认迁移目录路径"""
        current_dir = Path(__file__).parent.parent
        migrations_dir = current_dir / "migrations"
        if migrations_dir.exists():
            return str(migrations_dir)
        return str(current_dir / "core" / "migrations")
    
    def ensure_migrations_table(self):
        """确保迁移记录表存在"""
        self.data_source.execute(MIGRATIONS_TABLE)
        if not self.data_source.in_transaction:
            self.data_source.commit()
        logger.info("Migration tracking table ensured")
    
    def get_executed_migrations(self) -> List[str]:
        """获取已执行的迁移列表"""
        sql = "SELECT migration_name FROM schema_migrations ORDER BY id"
        cursor = self.data_source.execute(sql)
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    
    def is_migration_executed(self, migration_name: str) -> bool:
        """检查迁移是否已执行"""
        sql = "SELECT 1 FROM schema_migrations WHERE migration_name = ?"
        cursor = self.data_source.execute(sql, (migration_name,))
        return cursor.fetchone() is not None
    
    def record_migration(self, migration_name: str, checksum: str = None):
        """记录迁移执行"""
        sql = "INSERT INTO schema_migrations (migration_name, checksum) VALUES (?, ?)"
        self.data_source.execute(sql, (migration_name, checksum))
        if not self.data_source.in_transaction:
            self.data_source.commit()
        logger.info("Migration recorded: %s", migration_name)
    
    def execute_sql_file(self, sql_file_path: str) -> bool:
        """
        执行 SQL 文件
        
        Args:
            sql_file_path: SQL 文件路径
            
        Returns:
            是否执行成功
        """
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            statements = self._parse_sql_statements(sql_content)
            
            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    self.data_source.execute(statement)
            
            if not self.data_source.in_transaction:
                self.data_source.commit()
            
            logger.info("SQL file executed successfully: %s", sql_file_path)
            return True
            
        except Exception as e:
            logger.error("Failed to execute SQL file %s: %s", sql_file_path, str(e))
            return False
    
    def _parse_sql_statements(self, sql_content: str) -> List[str]:
        """
        解析 SQL 语句
        
        将 SQL 文件内容分割为独立的语句
        """
        statements = []
        current_statement = []
        
        for line in sql_content.split('\n'):
            line = line.strip()
            
            if line.startswith('--'):
                continue
            
            current_statement.append(line)
            
            if line.endswith(';'):
                stmt = '\n'.join(current_statement)
                if stmt.strip():
                    statements.append(stmt)
                current_statement = []
        
        if current_statement:
            stmt = '\n'.join(current_statement)
            if stmt.strip():
                statements.append(stmt)
        
        return statements
    
    def run_migration(self, migration_name: str) -> bool:
        """
        执行单个迁移
        
        Args:
            migration_name: 迁移名称（文件名）
            
        Returns:
            是否执行成功
        """
        if self.is_migration_executed(migration_name):
            logger.info("Migration already executed: %s", migration_name)
            return True
        
        sql_file_path = os.path.join(self.migrations_dir, migration_name)
        
        if not os.path.exists(sql_file_path):
            logger.error("Migration file not found: %s", sql_file_path)
            return False
        
        if self.execute_sql_file(sql_file_path):
            self.record_migration(migration_name)
            return True
        
        return False
    
    def run_pending_migrations(self) -> int:
        """
        执行所有待处理的迁移
        
        Returns:
            成功执行的迁移数量
        """
        self.ensure_migrations_table()
        
        if not os.path.exists(self.migrations_dir):
            logger.warning("Migrations directory not found: %s", self.migrations_dir)
            return 0
        
        executed_count = 0
        migration_files = sorted([
            f for f in os.listdir(self.migrations_dir)
            if f.endswith('.sql')
        ])
        
        for migration_file in migration_files:
            if self.run_migration(migration_file):
                executed_count += 1
        
        logger.info("Executed %d migrations", executed_count)
        return executed_count
    
    def run_change_notification_migration(self) -> bool:
        """
        执行变更通知表迁移
        
        Returns:
            是否执行成功
        """
        self.ensure_migrations_table()
        migration_name = "add_change_notification_tables.sql"
        return self.run_migration(migration_name)


def init_change_notification_tables(data_source) -> bool:
    """
    初始化变更通知表
    
    便捷函数，用于在应用启动时初始化变更通知相关的数据库表。
    
    Args:
        data_source: 数据源实例
        
    Returns:
        是否初始化成功
    """
    runner = MigrationRunner(data_source)
    return runner.run_change_notification_migration()


def run_all_migrations(data_source, migrations_dir: str = None) -> int:
    """
    执行所有待处理的迁移
    
    便捷函数，用于在应用启动时执行所有数据库迁移。
    
    Args:
        data_source: 数据源实例
        migrations_dir: 迁移脚本目录路径
        
    Returns:
        成功执行的迁移数量
    """
    runner = MigrationRunner(data_source, migrations_dir)
    return runner.run_pending_migrations()
