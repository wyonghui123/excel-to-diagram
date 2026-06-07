import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
import pytest
from datetime import datetime, timedelta
from meta.core.cron_parser import CronParser


class TestCronParserParse:
    
    def test_parse_every_minute(self):
        parser = CronParser()
        result = parser.parse("* * * * *")
        assert result['minute'] == set(range(60))
        assert result['hour'] == set(range(24))
        assert result['day'] == set(range(1, 32))
        assert result['month'] == set(range(1, 13))
        assert result['weekday'] == set(range(7))
    
    def test_parse_specific_time(self):
        parser = CronParser()
        result = parser.parse("30 14 * * *")
        assert result['minute'] == {30}
        assert result['hour'] == {14}
    
    def test_parse_step_values(self):
        parser = CronParser()
        result = parser.parse("*/5 * * * *")
        assert result['minute'] == set(range(0, 60, 5))
    
    def test_parse_range(self):
        parser = CronParser()
        result = parser.parse("0 9-17 * * *")
        assert result['hour'] == set(range(9, 18))
    
    def test_parse_multiple_values(self):
        parser = CronParser()
        result = parser.parse("0,30 8,12,18 * * *")
        assert result['minute'] == {0, 30}
        assert result['hour'] == {8, 12, 18}
    
    def test_parse_weekday(self):
        parser = CronParser()
        result = parser.parse("0 9 * * 1-5")
        assert result['weekday'] == {1, 2, 3, 4, 5}
    
    def test_parse_month_specific(self):
        parser = CronParser()
        result = parser.parse("0 0 1 1,6,12 *")
        assert result['month'] == {1, 6, 12}
        assert result['day'] == {1}
    
    def test_parse_invalid_expression(self):
        parser = CronParser()
        with pytest.raises(ValueError):
            parser.parse("invalid")
    
    def test_parse_too_few_fields(self):
        parser = CronParser()
        with pytest.raises(ValueError):
            parser.parse("* * * *")
    
    def test_parse_too_many_fields(self):
        parser = CronParser()
        with pytest.raises(ValueError):
            parser.parse("* * * * * *")


class TestCronParserGetNext:
    
    def test_get_next_every_minute(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 30, 45)
        next_run = parser.get_next("* * * * *", now)
        assert next_run == datetime(2026, 5, 23, 10, 31, 0)
    
    def test_get_next_specific_hour(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 30, 0)
        next_run = parser.get_next("0 14 * * *", now)
        assert next_run == datetime(2026, 5, 23, 14, 0, 0)
    
    def test_get_next_specific_hour_next_day(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 15, 30, 0)
        next_run = parser.get_next("0 14 * * *", now)
        assert next_run == datetime(2026, 5, 24, 14, 0, 0)
    
    def test_get_next_step_minutes(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 32, 0)
        next_run = parser.get_next("*/5 * * * *", now)
        assert next_run == datetime(2026, 5, 23, 10, 35, 0)
    
    def test_get_next_weekday(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 15, 0, 0)
        next_run = parser.get_next("0 9 * * 1", now)
        assert next_run.weekday() == 0
        assert next_run.hour == 9
        assert next_run.minute == 0
    
    def test_get_next_month_specific(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 0, 0)
        next_run = parser.get_next("0 0 1 6 *", now)
        assert next_run.month == 6
        assert next_run.day == 1
    
    def test_get_next_midnight(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 23, 45, 0)
        next_run = parser.get_next("0 0 * * *", now)
        assert next_run == datetime(2026, 5, 24, 0, 0, 0)
    
    def test_get_next_every_2_minutes(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 31, 0)
        next_run = parser.get_next("*/2 * * * *", now)
        assert next_run == datetime(2026, 5, 23, 10, 32, 0)
    
    def test_get_next_every_10_minutes(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 10, 35, 0)
        next_run = parser.get_next("*/10 * * * *", now)
        assert next_run == datetime(2026, 5, 23, 10, 40, 0)
    
    def test_get_next_sunday_4am(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 15, 0, 0)
        next_run = parser.get_next("0 4 * * 0", now)
        assert next_run.weekday() == 6
        assert next_run.hour == 4


class TestCronParserDescribe:
    
    def test_describe_every_minute(self):
        parser = CronParser()
        desc = parser.describe("* * * * *")
        assert "每分钟" in desc
    
    def test_describe_specific_time(self):
        parser = CronParser()
        desc = parser.describe("30 14 * * *")
        assert "14:30" in desc or "14" in desc
    
    def test_describe_step_minutes(self):
        parser = CronParser()
        desc = parser.describe("*/5 * * * *")
        assert "5" in desc
    
    def test_describe_daily(self):
        parser = CronParser()
        desc = parser.describe("0 2 * * *")
        assert "每天" in desc or "2" in desc
    
    def test_describe_weekly(self):
        parser = CronParser()
        desc = parser.describe("0 9 * * 1")
        assert "每天" in desc or "09:00" in desc or "9" in desc


class TestCronParserEdgeCases:
    
    def test_leap_year_february(self):
        parser = CronParser()
        now = datetime(2024, 2, 28, 23, 0, 0)
        next_run = parser.get_next("0 0 29 2 *", now)
        assert next_run.month == 2
        assert next_run.day == 29
    
    def test_year_boundary(self):
        parser = CronParser()
        now = datetime(2026, 12, 31, 23, 0, 0)
        next_run = parser.get_next("0 0 1 1 *", now)
        assert next_run.year == 2027
        assert next_run.month == 1
        assert next_run.day == 1
    
    def test_month_boundary(self):
        parser = CronParser()
        now = datetime(2026, 5, 31, 10, 0, 0)
        next_run = parser.get_next("0 0 1 * *", now)
        assert next_run.day == 1
        assert next_run.month == 6
    
    def test_hour_boundary(self):
        parser = CronParser()
        now = datetime(2026, 5, 23, 23, 30, 0)
        next_run = parser.get_next("0 0 * * *", now)
        assert next_run.day == 24
        assert next_run.hour == 0
