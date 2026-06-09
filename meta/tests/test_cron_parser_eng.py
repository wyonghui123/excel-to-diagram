# -*- coding: utf-8 -*-
"""
SVC-017: cron_parser (8 测试) - Cron 表达式解析器

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] parse / get_next / describe + _parse_field (internal)
"""
from datetime import datetime
import pytest
from meta.core.cron_parser import CronParser

pytestmark = [pytest.mark.unit]


class TestCronParser:
    """CronParser 测试 (8 用例)"""

    def setup_method(self):
        """每个测试用新 parser (避免 _cache 污染)"""
        self.cp = CronParser()

    def test_parse_wildcard(self):
        """'* * * * *' → 全部 60/24/31/12/7"""
        result = self.cp.parse('* * * * *')
        assert result['minute'] == set(range(0, 60))
        assert result['hour'] == set(range(0, 24))
        assert result['day'] == set(range(1, 32))
        assert result['month'] == set(range(1, 13))
        assert result['weekday'] == set(range(0, 7))

    def test_parse_step(self):
        """'*/15 * * * *' → minute = {0, 15, 30, 45}"""
        result = self.cp.parse('*/15 * * * *')
        assert result['minute'] == {0, 15, 30, 45}
        assert len(result['minute']) == 4

    def test_parse_range(self):
        """'9-17 * * * *' → hour = {9,10,...,17}"""
        result = self.cp.parse('* 9-17 * * *')
        assert result['hour'] == {9, 10, 11, 12, 13, 14, 15, 16, 17}

    def test_parse_list(self):
        """'0,30 * * * *' → minute = {0, 30}"""
        result = self.cp.parse('0,30 * * * *')
        assert result['minute'] == {0, 30}

    def test_parse_invalid_field_count_raises(self):
        """非 5 字段 → ValueError"""
        with pytest.raises(ValueError) as exc_info:
            self.cp.parse('* * *')  # 只有 3 字段
        assert 'Invalid cron expression' in str(exc_info.value)

    def test_get_next_daily_at_9am(self):
        """'0 9 * * *' → next 9:00 from given time"""
        # 2026-06-08 08:00:00 → next 09:00 同日
        after = datetime(2026, 6, 8, 8, 0, 0)
        result = self.cp.get_next('0 9 * * *', after)
        assert result == datetime(2026, 6, 8, 9, 0, 0)

    def test_describe_every_minute(self):
        """'* * * * *' → '每分钟'"""
        result = self.cp.describe('* * * * *')
        assert result == '每分钟'

    def test_describe_daily_at_specific_time(self):
        """'30 14 * * *' → '每天 14:30'"""
        result = self.cp.describe('30 14 * * *')
        assert result == '每天 14:30'

    # ---------- _parse_field 边界值 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('value,range_tuple,expected_count,id_label', [
        pytest.param('*', (0, 59), 60, 'star_full_range', id='star'),
        pytest.param('*/2', (0, 10), 6, 'step_evens', id='step'),
        pytest.param('5,15,25', (0, 59), 3, 'list_3_items', id='list'),
    ])
    def test_parse_field_edge_cases(self, value, range_tuple, expected_count, id_label):
        """_parse_field 3 种语法 (star/step/list)"""
        result = self.cp._parse_field(value, range_tuple)
        assert len(result) == expected_count
