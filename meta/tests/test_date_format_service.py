import pytest

pytestmark = pytest.mark.integration

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from meta.services.date_format_service import DateFormatService


class TestDateFormatServiceUnit:
    """DateFormatService 单元测试（mock data_source）"""

    @pytest.fixture
    def mock_ds(self):
        """创建 mock data_source"""
        ds = MagicMock()
        return ds

    @pytest.fixture
    def service_zh_cn(self, mock_ds):
        """中文用户服务（默认值）"""
        mock_ds.query.return_value = [{
            'id': 1, 'locale': 'zh-CN', 'timezone': 'Asia/Shanghai',
            'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 24
        }]
        return DateFormatService(mock_ds, 1)

    @pytest.fixture
    def service_en_us(self, mock_ds):
        """美式英语用户服务"""
        mock_ds.query.return_value = [{
            'id': 2, 'locale': 'en-US', 'timezone': 'America/New_York',
            'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 12
        }]
        return DateFormatService(mock_ds, 2)

    @pytest.fixture
    def service_en_gb(self, mock_ds):
        """英式英语用户服务"""
        mock_ds.query.return_value = [{
            'id': 3, 'locale': 'en-GB', 'timezone': 'Europe/London',
            'date_style': 'medium', 'time_style': 'short', 'hour_cycle': 24
        }]
        return DateFormatService(mock_ds, 3)

    @pytest.fixture
    def service_no_user(self, mock_ds):
        """用户不存在的服务"""
        mock_ds.query.return_value = []
        return DateFormatService(mock_ds, 999)

    def test_format_datetime_default_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt)
        assert '2025' in result
        assert '05' in result or '5' in result
        assert '24' in result
        assert '14:30' in result

    def test_format_datetime_medium_short_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt, date_style='medium', time_style='short')
        assert '2025-05-24' in result
        assert '14:30' in result

    def test_format_datetime_full_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 6, 15, 8, 0, 0)
        result = service_zh_cn.format_datetime(dt, date_style='full', time_style='full')
        assert '2025年' in result
        assert '6月' in result or '06月' in result
        assert '日' in result

    def test_format_datetime_long_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt, date_style='long', time_style='long')
        assert '2025年' in result
        assert '14:30:00' in result

    def test_format_datetime_short_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt, date_style='short', time_style='short')
        assert '25-05-24' in result

    def test_format_datetime_en_us_12h(self, service_en_us):
        dt = datetime(2025, 5, 24, 18, 30, 0)
        result = service_en_us.format_datetime(dt, date_style='medium', time_style='short')
        assert 'PM' in result

    def test_format_datetime_en_gb_24h(self, service_en_gb):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_en_gb.format_datetime(dt, date_style='medium', time_style='short')
        assert '07:30' in result

    def test_timezone_override(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 12, 0, 0)
        result_default = service_zh_cn.format_datetime(dt)
        result_override = service_zh_cn.format_datetime(dt, timezone='UTC')
        assert result_default != result_override

    def test_date_style_override(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt, date_style='long')
        assert '2025年' in result

    def test_time_style_override(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        result = service_zh_cn.format_datetime(dt, time_style='long')
        assert '14:30:00' in result

    def test_no_user_fallback_defaults(self, service_no_user):
        dt = datetime(2025, 5, 24, 12, 0, 0)
        result = service_no_user.format_datetime(dt)
        assert result and result != ''

    def test_no_user_timezone_fallback_utc(self, service_no_user):
        dt = datetime(2025, 5, 24, 12, 0, 0)
        result = service_no_user.format_datetime(dt, timezone='UTC')
        assert '12:00' in result

    def test_invalid_timezone_fallback_utc(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 12, 0, 0)
        result = service_zh_cn.format_datetime(dt, timezone='Invalid/Zone')
        assert result and result != ''

    def test_get_user_timezone(self, service_zh_cn):
        assert service_zh_cn.get_user_timezone() == 'Asia/Shanghai'

    def test_get_user_locale(self, service_zh_cn):
        assert service_zh_cn.get_user_locale() == 'zh-CN'

    def test_get_user_timezone_no_user(self, service_no_user):
        assert service_no_user.get_user_timezone() == 'UTC'

    def test_get_user_locale_no_user(self, service_no_user):
        assert service_no_user.get_user_locale() == 'zh-CN'

    def test_format_datetime_with_tz_aware_input(self, service_zh_cn):
        import pytz
        tz = pytz.timezone('UTC')
        dt = tz.localize(datetime(2025, 5, 24, 12, 0, 0))
        result = service_zh_cn.format_datetime(dt)
        assert '20:00' in result

    def test_all_date_styles_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 12, 15, 6, 0, 0)
        for style in ['full', 'long', 'medium', 'short']:
            result = service_zh_cn.format_datetime(dt, date_style=style, time_style='short')
            assert result and isinstance(result, str), f"Style {style} failed"

    def test_all_time_styles_zh_cn(self, service_zh_cn):
        dt = datetime(2025, 5, 24, 6, 30, 0)
        for style in ['full', 'long', 'medium', 'short']:
            result = service_zh_cn.format_datetime(dt, date_style='medium', time_style=style)
            assert result and isinstance(result, str), f"Time style {style} failed"

    def test_hour_cycle_12_formats(self, service_en_us):
        """12小时制所有时间格式都应包含AM/PM"""
        dt = datetime(2025, 5, 24, 18, 30, 0)
        for style in ['full', 'long', 'medium', 'short']:
            result = service_en_us.format_datetime(dt, date_style='medium', time_style=style)
            assert result and isinstance(result, str)
            if style != 'short':
                assert 'PM' in result

    def test_language_defaults_structure(self):
        """LANGUAGE_DEFAULTS 包含所有支持的语言"""
        assert 'zh-CN' in DateFormatService.LANGUAGE_DEFAULTS
        assert 'en-US' in DateFormatService.LANGUAGE_DEFAULTS
        assert 'en-GB' in DateFormatService.LANGUAGE_DEFAULTS

    def test_date_formats_structure(self):
        assert set(DateFormatService.DATE_FORMATS.keys()) == {'full', 'long', 'medium', 'short'}

    def test_time_formats_structure(self):
        expected = {'full', 'long', 'medium', 'short'}
        assert set(DateFormatService.TIME_FORMATS_24.keys()) == expected
        assert set(DateFormatService.TIME_FORMATS_12.keys()) == expected
