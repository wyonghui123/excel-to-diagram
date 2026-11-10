# -*- coding: utf-8 -*-
"""判定聚合方式（spec-rule-model M6b）

``constraint`` 规则可显式声明 ``combine_mode``，决定多个 key 的判定结果
如何聚合成最终结论：

- ``all``（默认）：全部 key 命中才构成结论（等价「同时突破所有限值」）
- ``any``        ：任一 key 命中即构成结论（等价「突破任一限值」）

约束：

- 词表封闭，配置期校验，不允许运行期自由字符串（NFR-003）；
- key 之间始终**全部求值**，不短路；聚合只决定最终结论，
  以保证 explain 能同时呈现每个 key 的度量值与结论（M6b 判定契约）。
"""

from __future__ import annotations

from typing import Any, Optional

COMBINE_MODES = ('any', 'all')
DEFAULT_COMBINE_MODE = 'all'


def normalize_combine_mode(value: Any) -> str:
    """未声明（空值）回退默认 ``all``，显式值原样返回（小写）。"""
    text = str(value or '').strip().lower()
    return text or DEFAULT_COMBINE_MODE


def validate_combine_mode(value: Any) -> Optional[str]:
    """校验 ``combine_mode`` 是否落在封闭词表内。

    未声明（空值）视为默认 ``all``，不报错。
    """
    text = str(value or '').strip().lower()
    if not text:
        return None
    if text not in COMBINE_MODES:
        return 'combine_mode %r 不在封闭词表 %s 内' % (text, list(COMBINE_MODES))
    return None