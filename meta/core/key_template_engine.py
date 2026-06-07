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
    auto_suggest: bool = True
    pattern: str = ""
    separator: str = "_"
    segments: List[Dict[str, Any]] = field(default_factory=list)
    preview: str = ""
    scope: Optional[str] = None
    sequence: Optional[SequenceConfig] = None

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

        return cls(
            object_id=object_id,
            enabled=data.get("enabled", False),
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
        with self._lock:
            try:
                self._data_source.execute(
                    f"INSERT OR IGNORE INTO {_SEQUENCES_TABLE} "
                    f"(sequence_name, current_value) VALUES (?, ?)",
                    (sequence_name, start - 1)
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
                    return val + 1
                return start
            except Exception as e:
                logger.debug(f"[SequenceEngine] peek_value failed: {e}")
                return start

    def auto_detect_start(self, sequence_name: str, table_name: str, code_column: str,
                          scope_condition: str = "", scope_params: tuple = ()) -> int:
        try:
            sql = f"SELECT MAX(CAST(SUBSTR({code_column}, LENGTH({code_column}) - INSTR(REVERSE({code_column}), '_') + 2) AS INTEGER)) FROM {table_name}"
            if scope_condition:
                sql += f" WHERE {scope_condition}"
            cursor = self._data_source.execute(sql, scope_params)
            row = cursor.fetchone()
            max_val = None
            if row:
                val = row[0] if not isinstance(row, dict) else list(row.values())[0]
                max_val = val
            if max_val is not None and max_val > 0:
                return int(max_val) + 1
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

    def generate_code(self, config: KeyTemplateConfig, field_values: Dict[str, Any],
                      object_type: str = "") -> Optional[str]:
        if not config.enabled or not config.pattern:
            return None

        tokens = self._parser.parse(config.pattern)
        segments = config.segments

        seq_seg = None
        for seg in segments:
            if seg.get("type") == "sequence":
                seq_seg = seg
                break

        seq_config = config.sequence or SequenceConfig.from_segments(segments)

        scope_key = config.object_id
        if seq_seg:
            seq_name = seq_seg.get("name", f"{config.object_id}_seq")
            scope_vals = self._parser.build_scope_key(segments, field_values, "default")
            scope_key = f"{seq_name}:{scope_vals}"

        full_seq_name = self._sequence_engine.build_periodic_sequence_name(
            seq_seg.get("name", f"{config.object_id}_seq") if seq_seg else f"{config.object_id}_seq",
            self._parser.build_scope_key(segments, field_values, "default"),
            seq_config.reset_strategy,
        )

        auto_detect = (seq_seg or {}).get("auto_detect", False)
        seq_start = seq_config.start
        table_name = config.object_id

        if auto_detect and self._data_source:
            try:
                detected = self._sequence_engine.auto_detect_start(
                    full_seq_name, table_name, "code"
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

        return code

    def preview_code(self, config: KeyTemplateConfig,
                     field_values: Dict[str, Any]) -> Optional[str]:
        if not config.enabled or not config.pattern:
            return None

        tokens = self._parser.parse(config.pattern)
        segments = config.segments

        seq_seg = None
        for seg in segments:
            if seg.get("type") == "sequence":
                seq_seg = seg
                break

        seq_config = config.sequence or SequenceConfig.from_segments(segments)

        if seq_seg:
            seq_name = seq_seg.get("name", f"{config.object_id}_seq")
            scope_vals = self._parser.build_scope_key(segments, field_values, "default")
            scope_key = f"{seq_name}:{scope_vals}"
            seq_start = seq_config.start
            seq_value = self._sequence_engine.peek_value(scope_key, start=seq_start)
        else:
            seq_value = 1

        return self._parser.resolve(tokens, field_values, sequence_value=seq_value)

    def get_sequence_engine(self) -> SequenceEngine:
        return self._sequence_engine