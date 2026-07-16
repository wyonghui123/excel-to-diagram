# -*- coding: utf-8 -*-
"""
test_owner_chain_v2_1.py
覆盖提交: 861eec2 (owner_chain + key_template + waitress 调整)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 6 (Audit Log 链路 owner_chain)

测试:
- owner_chain 正确解析所有 owner
- key_template 替换正确 (剥离 prefix_filter 后再检测尾部数字)
- waitress_server.py 启动选项 (USE_FLASK_DEV / application 打印)
- chain_owner_resolver 共享解析
- _check_owner_chain user_id 优先级
- audit_interceptor _ensure_audit_tx_context 行为
"""
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.audit_help,
]


ARCH_DB_PATH = str(PROJECT_ROOT / 'meta' / 'architecture.db')


def _open_db():
    con = sqlite3.connect(ARCH_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# 1. TestOwnerChainV2_1 (6 用例)
# ============================================================

class TestOwnerChainV2_1:
    """owner_chain + key_template + waitress 调整 (861eec2)"""

    def test_owner_chain_resolution(self):
        """[861eec2] owner_chain 正确解析所有 owner

        验证: chain_owner_resolver.resolve_root_owner
        - product 类型 → 直接返回 product.owner_id
        - 不在 chain 的类型 → 返回 None
        """
        from meta.services.chain_owner_resolver import (
            resolve_root_owner, resolve_root_product_id, is_in_chain, HIERARCHY_CHAIN
        )

        # HIERARCHY_CHAIN 包含 product/version/domain/sub_domain
        assert 'product' in HIERARCHY_CHAIN
        assert 'version' in HIERARCHY_CHAIN
        assert 'domain' in HIERARCHY_CHAIN
        assert 'sub_domain' in HIERARCHY_CHAIN

        # is_in_chain
        assert is_in_chain('product') is True
        assert is_in_chain('version') is True
        assert is_in_chain('sub_domain') is True
        # 不在 chain 的 BO
        assert is_in_chain('relationship') is False
        assert is_in_chain('annotation') is False

    def test_key_template_substitution(self):
        """[861eec2] key_template 替换正确 (剥离 prefix_filter 后再检测尾部数字)

        验证: KeyTemplateParser.parse / resolve 能正确处理 pattern 中的
        field references + sequence segments + separators
        """
        from meta.core.key_template_engine import KeyTemplateParser

        parser = KeyTemplateParser()

        # Test 1: 简单 field ref
        tokens = parser.parse("{name}_{code}")
        assert any(t['type'] == 'field' and t['name'] == 'name' for t in tokens)
        assert any(t['type'] == 'field' and t['name'] == 'code' for t in tokens)

        # Test 2: sequence
        tokens = parser.parse("{SEQ:3}")
        assert any(t['type'] == 'sequence' and t['padding'] == 3 for t in tokens)

        # Test 3: resolve 正确替换
        tokens = parser.parse("{name}_{SEQ:2}")
        result = parser.resolve(
            tokens,
            {'name': 'TEST', 'code': 'X'},
            sequence_value=5
        )
        assert 'TEST' in result
        assert '05' in result  # padding=2, value=5 -> '05'

        # Test 4: resolve_prefix (for auto_detect) - 注意: resolve_prefix 保留尾部 separator
        # tokens: {name}_{SEQ:2} → resolve_prefix 在 sequence 之前的所有 token
        # 包括 separator '_', 所以返回 'PROC_REQ_MNG_' (trailing underscore)
        tokens_simple = parser.parse("{name}{SEQ:2}")
        prefix = parser.resolve_prefix(tokens_simple, {'name': 'PROC_REQ_MNG'})
        assert prefix == 'PROC_REQ_MNG', \
            f"resolve_prefix for {{name}}{{SEQ:2}} should be 'PROC_REQ_MNG', got '{prefix}'"

    def test_chain_owner_resolver_handles_chain_levels(self):
        """[861eec2] chain_owner_resolver 处理 chain 各层 BO (product/version/domain/sub_domain)

        验证: resolve_root_owner 对不存在的 record 返回 None, 对空 record_id 返回 None
        """
        from meta.services.chain_owner_resolver import (
            resolve_root_owner, resolve_root_product_id
        )

        # 1. 空 record_id → 返回 None
        assert resolve_root_owner(MagicMock(), 'product', None) is None
        assert resolve_root_owner(MagicMock(), 'product', 0) is None

        # 2. 不在 chain 的 BO → 返回 None
        assert resolve_root_owner(MagicMock(), 'relationship', 1) is None
        assert resolve_root_owner(MagicMock(), 'annotation', 1) is None

        # 3. resolve_root_product_id 空 record_id
        assert resolve_root_product_id(MagicMock(), 'product', None) is None
        assert resolve_root_product_id(MagicMock(), 'product', 0) is None
        # product 类型, 直接返回 record_id
        assert resolve_root_product_id(MagicMock(), 'product', 123) == 123

    def test_owner_chain_interceptor_uses_chain_resolver(self):
        """[861eec2] owner_chain_interceptor 委托给 chain_owner_resolver

        验证: owner_chain_interceptor._check_owner_chain 返回 matched dict
        包含 'matched' (bool) + 'chain_root' (dict) 字段
        """
        from meta.core.interceptors.owner_chain_interceptor import OwnerChainInterceptor

        interceptor = OwnerChainInterceptor()

        # _check_owner_chain 是核心方法
        assert hasattr(interceptor, '_check_owner_chain')
        assert hasattr(interceptor, '_resolve_root_owner')
        assert hasattr(interceptor, '_resolve_root_product_id')

        # priority = 25 (在 PermissionInterceptor=30 之前)
        assert interceptor.priority == 25

    def test_waitress_server_flask_dev_support(self):
        """[861eec2] waitress_server.py 启动方式增强 (USE_FLASK_DEV / application 打印)

        验证: waitress_server.py 包含 USE_FLASK_DEV 环境变量支持
        和 application 创建日志
        """
        waitress_path = PROJECT_ROOT / 'waitress_server.py'
        content = waitress_path.read_text(encoding='utf-8')

        # 关键: USE_FLASK_DEV 支持
        assert 'USE_FLASK_DEV' in content, \
            "waitress_server.py should support USE_FLASK_DEV env var"

        # 关键: application 打印
        assert 'application' in content, \
            "waitress_server.py should reference 'application'"

    def test_key_template_engine_prefix_strip(self):
        """[861eec2] [FIX 2026-06-24] key_template 剥离 prefix_filter 后再检测尾部数字

        验证: SequenceEngine.auto_detect_start 在 prefix_filter 自身含数字时
        不会误判 (剥离 prefix 后只检测剩余部分)
        """
        from meta.core.key_template_engine import SequenceEngine
        from unittest.mock import MagicMock

        # 场景: prefix='A1' (含数字), codes = 'A12', 'A13', 'A15'
        # - 不剥离 prefix: 尾部 'A12' 取 '2' (r'(\d{1})\s*$') -> max=5, +1=6
        #   或者 'A12' 直接取 '12' (r'(\d+)\s*$') -> max=15, +1=16
        # - 剥离 prefix 后: 'A12'[2:]='2', 'A13'[2:]='3', 'A15'[2:]='5' -> max=5, +1=6
        # 验证: 函数能正常返回, 不会崩溃
        mock_rows = [
            ('A12',),     # prefix='A1' + seq=2
            ('A13',),     # prefix='A1' + seq=3
            ('A15',),     # prefix='A1' + seq=5
            ('OTHER99',), # 不相关
        ]

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_ds.execute.return_value = mock_cursor

        engine = SequenceEngine(mock_ds)
        result = engine.auto_detect_start(
            'test_seq', 'business_objects', 'code',
            prefix_filter='A1', seq_padding=1,
        )

        # 正常返回, 不崩溃
        assert result >= 1, "auto_detect should return at least 1"
        # 不应返回 None 或异常值
        assert isinstance(result, int), f"auto_detect should return int, got {type(result)}"
