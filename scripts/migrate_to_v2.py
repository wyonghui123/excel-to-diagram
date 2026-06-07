#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V2 迁移脚本

自动化执行从 V1 到 V2 的迁移过程。
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

class MigrationV2:
    """V2 迁移管理器"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.api_dir = self.base_dir / 'meta' / 'api'
        self.backup_dir = self.api_dir / 'backup_v1'
        self.db_path = self.base_dir / 'meta' / 'architecture.db'
        
        self.api_files = {
            'user_api.py': 'user_api_v2.py',
            'role_api.py': 'role_api_v2.py',
            'user_group_api.py': 'user_group_api_v2.py',
        }
        
        self.log_file = self.base_dir / 'migration_v2.log'
    
    def log(self, message, level='INFO'):
        """记录日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] [{level}] {message}"
        print(log_message)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')
    
    def backup_database(self):
        """备份数据库"""
        self.log("开始备份数据库...")
        
        if not self.db_path.exists():
            self.log("数据库文件不存在，跳过备份", 'WARN')
            return None
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.db_path.parent / f"architecture.db.backup_{timestamp}"
        
        shutil.copy2(self.db_path, backup_path)
        self.log(f"数据库备份完成: {backup_path}")
        
        return backup_path
    
    def backup_old_apis(self):
        """备份旧版本 API"""
        self.log("开始备份旧版本 API...")
        
        self.backup_dir.mkdir(exist_ok=True)
        
        for old_file in self.api_files.keys():
            old_path = self.api_dir / old_file
            if old_path.exists():
                backup_path = self.backup_dir / old_file
                shutil.copy2(old_path, backup_path)
                self.log(f"已备份: {old_file} -> {backup_path}")
            else:
                self.log(f"文件不存在，跳过: {old_file}", 'WARN')
        
        self.log("旧版本 API 备份完成")
    
    def run_tests(self):
        """运行测试"""
        self.log("开始运行测试...")
        
        test_commands = [
            ['python', '-m', 'pytest', 'meta/tests/test_bo_framework.py', '-v'],
            ['python', '-m', 'pytest', 'meta/tests/test_bo_transaction_lock.py', '-v'],
        ]
        
        all_passed = True
        for cmd in test_commands:
            self.log(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=self.base_dir, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.log(f"测试通过: {cmd[3]}")
            else:
                self.log(f"测试失败: {cmd[3]}", 'ERROR')
                self.log(result.stdout, 'DEBUG')
                self.log(result.stderr, 'ERROR')
                all_passed = False
        
        return all_passed
    
    def replace_apis(self):
        """替换 API 文件"""
        self.log("开始替换 API 文件...")
        
        for old_file, new_file in self.api_files.items():
            old_path = self.api_dir / old_file
            new_path = self.api_dir / new_file
            
            if not new_path.exists():
                self.log(f"新版本文件不存在: {new_file}", 'ERROR')
                return False
            
            # 重命名旧文件
            if old_path.exists():
                bak_path = self.api_dir / f"{old_file}.v1.bak"
                old_path.rename(bak_path)
                self.log(f"已重命名: {old_file} -> {old_file}.v1.bak")
            
            # 重命名新文件
            new_path.rename(old_path)
            self.log(f"已替换: {new_file} -> {old_file}")
        
        self.log("API 文件替换完成")
        return True
    
    def rollback(self):
        """回滚迁移"""
        self.log("开始回滚迁移...", 'WARN')
        
        for old_file in self.api_files.keys():
            old_path = self.api_dir / old_file
            bak_path = self.api_dir / f"{old_file}.v1.bak"
            new_path = self.api_dir / self.api_files[old_file]
            
            # 恢复旧文件
            if bak_path.exists():
                if old_path.exists():
                    old_path.rename(new_path)
                bak_path.rename(old_path)
                self.log(f"已恢复: {old_file}.v1.bak -> {old_file}")
        
        self.log("回滚完成", 'WARN')
    
    def verify_migration(self):
        """验证迁移"""
        self.log("开始验证迁移...")
        
        checks = [
            ('user_api.py', 'init_user_services'),
            ('role_api.py', 'init_role_services'),
            ('user_group_api.py', 'user_group_bp'),
        ]
        
        all_passed = True
        for file_name, check_item in checks:
            file_path = self.api_dir / file_name
            if not file_path.exists():
                self.log(f"文件不存在: {file_name}", 'ERROR')
                all_passed = False
                continue
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'BOFramework' in content:
                    self.log(f"[DECORATIVE] {file_name} 已使用 BOFramework")
                else:
                    self.log(f"[DECORATIVE] {file_name} 未使用 BOFramework", 'ERROR')
                    all_passed = False
        
        return all_passed
    
    def execute(self, skip_tests=False):
        """执行完整迁移流程"""
        self.log("=" * 60)
        self.log("开始 V2 迁移")
        self.log("=" * 60)
        
        try:
            # 1. 备份
            self.backup_database()
            self.backup_old_apis()
            
            # 2. 测试
            if not skip_tests:
                if not self.run_tests():
                    self.log("测试未通过，终止迁移", 'ERROR')
                    return False
            
            # 3. 替换
            if not self.replace_apis():
                self.log("API 替换失败，终止迁移", 'ERROR')
                return False
            
            # 4. 验证
            if not self.verify_migration():
                self.log("迁移验证失败", 'ERROR')
                return False
            
            self.log("=" * 60)
            self.log("V2 迁移成功完成！")
            self.log("=" * 60)
            
            return True
            
        except Exception as e:
            self.log(f"迁移过程中发生错误: {e}", 'ERROR')
            import traceback
            self.log(traceback.format_exc(), 'ERROR')
            
            self.log("执行回滚...", 'ERROR')
            self.rollback()
            
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='V2 迁移脚本')
    parser.add_argument('--skip-tests', action='store_true', help='跳过测试')
    parser.add_argument('--rollback', action='store_true', help='执行回滚')
    parser.add_argument('--verify', action='store_true', help='仅验证')
    
    args = parser.parse_args()
    
    migration = MigrationV2()
    
    if args.rollback:
        migration.rollback()
    elif args.verify:
        migration.verify_migration()
    else:
        success = migration.execute(skip_tests=args.skip_tests)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
