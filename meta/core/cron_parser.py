# -*- coding: utf-8 -*-
import re
from datetime import datetime, timedelta
from typing import Optional


class CronParser:
    """Cron表达式解析器"""
    
    FIELD_NAMES = ['minute', 'hour', 'day', 'month', 'weekday']
    FIELD_RANGES = {
        'minute': (0, 59),
        'hour': (0, 23),
        'day': (1, 31),
        'month': (1, 12),
        'weekday': (0, 6),
    }
    
    def __init__(self):
        self._cache = {}
    
    def parse(self, expression: str) -> dict:
        if expression in self._cache:
            return self._cache[expression]
        
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")
        
        result = {}
        for i, field_name in enumerate(self.FIELD_NAMES):
            result[field_name] = self._parse_field(
                fields[i], self.FIELD_RANGES[field_name]
            )
        
        self._cache[expression] = result
        return result
    
    def _parse_field(self, value: str, range_tuple: tuple) -> set:
        lo, hi = range_tuple
        
        if value == '*':
            return set(range(lo, hi + 1))
        
        if value.startswith('*/'):
            step = int(value[2:])
            return set(range(lo, hi + 1, step))
        
        result = set()
        for part in value.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                result.update(range(start, end + 1))
            else:
                result.add(int(part))
        
        return result
    
    def get_next(self, expression: str, after: datetime) -> Optional[datetime]:
        parsed = self.parse(expression)
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end_date = current + timedelta(days=1460)
        
        while current <= end_date:
            if (
                current.minute in parsed['minute']
                and current.hour in parsed['hour']
                and current.day in parsed['day']
                and current.month in parsed['month']
                and (current.weekday() in parsed['weekday']
                     or current.isoweekday() % 7 in parsed['weekday'])
            ):
                return current
            current = current + timedelta(minutes=1)
        
        return None
    
    def describe(self, expression: str) -> str:
        parsed = self.parse(expression)
        
        if len(parsed['minute']) == 60 and len(parsed['hour']) == 24:
            return "每分钟"
        
        if len(parsed['minute']) == 1:
            minute = min(parsed['minute'])
            if len(parsed['hour']) == 1:
                hour = min(parsed['hour'])
                return f"每天 {hour:02d}:{minute:02d}"
            if len(parsed['hour']) > 1:
                return f"每小时第{minute}分钟"
        
        minutes = sorted(parsed['minute'])
        if len(minutes) >= 2:
            step = minutes[1] - minutes[0]
            if all(
                minutes[i + 1] - minutes[i] == step
                for i in range(len(minutes) - 1)
            ):
                return f"每{step}分钟"
        
        return expression