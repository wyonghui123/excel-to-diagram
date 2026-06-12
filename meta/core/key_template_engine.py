# -*- coding: utf-8 -*-
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

_SEQUENCES_TABLE = "_sequences"
_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {_SEQUENCES_TABLE} (
    sequence_name TEXT PRIMARY KEY,
    current_value INTEGER NOT NULL DEFAULT 0,
    last_reset_at TEXT DEFAULT NULL
)
"""


@dataclass
class SequenceConfig:
    start: int = 1
    step: int = 1
    padding: int = 0
    reset_strategy: str = ""
    reset_scope: List[str] = field(default_factory=list)

    RESET_POLICIES = frozenset({"", "never", "daily", "monthly", "yearly"})

    def __post_init__(self):
        if self.reset_strategy not in self.RESET_POLICIES:
            raise ValueError(
                f"Invalid reset_strategy: {self.reset_strategy}. "
                f"Must be one of {self.RESET_POLICIES}"
            )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SequenceConfig":
        if not data:
            return cls()
        return cls(
            start=data.get("start", 1),
            step=data.get("step", 1),
            padding=data.get("padding", 0),
            reset_strategy=data.get("reset_strategy", data.get("reset", "")),
            reset_scope=data.get("reset_scope", data.get("scope_fields", [])),
        )

    @classmethod
    def from_segments(cls, segments: List[Dict[str, Any]]) -> "SequenceConfig":
        for seg in segments:
            if seg.get("type") == "sequence":
                return cls(
                    start=seg.get("start", 1),
                    step=1,
                    padding=seg.get("padding", 0),
                    reset_strategy="",
                    reset_scope=[],
                )
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "start": self.start,
            "step": self.step,
            "padding": self.padding,
        }
        if self.reset_strategy:
            result["reset_strategy"] = self.reset_strategy
        if self.reset_scope:
            result["reset_scope"] = self.reset_scope
        return result


@dataclass
class KeyTemplateConfig:
    object_id: str
    enabled: bool = False
    # [NEW v1.1 2026-06-11] 用户可编辑模式
    user_editable: str = "auto_or_manual"
    auto_suggest: bool = True
    pattern: str = ""
    separator: str = "_"
    segments: List[Dict[str, Any]] = field(default_factory=list)
    preview: str = ""
    scope: Optional[str] = None
    sequence: Optional[SequenceConfig] = None

    def __post_init__(self):
        """[NEW v1.1] 校验 user_editable 字段值合法"""
        valid = {"auto_only", "auto_or_manual", "manual_only"}
        if self.user_editable not in valid:
            raise ValueError(
                f"Invalid user_editable: {self.user_editable!r}. "
                f"Must be one of {sorted(valid)}"
            )

    @classmethod
    def from_dict(cls, object_id: str, data: Dict[str, Any]) -> "KeyTemplateConfig":
        if not data:
            return cls(object_id=object_id, enabled=False)

        sequence = None
        seq_data = data.get("sequence")
        if seq_data and isinstance(seq_data, dict):
            sequence = SequenceConfig.from_dict(seq_data)
        elif data.get("segments"):
            sequence = SequenceConfig.from_segments(data.get("segments", []))

        # [NEW v1.1] 默认 auto_or_manual
        user_editable = data.get("user_editable", "auto_or_manual")

        return cls(
            object_id=object_id,
            enabled=data.get("enabled", False),
            user_editable=user_editable,
            auto_suggest=data.get("auto_suggest", True),
            pattern=data.get("pattern", ""),
            separator=data.get("separator", "_"),
            segments=data.get("segments", []),
            preview=data.get("preview", ""),
            scope=data.get("scope"),
            sequence=sequence,
        )


class SequenceEngine:

    def __init__(self, data_source):
        self._data_source = data_source
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self):
        try:
            self._data_source.execute(_CREATE_TABLE_SQL)
            self._data_source.commit()
            try:
                self._data_source.execute(
                    "ALTER TABLE _sequences ADD COLUMN last_reset_at TEXT DEFAULT NULL"
                )
                self._data_source.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[SequenceEngine] Table ensure: {e}")

    def _should_reset(self, sequence_name: str, reset_strategy: str) -> bool:
        if not reset_strategy or reset_strategy == "never":
            return False

        cursor = self._data_source.execute(
            f"SELECT last_reset_at FROM {_SEQUENCES_TABLE} WHERE sequence_name = ?",
            (sequence_name,)
        )
        row = cursor.fetchone()
        if not row:
            return False

        last_reset = row[0] if not isinstance(row, dict) else row.get("last_reset_at")
        if not last_reset:
            return False

        from datetime import datetime
        try:
            last_dt = datetime.fromisoformat(last_reset)
            now = datetime.now()
            if reset_strategy == "daily":
                return last_dt.date() < now.date()
            elif reset_strategy == "monthly":
                return (last_dt.year, last_dt.month) < (now.year, now.month)
            elif reset_strategy == "yearly":
                return last_dt.year < now.year
        except (ValueError, TypeError):
            pass
        return False

    def _do_reset(self, sequence_name: str, start: int = 1) -> None:
        from datetime import datetime
        now_str = datetime.now().isoformat()
        self._data_source.execute(
            f"UPDATE {_SEQUENCES_TABLE} SET current_value = ?, last_reset_at = ? "
            f"WHERE sequence_name = ?",
            (start - 1, now_str, sequence_name)
        )
        self._data_source.commit()

    def next_value(self, sequence_name: str, start: int = 1,
                   reset_strategy: str = "") -> int:
        """
        [FIXED 2026-06-11] next_value 也应尊重 start 参数。

        原 BUG：INSERT OR IGNORE 写入 start-1，但行已存在时被忽略。
        然后 UPDATE current_value+1，从旧值递增（如 0→1），覆盖了 start。
        当 auto_detect_start 返回 2 而 _sequences.current_value = 0 时，
        next_value 返回 1，导致生成重复 code → 400 BAD REQUEST "值已存在"。

        修复：先 UPDATE current_value = MAX(current_value, start-1)，
        再 current_value+1，确保返回值 ≥ start。
        """
        with self._lock:
            try:
                self._data_source.execute(
                    f"INSERT OR IGNORE INTO {_SEQUENCES_TABLE} "
                    f"(sequence_name, current_value) VALUES (?, ?)",
                    (sequence_name, start - 1)
                )
                self._data_source.commit()

                # [FIX 2026-06-11] 确保 current_value 至少为 start-1
                # 这样后续 +1 才能保证返回值 ≥ start
                self._data_source.execute(
                    f"UPDATE {_SEQUENCES_TABLE} SET current_value = ? "
                    f"WHERE sequence_name = ? AND current_value < ?",
                    (start - 1, sequence_name, start - 1)
                )
                self._data_source.commit()

                if self._should_reset(sequence_name, reset_strategy):
                    self._do_reset(sequence_name, start)

                self._data_source.execute(
                    f"UPDATE {_SEQUENCES_TABLE} SET current_value = current_value + 1 "
                    f"WHERE sequence_name = ?",
                    (sequence_name,)
                )
                self._data_source.commit()
                cursor = self._data_source.execute(
                    f"SELECT current_value FROM {_SEQUENCES_TABLE} WHERE sequence_name = ?",
                    (sequence_name,)
                )
                row = cursor.fetchone()
                if row:
                    if isinstance(row, dict):
                        return row["current_value"]
                    return row[0]
                return start
            except Exception as e:
                logger.error(f"[SequenceEngine] next_value failed: {e}")
                raise

    def build_periodic_sequence_name(self, base_name: str,
                                      scope_key: str,
                                      reset_strategy: str) -> str:
        if not reset_strategy or reset_strategy == "never":
            return f"{base_name}:{scope_key}"

        from datetime import datetime
        now = datetime.now()
        if reset_strategy == "daily":
            period = now.strftime("%Y-%m-%d")
        elif reset_strategy == "monthly":
            period = now.strftime("%Y-%m")
        elif reset_strategy == "yearly":
            period = now.strftime("%Y")
        else:
            period = "default"

        return f"{base_name}:{scope_key}:{period}"

    def peek_value(self, sequence_name: str, start: int = 1) -> int:
        """
        [FIXED 2026-06-11] peek 应同时考虑 _sequences 计数和调用方传入的 start。
        原 BUG：auto_detect_start 从表里找到最大序号 N，返回 N+1 作为 start；
        但 peek_value 用 INSERT OR IGNORE 写入 start-1，若行已存在则忽略 start。
        然后 SELECT current_value+1 返回旧值（可能 < start），
        导致 auto_detect 的结果被 _sequences 的旧值覆盖，预览一直显示 01。
        修复：用 MAX(current_value+1, start) 作为返回值。
        """
        with self._lock:
            try:
                self._data_source.execute(
                    f"INSERT OR IGNORE INTO {_SEQUENCES_TABLE} (sequence_name, current_value) VALUES (?, ?)",
                    (sequence_name, start - 1)
                )
                self._data_source.commit()
                cursor = self._data_source.execute(
                    f"SELECT current_value FROM {_SEQUENCES_TABLE} WHERE sequence_name = ?",
                    (sequence_name,)
                )
                row = cursor.fetchone()
                if row:
                    val = row[0] if not isinstance(row, dict) else row.get("current_value", 0)
                    # [FIX 2026-06-11] 同时考虑 _sequences 旧值和 start，取大者
                    return max(val + 1, start)
                return start
            except Exception as e:
                logger.debug(f"[SequenceEngine] peek_value failed: {e}")
                return start

    def auto_detect_start(self, sequence_name: str, table_name: str, code_column: str,
                          scope_condition: str = "", scope_params: tuple = (),
                          prefix_filter: str = "") -> int:
        """
        [FIXED 2026-06-11] 从现有 code 列中提取最大序号

        原 SQL 假设 code 格式有 '_' 分隔符（如 'BO_A_01'），用 INSTR(REVERSE(code), '_') 定位数字起点。
        新格式 '{service_module_code}{SEQ:2}'（无分隔符，如 'PROC_REQ_MNG01'）会找不到 '_'，
        导致 SUBSTR 失败、MAX 返回 NULL、退回 start=1，造成序号重复 BUG。

        修复策略：改用 Python 正则提取所有 code 的尾部数字（trailing digits），取最大值 + 1。
        支持有/无分隔符的格式。

        Args:
            sequence_name: 序列名（仅用于日志）
            table_name: 物理表名（必须已解析，如 'business_objects'）
            code_column: code 列名
            scope_condition: SQL WHERE 子句（不含 WHERE 关键字）
            scope_params: WHERE 参数 tuple
            prefix_filter: [NEW 2026-06-11] 在 Python 层过滤 prefix，避免 SQL 层复杂条件
                           例如 'PROC_REQ_MNG' 只匹配以它开头的 code
        """
        try:
            # 拉取所有 code（数量可控，BO 一般 < 10k）
            sql = f"SELECT {code_column} FROM {table_name}"
            if scope_condition:
                sql += f" WHERE {scope_condition}"
            cursor = self._data_source.execute(sql, scope_params)
            rows = cursor.fetchall()

            import re
            trailing_digits = re.compile(r'(\d+)\s*$')
            max_val = 0
            matched_count = 0
            for row in rows:
                # 兼容 tuple / dict 返回
                if isinstance(row, dict):
                    code = row.get(code_column)
                elif isinstance(row, (tuple, list)):
                    code = row[0]
                else:
                    code = row
                if not code or not isinstance(code, str):
                    continue
                # prefix 过滤（避免不同 service_module 的 BO 互相干扰）
                if prefix_filter and not code.startswith(prefix_filter):
                    continue
                matched_count += 1
                m = trailing_digits.search(code)
                if m:
                    try:
                        v = int(m.group(1))
                        if v > max_val:
                            max_val = v
                    except (ValueError, TypeError):
                        continue

            if max_val > 0:
                logger.debug(
                    f"[SequenceEngine] auto_detect_start: max={max_val} from "
                    f"{matched_count}/{len(rows)} rows in {table_name}.{code_column} "
                    f"(prefix_filter={prefix_filter!r})"
                )
                return max_val + 1
            return 1
        except Exception as e:
            logger.debug(f"[SequenceEngine] auto_detect_start fallback (using 1): {e}")
            return 1

    def reset_sequence(self, sequence_name: str):
        try:
            self._data_source.execute(
                f"UPDATE {_SEQUENCES_TABLE} SET current_value = 0 WHERE sequence_name = ?",
                (sequence_name,)
            )
            self._data_source.commit()
        except Exception as e:
            logger.error(f"[SequenceEngine] reset failed: {e}")


class KeyTemplateParser:

    FIELD_REF_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
    SEQ_PATTERN = re.compile(r'\{SEQ:(\d+)\}')

    def parse(self, pattern: str) -> List[Dict[str, Any]]:
        tokens = []
        pos = 0
        while pos < len(pattern):
            seq_match = self.SEQ_PATTERN.match(pattern, pos)
            if seq_match:
                tokens.append({"type": "sequence", "padding": int(seq_match.group(1))})
                pos = seq_match.end()
                continue

            field_match = self.FIELD_REF_PATTERN.match(pattern, pos)
            if field_match:
                tokens.append({"type": "field", "name": field_match.group(1)})
                pos = field_match.end()
                continue

            char = pattern[pos]
            if char in ('_', '-', '.', '/', ':'):
                tokens.append({"type": "separator", "value": char})
                pos += 1
                continue

            tokens.append({"type": "literal", "value": char})
            pos += 1
        return tokens

    def resolve(self, tokens: List[Dict[str, Any]], field_values: Dict[str, Any],
                sequence_value: int) -> str:
        parts = []
        for token in tokens:
            t = token["type"]
            if t == "field":
                val = field_values.get(token["name"], "")
                if val:
                    parts.append(str(val).upper())
            elif t == "sequence":
                padding = token.get("padding", 0)
                if padding > 0:
                    parts.append(str(sequence_value).zfill(padding))
                else:
                    parts.append(str(sequence_value))
            elif t == "separator":
                parts.append(token["value"])
            elif t == "literal":
                parts.append(token["value"])
        return "".join(parts)

    def resolve_prefix(self, tokens: List[Dict[str, Any]],
                        field_values: Dict[str, Any]) -> str:
        """
        [NEW 2026-06-11] 解析 pattern 中第一个 sequence token 之前的所有 token，
        生成 prefix_filter 用于 auto_detect_start 的范围过滤。

        例如 {service_module_code}{SEQ:2} + {service_module_code: 'PROC_REQ_MNG'}
        → 'PROC_REQ_MNG'
        """
        parts = []
        for token in tokens:
            if token["type"] == "sequence":
                break
            if token["type"] == "field":
                val = field_values.get(token["name"], "")
                if val:
                    parts.append(str(val).upper())
            elif token["type"] == "separator":
                parts.append(token["value"])
            elif token["type"] == "literal":
                parts.append(token["value"])
        return "".join(parts)

    def build_scope_key(self, segments: List[Dict[str, Any]],
                        field_values: Dict[str, Any],
                        default_name: str = "default") -> str:
        scope_fields = []
        for seg in segments:
            if seg.get("type") == "parent_field":
                scope_fields.append(seg.get("source", seg.get("name", "")))
        if not scope_fields:
            return default_name
        values = []
        for f in scope_fields:
            val = field_values.get(f, "")
            if val:
                values.append(str(val).upper())
        scope_part = ":".join(values) if values else default_name
        return scope_part


class KeyTemplateEngine:

    def __init__(self, data_source):
        self._data_source = data_source
        self._sequence_engine = SequenceEngine(data_source)
        self._parser = KeyTemplateParser()

    def _validate_parent_fields(self, segments: List[Dict[str, Any]],
                                 field_values: Dict[str, Any]) -> bool:
        """
        [NEW 2026-06-11] 校验 segments 中所有 parent_field.source 在 field_values 中有非空值。

        返回 False 时，generate_code / preview_code 应返回 None（拒绝生成裸序列号）。
        """
        for seg in segments:
            if seg.get("type") == "parent_field":
                source = seg.get("source", seg.get("name", ""))
                if not field_values.get(source):
                    logger.debug(
                        f"[KeyTemplateEngine] Missing parent_field value: {source}. "
                        f"Skipping code generation."
                    )
                    return False
        return True

    def generate_code(self, config: KeyTemplateConfig, field_values: Dict[str, Any],
                      object_type: str = "",
                      table_name: str = None,
                      prefix_filter: str = "") -> Optional[str]:
        if not config.enabled or not config.pattern:
            return None

        # [FIXED 2026-06-11] 预校验：parent_field 引用的值不能为空
        # 原行为：service_module_code 缺失时 resolve() 跳过该字段，只输出序列号 → "44"
        # 修复：返回 None，API 层返回 "Failed to generate code" 而非裸序列号
        if not self._validate_parent_fields(config.segments, field_values):
            return None

        tokens = self._parser.parse(config.pattern)
        segments = config.segments

        seq_seg = None
        for seg in segments:
            if seg.get("type") == "sequence":
                seq_seg = seg
                break

        seq_config = config.sequence or SequenceConfig.from_segments(segments)

        full_seq_name = self._sequence_engine.build_periodic_sequence_name(
            seq_seg.get("name", f"{config.object_id}_seq") if seq_seg else f"{config.object_id}_seq",
            self._parser.build_scope_key(segments, field_values, "default"),
            seq_config.reset_strategy,
        )

        effective_table = table_name or config.object_id

        # [FIXED 2026-06-11] 重试机制：避免生成已存在的 code
        # 原 BUG：_sequences 表的 current_value 可能因为历史失败插入而虚高（如 auto_detect=5 但 current=7）。
        # 直接 next_value(start=5) 会跳到 8 → 与表中存在的 6,7 不冲突，
        # 但若当前值与表中已有的真实记录不一致（如有人手工修改了表），
        # 仍可能返回已存在的 code → 400 BAD REQUEST "值已存在"。
        # 修复：生成 code 后立刻在 DB 中查询，若已存在则自增重试，最多 10 次。
        for _ in range(10):
            auto_detect = (seq_seg or {}).get("auto_detect", False)
            seq_start = seq_config.start
            if auto_detect and self._data_source:
                try:
                    detected = self._sequence_engine.auto_detect_start(
                        full_seq_name, effective_table, "code",
                        prefix_filter=prefix_filter,
                    )
                    if detected > seq_start:
                        seq_start = detected
                except Exception:
                    pass

            reset_policy = seq_config.reset_strategy
            seq_value = self._sequence_engine.next_value(
                full_seq_name, start=seq_start, reset_strategy=reset_policy
            )

            code = self._parser.resolve(tokens, field_values, seq_value)

            # 检查 code 是否已存在
            if code and self._data_source:
                try:
                    cursor = self._data_source.execute(
                        f"SELECT 1 FROM {effective_table} WHERE code = ? LIMIT 1",
                        (code,)
                    )
                    if not cursor.fetchone():
                        return code
                    # 已存在 → 继续重试，让 next_value 递增
                    logger.debug(
                        f"[KeyTemplateEngine] Generated code '{code}' already exists, retrying"
                    )
                except Exception:
                    # 查询失败时直接返回（避免阻断）
                    return code
            else:
                return code

        logger.warning(
            f"[KeyTemplateEngine] Failed to generate unique code after 10 retries"
        )
        return None

    def preview_code(self, config: KeyTemplateConfig,
                     field_values: Dict[str, Any],
                     table_name: str = None,
                     prefix_filter: str = "") -> Optional[str]:
        if not config.enabled or not config.pattern:
            return None

        # [FIXED 2026-06-11] 同 generate_code：parent_field 值不能为空
        if not self._validate_parent_fields(config.segments, field_values):
            return None

        tokens = self._parser.parse(config.pattern)
        segments = config.segments

        seq_seg = None
        for seg in segments:
            if seg.get("type") == "sequence":
                seq_seg = seg
                break

        seq_config = config.sequence or SequenceConfig.from_segments(segments)

        seq_start = seq_config.start
        if seq_seg:
            seq_name = seq_seg.get("name", f"{config.object_id}_seq")
            scope_vals = self._parser.build_scope_key(segments, field_values, "default")
            scope_key = f"{seq_name}:{scope_vals}"

            # [FIXED 2026-06-11] auto_detect 应同样在 preview 路径生效
            # 原 BUG: preview_code 用 seq_config.start（默认 1）作 peek_value 的 start，
            # 即使 generate_code 通过 auto_detect_start 检测到了最大序号（如 01），
            # preview 仍会显示 01，造成预览与生成不一致。
            # 修复：preview 也调用 auto_detect_start 校正 seq_start。
            auto_detect = (seq_seg or {}).get("auto_detect", False)
            # [FIXED 2026-06-11] 使用调用方传入的物理表名
            effective_table = table_name or config.object_id
            if auto_detect and self._data_source:
                try:
                    detected = self._sequence_engine.auto_detect_start(
                        scope_key, effective_table, "code",
                        prefix_filter=prefix_filter,
                    )
                    if detected > seq_start:
                        seq_start = detected
                except Exception:
                    pass

            seq_value = self._sequence_engine.peek_value(scope_key, start=seq_start)
        else:
            seq_value = 1

        return self._parser.resolve(tokens, field_values, sequence_value=seq_value)

    def get_sequence_engine(self) -> SequenceEngine:
        return self._sequence_engine