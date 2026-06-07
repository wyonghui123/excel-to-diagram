import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
边界条件与异常处理测试
==========================

测试各种边界条件、特殊字符和异常情况。
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, date


@pytest.fixture
def edge_db():
    """创建边界测试数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT UNIQUE,
            description TEXT,
            version_id INTEGER DEFAULT 1,
            created_at DATETIME,
            created_by TEXT,
            updated_at DATETIME,
            status TEXT DEFAULT 'active'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            positive INTEGER,
            negative INTEGER,
            zero INTEGER,
            decimal_val REAL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_strings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text_val TEXT,
            varchar_val TEXT
        )
    """)

    conn.commit()
    yield conn
    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def api_client(shared_client):
    """创建API测试客户端"""
    return shared_client


class TestEmptyDatabase:
    """空数据库操作测试"""

    def test_query_empty_table_returns_empty(self, edge_db):
        """查询空表应返回空列表"""
        cursor = edge_db.execute("SELECT * FROM domains WHERE version_id = 999")
        results = cursor.fetchall()
        assert results == [], "空表查询应返回空列表"

    def test_count_empty_table_returns_zero(self, edge_db):
        """COUNT空表应返回0"""
        cursor = edge_db.execute("SELECT COUNT(*) as cnt FROM domains")
        count = cursor.fetchone()['cnt']
        assert count == 0, "空表的COUNT应为0"

    def test_update_empty_table_returns_zero_rows(self, edge_db):
        """UPDATE空表应返回0行影响"""
        cursor = edge_db.execute("UPDATE domains SET status = 'inactive' WHERE id = 1")
        assert cursor.rowcount == 0, "更新空表应影响0行"


class TestFieldLengthLimits:
    """字段长度限制测试"""

    def test_maximum_varchar_handling(self, edge_db):
        """超长字符串处理 - SQLite TEXT类型不强制长度限制"""
        max_length = 255
        long_string = "x" * (max_length + 100)

        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (long_string, "MAX_LEN")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("MAX_LEN",))
        result = cursor.fetchone()['name']
        assert len(result) == max_length + 100, "超长字符串应被存储或截断"

    def test_exact_length_string(self, edge_db):
        """精确长度字符串"""
        exact_string = "x" * 255
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (exact_string, "EXACT_LEN")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("EXACT_LEN",))
        result = cursor.fetchone()['name']
        assert len(result) == 255, "应正确存储255字符"

    def test_zero_length_string(self, edge_db):
        """零长度字符串"""
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            ("", "EMPTY_STRING")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("EMPTY_STRING",))
        result = cursor.fetchone()['name']
        assert result == "", "应正确存储空字符串"


class TestSpecialCharacters:
    """特殊字符处理测试"""

    def test_sql_injection_attempt_handled(self, edge_db):
        """SQL注入尝试应被安全处理 (参数化查询自动防止注入)"""
        malicious_inputs = [
            "'; DROP TABLE domains;--",
            "1 OR 1=1",
            "admin'--",
            "1 UNION SELECT * FROM users--"
        ]

        for malicious in malicious_inputs:
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                (malicious, f"SQL_INJ_{hash(malicious) % 10000}")
            )
            edge_db.commit()

            cursor = edge_db.execute(
                "SELECT name FROM domains WHERE code = ?",
                (f"SQL_INJ_{hash(malicious) % 10000}",)
            )
            result = cursor.fetchone()
            assert result['name'] == malicious, "注入字符串应作为字面值存储"

    def test_single_quotes_in_text(self, edge_db):
        """单引号应正确转义"""
        text_with_quotes = "O'Brien's Pub"
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (text_with_quotes, "SINGLE_QUOTE")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("SINGLE_QUOTE",))
        result = cursor.fetchone()['name']
        assert result == text_with_quotes

    def test_double_quotes_in_text(self, edge_db):
        """双引号应正确处理"""
        text_with_quotes = 'He said "Hello"'
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (text_with_quotes, "DOUBLE_QUOTE")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("DOUBLE_QUOTE",))
        result = cursor.fetchone()['name']
        assert result == text_with_quotes

    def test_backslash_in_text(self, edge_db):
        """反斜杠应正确处理"""
        text_with_backslash = "path\\to\\file"
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (text_with_backslash, "BACKSLASH")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("BACKSLASH",))
        result = cursor.fetchone()['name']
        assert result == text_with_backslash

    def test_newline_in_text(self, edge_db):
        """换行符应正确处理"""
        text_with_newline = "line1\nline2\nline3"
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (text_with_newline, "NEWLINE")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("NEWLINE",))
        result = cursor.fetchone()['name']
        assert result == text_with_newline


class TestUnicodeAndEmoji:
    """Unicode和Emoji支持测试"""

    def test_chinese_characters(self, edge_db):
        """中文支持"""
        chinese_texts = [
            "简体中文测试",
            "繁體中文",
            "中文123abc"
        ]
        for i, text in enumerate(chinese_texts):
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                (text, f"CHINESE_{i}")
            )
            edge_db.commit()

            cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", (f"CHINESE_{i}",))
            assert cursor.fetchone()['name'] == text

    def test_japanese_characters(self, edge_db):
        """日文支持"""
        japanese_text = "日本語テスト"
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (japanese_text, "JAPANESE")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("JAPANESE",))
        assert cursor.fetchone()['name'] == japanese_text

    def test_korean_characters(self, edge_db):
        """韩文支持"""
        korean_text = "한국어 테스트"
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (korean_text, "KOREAN")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", ("KOREAN",))
        assert cursor.fetchone()['name'] == korean_text

    def test_emoji_support(self, edge_db):
        """Emoji支持"""
        emoji_texts = [
            "[SYMBOL] 庆祝",
            "[SYMBOL] 点赞",
            "[DECORATIVE][DECORATIVE][DECORATIVE]",
            "[SYMBOL][SYMBOL][SYMBOL]"
        ]
        for i, text in enumerate(emoji_texts):
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                (text, f"EMOJI_{i}")
            )
            edge_db.commit()

            cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", (f"EMOJI_{i}",))
            assert cursor.fetchone()['name'] == text

    def test_flag_emoji(self, edge_db):
        """国旗emoji支持"""
        flag_texts = [
            "[SYMBOL][SYMBOL] 中国",
            "[SYMBOL][SYMBOL] 美国",
            "[SYMBOL][SYMBOL] 日本"
        ]
        for i, text in enumerate(flag_texts):
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                (text, f"FLAG_{i}")
            )
            edge_db.commit()

            cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", (f"FLAG_{i}",))
            assert cursor.fetchone()['name'] == text

    def test_skin_tone_modifiers(self, edge_db):
        """肤色修饰符支持"""
        skin_tone_texts = [
            "[SYMBOL][SYMBOL] 浅肤色",
            "[SYMBOL][SYMBOL] 中浅肤色",
            "[SYMBOL][SYMBOL] 中肤色",
            "[SYMBOL][SYMBOL] 中深肤色",
            "[SYMBOL][SYMBOL] 深肤色"
        ]
        for i, text in enumerate(skin_tone_texts):
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                (text, f"SKIN_{i}")
            )
            edge_db.commit()

            cursor = edge_db.execute("SELECT name FROM domains WHERE code = ?", (f"SKIN_{i}",))
            assert cursor.fetchone()['name'] == text


class TestDateTimeBoundary:
    """日期时间边界值测试"""

    def test_minimum_datetime(self, edge_db):
        """最小日期时间"""
        min_date = "1970-01-01 00:00:00"
        edge_db.execute(
            "INSERT INTO domains (name, code, created_at) VALUES (?, ?, ?)",
            ("min_date", "MIN_DATE", min_date)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT created_at FROM domains WHERE code = ?", ("MIN_DATE",))
        result = cursor.fetchone()['created_at']
        assert min_date in result or result.startswith("1970-01-01")

    def test_maximum_datetime(self, edge_db):
        """最大日期时间"""
        max_date = "9999-12-31 23:59:59"
        edge_db.execute(
            "INSERT INTO domains (name, code, created_at) VALUES (?, ?, ?)",
            ("max_date", "MAX_DATE", max_date)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT created_at FROM domains WHERE code = ?", ("MAX_DATE",))
        result = cursor.fetchone()['created_at']
        assert "9999" in result or "9998" in result

    def test_future_datetime(self, edge_db):
        """未来日期时间"""
        future_date = "2099-12-31 23:59:59"
        edge_db.execute(
            "INSERT INTO domains (name, code, created_at) VALUES (?, ?, ?)",
            ("future_date", "FUTURE_DATE", future_date)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT created_at FROM domains WHERE code = ?", ("FUTURE_DATE",))
        result = cursor.fetchone()['created_at']
        assert "2099" in result

    def test_datetime_with_timezone(self, edge_db):
        """带时区信息的时间"""
        tz_date = "2024-01-15 08:30:00+08:00"
        edge_db.execute(
            "INSERT INTO domains (name, code, created_at) VALUES (?, ?, ?)",
            ("tz_date", "TZ_DATE", tz_date)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT created_at FROM domains WHERE code = ?", ("TZ_DATE",))
        result = cursor.fetchone()['created_at']
        assert "2024-01-15" in result


class TestNumericBoundaries:
    """数值边界测试"""

    def test_zero_values(self, edge_db):
        """零值测试"""
        edge_db.execute(
            "INSERT INTO test_numbers (positive, negative, zero) VALUES (?, ?, ?)",
            (0, 0, 0)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT * FROM test_numbers WHERE positive = 0")
        result = cursor.fetchone()
        assert result is not None
        assert result['positive'] == 0
        assert result['negative'] == 0

    def test_negative_values(self, edge_db):
        """负数值测试"""
        edge_db.execute(
            "INSERT INTO test_numbers (positive, negative) VALUES (?, ?)",
            (-100, -200)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT * FROM test_numbers WHERE negative < 0")
        result = cursor.fetchone()
        assert result is not None
        assert result['negative'] == -200

    def test_maximum_integer(self, edge_db):
        """最大整数"""
        max_int = 9223372036854775807
        edge_db.execute(
            "INSERT INTO test_numbers (positive) VALUES (?)",
            (max_int,)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT positive FROM test_numbers WHERE positive = ?", (max_int,))
        result = cursor.fetchone()
        assert result['positive'] == max_int

    def test_minimum_integer(self, edge_db):
        """最小整数"""
        min_int = -9223372036854775808
        edge_db.execute(
            "INSERT INTO test_numbers (negative) VALUES (?)",
            (min_int,)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT negative FROM test_numbers WHERE negative = ?", (min_int,))
        result = cursor.fetchone()
        assert result['negative'] == min_int

    def test_decimal_precision(self, edge_db):
        """小数精度"""
        pi = 3.141592653589793
        edge_db.execute(
            "INSERT INTO test_numbers (decimal_val) VALUES (?)",
            (pi,)
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT decimal_val FROM test_numbers WHERE decimal_val > ?", (3.14,))
        result = cursor.fetchone()
        assert result is not None
        assert abs(result['decimal_val'] - pi) < 0.0001


class TestNullHandling:
    """NULL值处理测试"""

    def test_null_vs_empty_string(self, edge_db):
        """NULL与空字符串区分"""
        edge_db.execute(
            "INSERT INTO domains (name, code, description) VALUES (?, ?, ?)",
            ("with_null", "NULL_TEST", None)
        )
        edge_db.execute(
            "INSERT INTO domains (name, code, description) VALUES (?, ?, ?)",
            ("with_empty", "EMPTY_TEST", "")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT * FROM domains WHERE code = 'NULL_TEST'")
        null_row = cursor.fetchone()
        assert null_row['description'] is None

        cursor = edge_db.execute("SELECT * FROM domains WHERE code = 'EMPTY_TEST'")
        empty_row = cursor.fetchone()
        assert empty_row['description'] == ""

    def test_null_in_aggregate_functions(self, edge_db):
        """NULL在聚合函数中的行为"""
        edge_db.execute("INSERT INTO test_numbers (positive) VALUES (10)")
        edge_db.execute("INSERT INTO test_numbers (positive) VALUES (NULL)")
        edge_db.execute("INSERT INTO test_numbers (positive) VALUES (20)")
        edge_db.commit()

        cursor = edge_db.execute("SELECT AVG(positive) as avg, COUNT(positive) as cnt FROM test_numbers")
        result = cursor.fetchone()
        assert result['cnt'] == 2, "COUNT应忽略NULL"
        assert result['avg'] == 15.0, "AVG应忽略NULL"

    def test_null_in_string_concatenation(self, edge_db):
        """NULL在字符串拼接中的行为"""
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            (None, "NULL_CONCAT")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT name || '_suffix' as concat FROM domains WHERE code = 'NULL_CONCAT'")
        result = cursor.fetchone()['concat']
        assert result is None


class TestDuplicateHandling:
    """重复数据处理测试"""

    def test_duplicate_unique_field_rejected(self, edge_db):
        """唯一字段重复应被拒绝"""
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            ("first", "DUPLICATE")
        )
        edge_db.commit()

        with pytest.raises(sqlite3.IntegrityError):
            edge_db.execute(
                "INSERT INTO domains (name, code) VALUES (?, ?)",
                ("second", "DUPLICATE")
            )
            edge_db.commit()

    def test_duplicate_non_unique_field_allowed(self, edge_db):
        """非唯一字段重复应被允许"""
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            ("same_name", "DUP_1")
        )
        edge_db.execute(
            "INSERT INTO domains (name, code) VALUES (?, ?)",
            ("same_name", "DUP_2")
        )
        edge_db.commit()

        cursor = edge_db.execute("SELECT COUNT(*) as cnt FROM domains WHERE name = 'same_name'")
        count = cursor.fetchone()['cnt']
        assert count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
