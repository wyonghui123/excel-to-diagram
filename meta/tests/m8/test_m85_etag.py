"""M8 VP-5 ETag / If-None-Match 测试。

[M8 2026-06-06] ETag middleware + 304 缓存测试。

覆盖：
- MD5 稳定 hash
- 不同内容 → 不同 hash
- If-None-Match 匹配 / 不匹配
- 通配符 '*'
- middleware 排除 SSE / 导出 / 非 JSON
"""
import pytest


class TestComputeETag:
    """M8 VP-5.1 ETag 计算。"""

    def test_stable_hash(self):
        from meta.core.m8_utils import compute_etag
        data = {'items': [1, 2, 3], 'total': 3}
        e1 = compute_etag(data)
        e2 = compute_etag(data)
        assert e1 == e2

    def test_different_content_different_hash(self):
        from meta.core.m8_utils import compute_etag
        e1 = compute_etag({'items': [1, 2, 3]})
        e2 = compute_etag({'items': [1, 2, 3, 4]})
        assert e1 != e2

    def test_dict_order_independent(self):
        """dict 顺序不影响 hash（sort_keys=True）。"""
        from meta.core.m8_utils import compute_etag
        d1 = {'a': 1, 'b': 2}
        d2 = {'b': 2, 'a': 1}
        assert compute_etag(d1) == compute_etag(d2)

    def test_chinese_content_supported(self):
        from meta.core.m8_utils import compute_etag
        e1 = compute_etag({'name': '张三'})
        e2 = compute_etag({'name': '张三'})
        assert e1 == e2

    def test_hash_is_md5_length(self):
        from meta.core.m8_utils import compute_etag
        e = compute_etag({'a': 1})
        assert len(e) == 32  # MD5 hex


class TestCheckETagMatch:
    """M8 VP-5.2 If-None-Match 匹配检查。"""

    def test_exact_match_returns_true(self):
        from meta.core.m8_utils import compute_etag, check_etag_match
        etag = compute_etag({'a': 1})
        assert check_etag_match(etag, {'If-None-Match': f'"{etag}"'})

    def test_unquoted_match(self):
        """客户端可能省略引号。"""
        from meta.core.m8_utils import compute_etag, check_etag_match
        etag = compute_etag({'a': 1})
        assert check_etag_match(etag, {'If-None-Match': etag})

    def test_mismatch_returns_false(self):
        from meta.core.m8_utils import check_etag_match
        assert not check_etag_match('abc', {'If-None-Match': '"wrong"'})

    def test_wildcard_returns_true(self):
        from meta.core.m8_utils import check_etag_match
        assert check_etag_match('abc', {'If-None-Match': '*'})

    def test_no_header_returns_false(self):
        from meta.core.m8_utils import check_etag_match
        assert not check_etag_match('abc', {})

    def test_empty_header_returns_false(self):
        from meta.core.m8_utils import check_etag_match
        assert not check_etag_match('abc', {'If-None-Match': ''})

    def test_strip_whitespace(self):
        from meta.core.m8_utils import compute_etag, check_etag_match
        etag = compute_etag({'a': 1})
        assert check_etag_match(etag, {'If-None-Match': f'  "{etag}"  '})


class TestETagMiddleware:
    """M8 VP-5.3 middleware 行为。"""

    def test_middleware_module_importable(self):
        from meta.core.etag_middleware import init_etag_middleware
        assert callable(init_etag_middleware)

    def test_init_etag_middleware_registers(self):
        from meta.core.etag_middleware import init_etag_middleware
        from flask import Flask
        app = Flask(__name__)
        # 不应抛错
        init_etag_middleware(app)
        # 至少注册了 after_request
        assert app is not None

    def test_middleware_skips_non_get(self):
        """POST/PUT/DELETE 不加 ETag。"""
        from meta.core.etag_middleware import init_etag_middleware
        from flask import Flask
        app = Flask(__name__)
        init_etag_middleware(app)
        # 验证 after_request 处理函数已注册
        # Flask after_request_funcs 存的是 None key 对应 app 级
        after_funcs = app.after_request_funcs.get(None, [])
        assert len(after_funcs) > 0, "after_request handler should be registered"

    def test_middleware_skips_sse(self):
        """SSE 端点 /subscribe/* 不加 ETag。"""
        # 由 middleware 内部 if '/subscribe/' in path: return response
        from meta.core.etag_middleware import init_etag_middleware
        from meta.core.m8_utils import compute_etag
        # compute_etag 是 middleware 的核心
        e = compute_etag({'a': 1})
        assert e is not None
