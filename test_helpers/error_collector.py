"""
Unified error collector — aggregates errors across all testing layers

Layers:
  - page   : Playwright page.on('pageerror') — uncaught JS runtime errors
  - console: console.error / console.warn (from inject_helpers.js hijacking)
  - vue    : window.__appErrors (from main.js errorHandler + unhandledrejection)
  - network: HTTP 4xx/5xx (future)
  - health : page crash / missing #app / dom not found
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import time


@dataclass
class TestError:
    layer: str
    level: str
    message: str
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)


class ErrorCollector:
    """
    Unified error collector — aggregates errors from all layers.

    Usage:
        collector = ErrorCollector()
        # ... run test operations ...
        if not collector.is_healthy():
            print(collector.summary())
            raise PageHealthError(collector.summary())
    """

    def __init__(self):
        self.errors: List[TestError] = []

    def add_page_error(self, message: str):
        self.errors.append(TestError(
            layer='page', level='error', message=message
        ))

    def add_console_error(self, message: str):
        self.errors.append(TestError(
            layer='console', level='error', message=message
        ))

    def add_console_warning(self, message: str):
        self.errors.append(TestError(
            layer='console', level='warning', message=message
        ))

    def add_vue_error(self, message: str, component: str = ''):
        self.errors.append(TestError(
            layer='vue', level='error', message=message,
            context={'component': component}
        ))

    def add_health_failure(self, message: str):
        self.errors.append(TestError(
            layer='health', level='error', message=message
        ))

    @property
    def has_errors(self) -> bool:
        return any(e.level == 'error' for e in self.errors)

    @property
    def has_warnings(self) -> bool:
        return any(e.level == 'warning' for e in self.errors)

    def is_healthy(self) -> bool:
        return not self.has_errors

    def summary(self) -> str:
        lines = []
        errors = [e for e in self.errors if e.level == 'error']
        warnings = [e for e in self.errors if e.level == 'warning']
        total = len(errors) + len(warnings)
        lines.append(f"[ErrorCollector] {total} issue(s): {len(errors)} errors, {len(warnings)} warnings")
        for e in errors:
            ctx = f" ({e.context.get('component', '')})" if e.context.get('component') else ''
            lines.append(f"  [ERROR][{e.layer}]{ctx} {e.message}")
        for e in warnings:
            lines.append(f"  [WARN][{e.layer}] {e.message}")
        return '\n'.join(lines)

    def to_dict(self) -> Dict:
        return {
            'healthy': self.is_healthy(),
            'error_count': sum(1 for e in self.errors if e.level == 'error'),
            'warning_count': sum(1 for e in self.errors if e.level == 'warning'),
            'errors': [
                {
                    'layer': e.layer,
                    'level': e.level,
                    'message': e.message,
                    'context': e.context
                }
                for e in self.errors
            ]
        }


class PageHealthError(Exception):
    """Page health check failed — page is unusable for testing"""

    def __init__(self, summary: str, details: dict = None):
        self.summary = summary
        self.details = details or {}
        super().__init__(summary)


class TestTimeoutError(Exception):
    """Test operation timed out"""

    def __init__(self, operation: str, timeout_ms: int, last_state: dict = None):
        self.operation = operation
        self.timeout_ms = timeout_ms
        self.last_state = last_state or {}
        msg = f"Operation '{operation}' timed out after {timeout_ms}ms"
        if last_state:
            msg += f"\n  Last known state: {last_state}"
        super().__init__(msg)
