#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根目录清理脚本

将临时文件、调试脚本、部署脚本等归档到 archive/ 目录，
提升智能体搜索精确度。

使用方法:
    python scripts/archive-root-files.py [--dry-run]

    --dry-run: 仅显示将要移动的文件，不实际执行
"""

import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
ARCHIVE_DIR = ROOT_DIR / "archive"

FILE_CATEGORIES = {
    "debug": [
        "debug_tree.py",
        "debug_test.py",
        "debug_filter.py",
        "debug_view_config.py",
        "debug_list_data.py",
        "debug_version_routing.py",
        "debug_version_filter.py",
        "debug_preview_sheets.py",
        "debug_index.py",
        "debug_import_trace.py",
        "debug_import_success_but_empty.py",
        "debug_import_diff.py",
        "debug_excel_meta.py",
        "debug_excel_content.py",
        "debug_backend_version.py",
        "debug.log",
        "debug-arch-data.png",
        "debug-landing.png",
        "debug-deploy.sh",
        "debug-server.sh",
    ],
    "check": [
        "check_enums.py",
        "check_bos.py",
        "check_protection.py",
        "check_version_data.py",
        "check_user_excel.py",
        "check_transaction.py",
        "check_service_modules.py",
        "check_resolve_to.py",
        "check_relationship_columns.py",
        "check_recent_records.py",
        "check_parent_objects.py",
        "check_missing_sm.py",
        "check_import_result.py",
        "check_if_need_restart.py",
        "check_excel_sheets.py",
        "check_excel_meta.py",
        "check_excel_full.py",
        "check_excel_codes.py",
        "check_excel_bo.py",
        "check_db.py",
        "check_bo_bk_fields.py",
        "check_all_versions.py",
        "check-current.sh",
        "check-deploy.sh",
        "check-http.sh",
        "check-version.sh",
    ],
    "deploy": [
        "deploy.sh",
        "deploy-yonyou.sh",
        "deploy-robust.sh",
        "deploy-python.sh",
        "deploy-package.sh",
        "deploy-latest.sh",
        "deploy-full-app.sh",
        "deploy-final.sh",
        "deploy-direct.sh",
        "deploy-centos7.sh",
        "deploy-bastion.sh",
        "deploy-bastion-debug.sh",
        "deploy-auto.sh",
        "clean-and-redeploy.sh",
        "base64-deploy.sh",
        "build-and-notify.sh",
        "docker-start.sh",
        "manual-deploy.sh",
        "offline-install.sh",
        "rollback.sh",
        "self-extract.sh",
        "self-extract-py25.sh",
        "self-extract-py25-fixed.sh",
        "self-extract-py25-clean.sh",
        "self-extract-80.sh",
        "test-api.sh",
    ],
    "fix": [
        "fix-structure.sh",
        "fix-server.sh",
        "fix-server-start.sh",
        "fix-permission.sh",
        "fix_subdomains.py",
        "fix_subdomain_import.py",
        "fix_bo_module.py",
        "fix-garbled.ps1",
        "fix-garbled-v2.ps1",
    ],
    "analyze": [
        "analyze_deep.py",
        "analyze_missing_data.py",
    ],
    "find": [
        "find_v5_excel.py",
        "find_large_excel_files.py",
        "find_large_excel.py",
        "find_abca01.py",
    ],
    "temp": [
        "final_report.py",
        "final_import.py",
        "full_manual_import.py",
        "import_modules_and_relations.py",
        "cleanup_test_data.py",
        "demo-data.js",
        "bookmarklet.txt",
        "backend_restart.log",
        "record-operations.js",
        "record-manual.js",
        "record-demo.js",
        "restart_backend.py",
        "manual_import.py",
        "import_relationships.py",
        "push-to-github.ps1",
        "package-v3.ps1",
    ],
    "packages": [
        "deploy-v20260416_001.zip",
        "deploy-v20260416_002.zip",
        "deploy-v20260416_003.zip",
        "deploy-v20260428_001.zip",
        "deploy-bastion.zip",
        "meta-server-fix.zip",
        "meta-backend-v20260428_001.zip",
        "frontend-deploy-centos7.zip",
        "frontend-deploy-python.zip",
        "frontend-deploy-latest.zip",
        "dist.tar.gz",
        "dist-new.tar.gz",
        "excel-to-diagram-full.zip",
        "init-db.zip",
        "frontend-deploy-centos7.zip",
        "frontend-deploy-latest.zip",
        "frontend-deploy-python.zip",
        "server-py.zip",
        "schema-api-fix.zip",
        "stats-api-fix.zip",
        "test-api-final.zip",
        "test-api-v2.zip",
        "test-ui-v20260428_001.zip",
    ],
    "docs": [
        "问题诊断报告.md",
        "导入问题根因分析报告.md",
        "导入系统修复总结.md",
        "导入数据路由错误问题诊断与解决方案.md",
        "前端版本传递问题修复说明.md",
        "centos7-manual-deploy.md",
        "deploy-step-by-step.md",
        "TODO_page_edit.md",
    ],
    "server-variants": [
        "server.py",
        "server-fixed.py",
        "server-correct.py",
        "python-server.py",
    ],
    "test": [
        "test_update.py",
        "test_import_validation.py",
        "test_import_e2e.py",
        "test_import_debug.py",
        "test_filter.py",
        "test_delete.py",
        "test_business_object_fields.py",
        "test_api_response.py",
        "test_id_field.py",
        "test_version_business_key.py",
        "test_upsert.py",
        "test_sub_domain_fk.py",
        "test_sub_domain2.py",
        "test_sub_domain.py",
        "test_relationship_preview.py",
        "test_query_service.py",
        "test_preview_validation.py",
        "test_parent_key_headers.py",
        "test_parent_header.py",
        "test_new_excel.py",
        "test_manage_service.py",
        "test_manage_direct.py",
        "test_index.py",
        "test_import_v5.py",
        "test_import_order.py",
        "test_import_fix.py",
        "test_import_detail.py",
        "test_import_debug3.py",
        "test_import_debug2.py",
        "test_import_cascade.py",
        "test_import_automation.py",
        "test_import_api.py",
        "test_full_import.py",
        "test_find_bo.py",
        "test_service_module.py",
        "test_frontend.py",
        "test_edit_form.py",
        "test_edit_debug.py",
        "test_import.xlsx",
    ],
    "screenshots": [
        "screenshot_detail.png",
        "screenshot_arch_manage.png",
        "screenshot_home.png",
        "screenshot_service_module_edit.png",
        "screenshot_edit_debug.png",
        "screenshot_edit_form.png",
    ],
}

def create_archive_dirs():
    for category in FILE_CATEGORIES.keys():
        (ARCHIVE_DIR / category).mkdir(parents=True, exist_ok=True)
    print(f"Created archive directories under {ARCHIVE_DIR}")

def move_files(dry_run=False):
    moved_count = 0
    missing_count = 0
    
    for category, files in FILE_CATEGORIES.items():
        target_dir = ARCHIVE_DIR / category
        for filename in files:
            src = ROOT_DIR / filename
            dst = target_dir / filename
            
            if not src.exists():
                missing_count += 1
                continue
            
            if dry_run:
                print(f"[DRY-RUN] Would move: {filename} -> archive/{category}/")
            else:
                shutil.move(str(src), str(dst))
                print(f"Moved: {filename} -> archive/{category}/")
                moved_count += 1
    
    return moved_count, missing_count

def create_readme():
    readme_content = f"""# Archive Directory

This directory contains archived temporary files moved from the project root.

**Archived on**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Directory Structure

| Directory | Content |
|-----------|---------|
| debug/ | Debug scripts (debug_*.py, debug-*.sh) |
| check/ | Check/verification scripts (check_*.py, check-*.sh) |
| deploy/ | Deployment scripts (deploy-*.sh) |
| fix/ | Fix scripts (fix_*.py, fix-*.sh, fix-*.ps1) |
| analyze/ | Analysis scripts (analyze_*.py) |
| find/ | Search scripts (find_*.py) |
| temp/ | Temporary files and misc scripts |
| packages/ | Archived deployment packages (.zip, .tar.gz) |
| docs/ | Temporary documentation files |
| server-variants/ | Alternative server entry points |

## Purpose

These files were moved to improve AI agent search accuracy by reducing
noise in the project root directory. They are kept for reference but
are not part of the active codebase.

## Restoration

To restore any file, simply move it back to the project root:
```bash
mv archive/category/filename.ext .
```
"""
    
    readme_path = ARCHIVE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"Created: {readme_path}")

def main():
    parser = argparse.ArgumentParser(description="Archive temporary files from project root")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be moved without actually moving")
    args = parser.parse_args()
    
    print(f"Root directory: {ROOT_DIR}")
    print(f"Archive directory: {ARCHIVE_DIR}")
    print()
    
    if args.dry_run:
        print("=== DRY RUN MODE ===")
        print()
    
    create_archive_dirs()
    moved, missing = move_files(dry_run=args.dry_run)
    
    if not args.dry_run:
        create_readme()
    
    print()
    print(f"Summary: {moved} files moved, {missing} files not found")
    
    if args.dry_run:
        print()
        print("Run without --dry-run to actually move files")

if __name__ == "__main__":
    main()
