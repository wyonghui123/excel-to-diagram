# -*- coding: utf-8 -*-
"""
Formula 函数库

提供日期、字符串、数学、逻辑、高级等分类的公式函数，
通过 FormulaFunctionRegistry 统一注册管理，供 SafeExpressionEvaluator 动态调用。

设计原则：
1. 所有函数均为纯函数或弱依赖（仅依赖 datetime 等标准库）
2. 函数名大写，与 Salesforce Formula 风格一致
3. 空值安全：None 输入返回 None 而非抛异常
4. 类型宽容：自动尝试类型转换
"""

from typing import Any, Optional, List, Callable, Dict, Tuple
from datetime import date, datetime, timedelta
import math
import re
import logging

logger = logging.getLogger(__name__)


def _safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(v, fmt).date()
            except ValueError:
                continue
        return None
    return None


def _to_datetime(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                     "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f",
                     "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue
        return None
    return None


def _add_months_to_date(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _add_years_to_date(d: date, years: int) -> date:
    year = d.year + years
    day = min(d.day, _days_in_month(year, d.month))
    return date(year, d.month, day)


def _days_in_month(year: int, month: int) -> int:
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    elif month in (4, 6, 9, 11):
        return 30
    elif (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return 29
    else:
        return 28


def _month_diff(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


class DateFunctions:

    @staticmethod
    def TODAY() -> date:
        return date.today()

    @staticmethod
    def NOW() -> datetime:
        return datetime.now()

    @staticmethod
    def ADD_DAYS(d: Any, n: Any) -> Optional[date]:
        dt = _to_date(d)
        days = _safe_int(n)
        if dt is None or days is None:
            return None
        return dt + timedelta(days=days)

    @staticmethod
    def ADD_MONTHS(d: Any, n: Any) -> Optional[date]:
        dt = _to_date(d)
        months = _safe_int(n)
        if dt is None or months is None:
            return None
        return _add_months_to_date(dt, months)

    @staticmethod
    def ADD_YEARS(d: Any, n: Any) -> Optional[date]:
        dt = _to_date(d)
        years = _safe_int(n)
        if dt is None or years is None:
            return None
        return _add_years_to_date(dt, years)

    @staticmethod
    def DATEDIFF(d1: Any, d2: Any, unit: str = "days") -> Optional[int]:
        dt1 = _to_datetime(d1)
        dt2 = _to_datetime(d2)
        if dt1 is None or dt2 is None:
            return None
        unit_lower = (unit or "days").lower()
        if unit_lower == "days":
            return (dt2.date() - dt1.date()).days
        elif unit_lower == "months":
            return _month_diff(dt1.date(), dt2.date())
        elif unit_lower == "years":
            return dt2.year - dt1.year
        elif unit_lower == "hours":
            diff = dt2 - dt1
            return int(diff.total_seconds() // 3600)
        elif unit_lower == "minutes":
            diff = dt2 - dt1
            return int(diff.total_seconds() // 60)
        elif unit_lower == "seconds":
            diff = dt2 - dt1
            return int(diff.total_seconds())
        else:
            return (dt2.date() - dt1.date()).days

    @staticmethod
    def DAY(d: Any) -> Optional[int]:
        dt = _to_date(d)
        return dt.day if dt else None

    @staticmethod
    def MONTH(d: Any) -> Optional[int]:
        dt = _to_date(d)
        return dt.month if dt else None

    @staticmethod
    def YEAR(d: Any) -> Optional[int]:
        dt = _to_date(d)
        return dt.year if dt else None

    @staticmethod
    def DATE_STR(d: Any, fmt: str = "%Y-%m-%d") -> Optional[str]:
        dt = _to_date(d)
        if dt is None:
            return None
        return dt.strftime(fmt)


class StringFunctions:

    @staticmethod
    def CONCAT(*args: Any) -> str:
        return "".join(str(a) for a in args if a is not None)

    @staticmethod
    def SUBSTRING(s: Any, start: Any, length: Any = None) -> Optional[str]:
        sv = _safe_str(s)
        if sv is None:
            return None
        st = _safe_int(start)
        if st is None:
            return None
        idx = max(st - 1, 0) if st > 0 else 0
        if length is not None:
            ln = _safe_int(length)
            if ln is None:
                return None
            return sv[idx:idx + ln]
        return sv[idx:]

    @staticmethod
    def UPPER(s: Any) -> Optional[str]:
        sv = _safe_str(s)
        return sv.upper() if sv else None

    @staticmethod
    def LOWER(s: Any) -> Optional[str]:
        sv = _safe_str(s)
        return sv.lower() if sv else None

    @staticmethod
    def TRIM(s: Any) -> Optional[str]:
        sv = _safe_str(s)
        return sv.strip() if sv else None

    @staticmethod
    def LTRIM(s: Any) -> Optional[str]:
        sv = _safe_str(s)
        return sv.lstrip() if sv else None

    @staticmethod
    def RTRIM(s: Any) -> Optional[str]:
        sv = _safe_str(s)
        return sv.rstrip() if sv else None

    @staticmethod
    def REPLACE(s: Any, old: Any, new: Any) -> Optional[str]:
        sv = _safe_str(s)
        if sv is None:
            return None
        return sv.replace(str(old), str(new))

    @staticmethod
    def CONTAINS(s: Any, sub: Any) -> Optional[bool]:
        sv = _safe_str(s)
        if sv is None:
            return None
        return str(sub) in sv

    @staticmethod
    def STARTS_WITH(s: Any, prefix: Any) -> Optional[bool]:
        sv = _safe_str(s)
        if sv is None:
            return None
        return sv.startswith(str(prefix))

    @staticmethod
    def ENDS_WITH(s: Any, suffix: Any) -> Optional[bool]:
        sv = _safe_str(s)
        if sv is None:
            return None
        return sv.endswith(str(suffix))

    @staticmethod
    def LENGTH(s: Any) -> Optional[int]:
        sv = _safe_str(s)
        return len(sv) if sv else None


class MathFunctions:

    @staticmethod
    def ROUND(n: Any, digits: Any = 0) -> Optional[float]:
        nv = _safe_float(n)
        dv = _safe_int(digits) or 0
        if nv is None:
            return None
        return round(nv, dv)

    @staticmethod
    def CEIL(n: Any) -> Optional[int]:
        nv = _safe_float(n)
        return math.ceil(nv) if nv is not None else None

    @staticmethod
    def FLOOR(n: Any) -> Optional[int]:
        nv = _safe_float(n)
        return math.floor(nv) if nv is not None else None

    @staticmethod
    def POWER(base: Any, exp: Any) -> Optional[float]:
        bv = _safe_float(base)
        ev = _safe_float(exp)
        if bv is None or ev is None:
            return None
        return math.pow(bv, ev)

    @staticmethod
    def SQRT(n: Any) -> Optional[float]:
        nv = _safe_float(n)
        if nv is None or nv < 0:
            return None
        return math.sqrt(nv)

    @staticmethod
    def MOD(n: Any, divisor: Any) -> Optional[int]:
        nv = _safe_int(n)
        dv = _safe_int(divisor)
        if nv is None or dv is None or dv == 0:
            return None
        return nv % dv

    @staticmethod
    def DIVIDE(numerator: Any, denominator: Any, default: Any = 0) -> Any:
        num = _safe_float(numerator)
        den = _safe_float(denominator)
        if num is None or den is None or den == 0:
            return default
        return num / den

    @staticmethod
    def LOG(n: Any) -> Optional[float]:
        nv = _safe_float(n)
        if nv is None or nv <= 0:
            return None
        return math.log(nv)

    @staticmethod
    def LOG10(n: Any) -> Optional[float]:
        nv = _safe_float(n)
        if nv is None or nv <= 0:
            return None
        return math.log10(nv)


class LogicFunctions:

    @staticmethod
    def IF(condition: Any, true_value: Any, false_value: Any) -> Any:
        return true_value if condition else false_value

    @staticmethod
    def COALESCE(*args: Any) -> Any:
        for arg in args:
            if arg is not None:
                return arg
        return None

    @staticmethod
    def ISNULL(v: Any) -> bool:
        return v is None

    @staticmethod
    def ISBLANK(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and v.strip() == "":
            return True
        return False

    @staticmethod
    def CASE(expr: Any, *args: Any) -> Any:
        if len(args) < 2:
            return None
        pairs = args[:-1]
        default = args[-1]
        for i in range(0, len(pairs), 2):
            if i + 1 < len(pairs):
                if expr == pairs[i]:
                    return pairs[i + 1]
        if len(args) % 2 == 1:
            return default
        return None


class AdvancedFunctions:

    @staticmethod
    def REGEX_MATCH(s: Any, pattern: Any) -> Optional[bool]:
        sv = _safe_str(s)
        pv = _safe_str(pattern)
        if sv is None or pv is None:
            return None
        try:
            return bool(re.search(pv, sv))
        except re.error:
            return None

    @staticmethod
    def FORMAT_NUMBER(n: Any, pattern: Any) -> Optional[str]:
        nv = _safe_float(n)
        pv = _safe_str(pattern)
        if nv is None or pv is None:
            return None
        try:
            return format(nv, pv)
        except (ValueError, TypeError):
            return str(nv)


class FormulaFunctionRegistry:
    """
    Formula 函数注册中心

    统一管理所有 Formula 函数的注册、查找和调用。
    支持动态注册自定义函数。
    """

    _functions: Dict[str, Callable] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return
        cls._initialized = True
        cls._register_builtins()
        cls._register_date_functions()
        cls._register_string_functions()
        cls._register_math_functions()
        cls._register_logic_functions()
        cls._register_advanced_functions()

    @classmethod
    def _register_builtins(cls) -> None:
        builtin_map = {
            'len': len, 'str': str, 'int': int, 'float': float,
            'bool': bool, 'abs': abs, 'min': min, 'max': max,
            'sum': sum, 'any': any, 'all': all,
        }
        for name, func in builtin_map.items():
            cls._functions[name] = func

    @classmethod
    def _register_date_functions(cls) -> None:
        df = DateFunctions
        for name in ['TODAY', 'NOW', 'ADD_DAYS', 'ADD_MONTHS', 'ADD_YEARS',
                      'DATEDIFF', 'DAY', 'MONTH', 'YEAR', 'DATE_STR']:
            cls._functions[name] = getattr(df, name)

    @classmethod
    def _register_string_functions(cls) -> None:
        sf = StringFunctions
        for name in ['CONCAT', 'SUBSTRING', 'UPPER', 'LOWER', 'TRIM',
                      'LTRIM', 'RTRIM', 'REPLACE', 'CONTAINS',
                      'STARTS_WITH', 'ENDS_WITH', 'LENGTH']:
            cls._functions[name] = getattr(sf, name)

    @classmethod
    def _register_math_functions(cls) -> None:
        mf = MathFunctions
        for name in ['ROUND', 'CEIL', 'FLOOR', 'POWER', 'SQRT', 'MOD', 'DIVIDE',
                      'LOG', 'LOG10']:
            cls._functions[name] = getattr(mf, name)

    @classmethod
    def _register_logic_functions(cls) -> None:
        lf = LogicFunctions
        for name in ['IF', 'COALESCE', 'ISNULL', 'ISBLANK', 'CASE']:
            cls._functions[name] = getattr(lf, name)

    @classmethod
    def _register_advanced_functions(cls) -> None:
        af = AdvancedFunctions
        for name in ['REGEX_MATCH', 'FORMAT_NUMBER']:
            cls._functions[name] = getattr(af, name)

    @classmethod
    def register(cls, name: str, func: Callable) -> None:
        cls._ensure_initialized()
        cls._functions[name] = func

    @classmethod
    def unregister(cls, name: str) -> bool:
        cls._ensure_initialized()
        if name in cls._functions:
            del cls._functions[name]
            return True
        return False

    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        cls._ensure_initialized()
        return cls._functions.get(name)

    @classmethod
    def has(cls, name: str) -> bool:
        cls._ensure_initialized()
        return name in cls._functions

    @classmethod
    def list_functions(cls) -> Dict[str, str]:
        cls._ensure_initialized()
        return {name: (func.__doc__ or "").strip().split("\n")[0]
                for name, func in cls._functions.items()}

    @classmethod
    def list_names(cls) -> List[str]:
        cls._ensure_initialized()
        return sorted(cls._functions.keys())

    @classmethod
    def get_allowed_functions(cls) -> frozenset:
        cls._ensure_initialized()
        return frozenset(cls._functions.keys())

    @classmethod
    def build_locals(cls, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cls._ensure_initialized()
        result = dict(cls._functions)
        if extra:
            result.update(extra)
        return result
