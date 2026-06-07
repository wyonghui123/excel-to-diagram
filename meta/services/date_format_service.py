from datetime import datetime
from typing import Optional, Dict, Any
import pytz


class DateFormatService:
    """日期格式化服务，支持时区转换和多语言默认配置"""

    LANGUAGE_DEFAULTS = {
        'zh-CN': {'hour_cycle': 24},
        'en-US': {'hour_cycle': 12},
        'en-GB': {'hour_cycle': 24},
    }

    DATE_FORMATS = {
        'full': '%Y年%m月%d日 %A',
        'long': '%Y年%m月%d日',
        'medium': '%Y-%m-%d',
        'short': '%y-%m-%d',
    }

    TIME_FORMATS_24 = {
        'full': '%H:%M:%S %Z',
        'long': '%H:%M:%S',
        'medium': '%H:%M:%S',
        'short': '%H:%M',
    }

    TIME_FORMATS_12 = {
        'full': '%I:%M:%S %p %Z',
        'long': '%I:%M:%S %p',
        'medium': '%I:%M:%S %p',
        'short': '%I:%M %p',
    }

    def __init__(self, data_source, user_id: int):
        self.data_source = data_source
        self.user_id = user_id
        self._user = None

    def _get_user(self) -> Dict[str, Any]:
        if self._user is None:
            result = self.data_source.query(
                "SELECT * FROM users WHERE id = ?", (self.user_id,)
            )
            self._user = result[0] if result else {}
        return self._user

    def format_datetime(
        self,
        dt: datetime,
        date_style: str = 'medium',
        time_style: str = 'short',
        timezone: Optional[str] = None,
    ) -> str:
        user = self._get_user()

        tz_name = timezone or user.get('timezone', 'UTC')
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.UTC

        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        local_dt = dt.astimezone(tz)

        locale = user.get('locale', 'zh-CN')
        hour_cycle = user.get('hour_cycle', 24)

        date_fmt = self.DATE_FORMATS.get(date_style, self.DATE_FORMATS['medium'])
        time_fmts = self.TIME_FORMATS_24 if hour_cycle == 24 else self.TIME_FORMATS_12
        time_fmt = time_fmts.get(time_style, time_fmts['short'])

        return local_dt.strftime(f"{date_fmt} {time_fmt}")

    def get_user_timezone(self) -> str:
        user = self._get_user()
        return user.get('timezone', 'UTC')

    def get_user_locale(self) -> str:
        user = self._get_user()
        return user.get('locale', 'zh-CN')
