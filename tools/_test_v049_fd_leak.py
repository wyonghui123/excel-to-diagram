#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V049 真端到端测试: 验证 import_export_service 的 wb leak 修法

测试目标:
  1. _import_sheet (异常路径) 强制 wb.close() + gc.collect()
  2. import_cascade 已有 wb.close() + gc.collect()
  3. 100 次调用后, 进程内 file descriptor 数量不应无限制增长
"""
import sys
import os
import gc
import tempfile
import shutil
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def count_fds():
    """当前进程的 fd 数量 (Windows 用 handle 数)"""
    proc = psutil.Process()
    if os.name == 'nt':
        return len(proc.open_files())
    return proc.num_fds()


def make_temp_xlsx(num_sheets=3, num_rows=100):
    """造一个临时 xlsx 文件 (openpyxl 真实创建)"""
    from openpyxl import Workbook
    tmpdir = tempfile.mkdtemp(prefix='v049_test_')
    fp = os.path.join(tmpdir, 'test.xlsx')
    wb = Workbook()
    ws = wb.active
    ws.title = '元数据'
    ws.append(['product_code', 'version_code', '操作说明'])
    ws.append(['TEST', 'v1', '测试'])
    for i in range(1, num_sheets):
        ws = wb.create_sheet(title=f'sheet_{i}')
        ws.append(['code', 'name', 'description'])
        for r in range(num_rows):
            ws.append([f'code_{i}_{r}', f'name_{i}_{r}', f'desc_{i}_{r}'])
    wb.save(fp)
    wb.close()
    return tmpdir, fp


def test_import_cascade_releases_wb():
    """测试 import_cascade 跑 100 次, FD 不应无限制增长"""
    from meta.services.import_export_service import ImportExportService
    from unittest.mock import MagicMock

    tmpdir, fp = make_temp_xlsx(num_sheets=2, num_rows=10)
    try:
        service = ImportExportService(data_source=MagicMock())
        fd_before = count_fds()

        # 跑 100 次 import_cascade (会失败因为 mock ds, 但 wb 应该 close)
        for i in range(100):
            try:
                service.import_cascade(
                    file_path=fp,
                    mode='execute',
                    conflict_strategy='skip',
                )
            except Exception:
                pass  # mock ds 会失败, 我们只关心 wb 释放

        gc.collect()
        fd_after = count_fds()

        delta = fd_after - fd_before
        print(f'[import_cascade] 100 calls: FD {fd_before} -> {fd_after} (delta {delta})')
        if delta > 10:
            print(f'  [X] LEAK: 100 次 import_cascade 后 FD 增长 {delta} (应 < 10)')
            return False
        print(f'  [OK] FD 增长 {delta} (< 10, 100 次可接受)')
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_import_sheet_exception_releases_wb():
    """测试 _import_sheet 异常路径 (registry miss), FD 不应增长"""
    from meta.services.import_export_service import ImportExportService
    from unittest.mock import MagicMock

    tmpdir, fp = make_temp_xlsx(num_sheets=1, num_rows=5)
    try:
        service = ImportExportService(data_source=MagicMock())
        fd_before = count_fds()

        # 100 次 _import_sheet (sheet_info 含 fake object_type, registry 会 miss)
        for i in range(100):
            sheet_info = {
                'name': 'sheet_1',  # 存在的 sheet
                'object_type': f'nonexistent_object_{i}',  # 触发 except 路径
                'mode': 'execute',
                'strategy': 'skip',
            }
            try:
                service._import_sheet(
                    file_path=fp,
                    sheet_info=sheet_info,
                    conflict_strategy='skip',
                    context={'version_id': None, 'product_id': None},
                )
            except Exception:
                pass  # 预期异常

        gc.collect()
        fd_after = count_fds()

        delta = fd_after - fd_before
        print(f'[_import_sheet except path] 100 calls: FD {fd_before} -> {fd_after} (delta {delta})')
        if delta > 10:
            print(f'  [X] LEAK: 100 次 _import_sheet except 后 FD 增长 {delta} (应 < 10)')
            return False
        print(f'  [OK] FD 增长 {delta} (< 10, 100 次可接受)')
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_import_sheet_normal_releases_wb():
    """测试 _import_sheet 正常路径 (registry miss 之前), FD 不应增长"""
    from meta.services.import_export_service import ImportExportService
    from unittest.mock import MagicMock

    tmpdir, fp = make_temp_xlsx(num_sheets=1, num_rows=5)
    try:
        service = ImportExportService(data_source=MagicMock())
        fd_before = count_fds()

        # 100 次 _import_sheet (不存在的 object_type, 走 except 路径)
        for i in range(100):
            sheet_info = {
                'name': '元数据',  # 不存在的 sheet
                'object_type': 'product',
                'mode': 'execute',
                'strategy': 'skip',
            }
            try:
                service._import_sheet(
                    file_path=fp,
                    sheet_info=sheet_info,
                    conflict_strategy='skip',
                    context={'version_id': None, 'product_id': None},
                )
            except Exception:
                pass

        gc.collect()
        fd_after = count_fds()

        delta = fd_after - fd_before
        print(f'[_import_sheet normal path] 100 calls: FD {fd_before} -> {fd_after} (delta {delta})')
        if delta > 10:
            print(f'  [X] LEAK: 100 次 _import_sheet normal 后 FD 增长 {delta} (应 < 10)')
            return False
        print(f'  [OK] FD 增长 {delta} (< 10, 100 次可接受)')
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    print('=' * 60)
    print('V049 真端到端测试: FD leak 修法验证')
    print('=' * 60)
    print()

    results = []
    results.append(('import_cascade 100 calls', test_import_cascade_releases_wb()))
    print()
    results.append(('_import_sheet except path 100 calls', test_import_sheet_exception_releases_wb()))
    print()
    results.append(('_import_sheet normal path 100 calls', test_import_sheet_normal_releases_wb()))
    print()

    print('=' * 60)
    print('Test Results:')
    for name, passed in results:
        print(f'  {"[OK]" if passed else "[X]"} {name}')
    print('=' * 60)

    if all(p for _, p in results):
        print('ALL PASS - V049 fd leak fix 真验证通过')
        sys.exit(0)
    else:
        print('FAIL - V049 fd leak fix 有问题')
        sys.exit(1)
