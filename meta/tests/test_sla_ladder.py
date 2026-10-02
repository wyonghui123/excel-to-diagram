import pytest

pytestmark = pytest.mark.unit

# 平台内部表（task_slas）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - SLA 梯队与告警（A9）
测试 meta.core.sla_ladder（§7.6 升级梯队 + 幂等去重 + 告警产出）

覆盖目标（对齐 §12.1 A9 / §7.6 / §12.1 Q3）：
  1. 梯级判定：T0 warn_at_pct / T1 alert / T2 due_at（on_breach）/ T3 due+grace 死信
  2. 幂等去重：梯级单调不回退，重复扫描不重复告警（进度记在 SLA 自身）
  3. 告警产出：返回清单供收件箱/IM；apply=False 纯预览不改库
  4. 边界：暂停中不越线、已完成不扫、动作意图取 on_breach
"""

from datetime import datetime, timedelta

from meta.core.sla_ladder import (
    RUNG_ALERT,
    RUNG_BREACH,
    RUNG_DEAD_LETTER,
    RUNG_NAMES,
    RUNG_NONE,
    RUNG_WARN,
    ladder_status,
    resolve_action,
    resolve_rung,
    scan_escalations,
)
from meta.core.task_sla import (
    close_sla,
    ensure_sla_tables,
    get_sla,
    open_sla,
    pause_sla,
)

T0 = datetime(2026, 10, 2, 9, 0, 0)


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "a9.db"))
    with source.transaction():
        ensure_sla_tables(source)
    yield source


def _sla(ds, task_id="T-1", *, target=3600, warn=80, alert=100, grace=0,
         on_breach=None, start=T0):
    return open_sla(ds, task_id=task_id, target_seconds=target, warn_at_pct=warn,
                    alert_at_pct=alert, grace_seconds=grace, on_breach=on_breach,
                    start_at=start)


# ─────────────────────────────────────────────────────────────────────────────
# 判定（纯函数）
# ─────────────────────────────────────────────────────────────────────────────

class TestRungs:
    """TC-A9-001~003 梯级与动作"""

    def test_TC_A9_001_梯级判定(self):
        assert resolve_rung({"is_warn": False}) == RUNG_NONE
        assert resolve_rung({"is_warn": True}) == RUNG_WARN
        assert resolve_rung({"is_warn": True, "is_alert": True}) == RUNG_ALERT
        assert resolve_rung({"is_alert": True, "is_breached": True}) == RUNG_BREACH
        assert resolve_rung({"is_breached": True, "is_dead_letter": True}) == RUNG_DEAD_LETTER

    def test_TC_A9_002_动作意图(self):
        assert resolve_action(RUNG_WARN, None) == "notify"
        assert resolve_action(RUNG_ALERT, None) == "notify"
        assert resolve_action(RUNG_BREACH, "reassign") == "reassign"
        assert resolve_action(RUNG_BREACH, {"action": "escalate_fallback"}) == "escalate_fallback"
        assert resolve_action(RUNG_BREACH, "不存在的动作") == "notify"   # 兜底
        assert resolve_action(RUNG_DEAD_LETTER, "reassign") == "dead_letter"  # T3 强制死信

    def test_TC_A9_003_梯级命名(self):
        assert RUNG_NAMES[RUNG_WARN] == "warn"
        assert RUNG_NAMES[RUNG_BREACH] == "breach"
        assert RUNG_NAMES[RUNG_DEAD_LETTER] == "dead_letter"


# ─────────────────────────────────────────────────────────────────────────────
# 扫描与幂等去重
# ─────────────────────────────────────────────────────────────────────────────

class TestScan:
    """TC-A9-010~017 scan_escalations"""

    def test_TC_A9_010_预警梯级与幂等(self, ds):
        _sla(ds)

        first = scan_escalations(ds, now=_at(49))       # ≈81.7% → warn
        second = scan_escalations(ds, now=_at(50))      # 同梯级 → 不重复

        assert [f["rung"] for f in first] == [RUNG_WARN]
        assert first[0]["rung_name"] == "warn"
        assert first[0]["action"] == "notify"
        assert second == []
        assert get_sla(ds, first[0]["sla_id"])["last_escalation_rung"] == RUNG_WARN

    def test_TC_A9_011_跨级只报最高(self, ds):
        _sla(ds)

        findings = scan_escalations(ds, now=_at(61))    # 直接越线，跳过 warn/alert

        assert [f["rung"] for f in findings] == [RUNG_BREACH]
        assert scan_escalations(ds, now=_at(62)) == []  # 已发 → 不重复

    def test_TC_A9_012_越线写客观事实(self, ds):
        sla = _sla(ds)

        scan_escalations(ds, now=_at(61))
        row = get_sla(ds, sla["id"])

        assert row["has_breached"] == 1
        assert row["breach_at"] is not None
        assert row["last_escalation_at"] is not None

    def test_TC_A9_013_死信强制动作(self, ds):
        _sla(ds, grace=600, on_breach="reassign")

        findings = scan_escalations(ds, now=_at(71))

        assert [f["rung"] for f in findings] == [RUNG_DEAD_LETTER]
        assert findings[0]["action"] == "dead_letter"

    def test_TC_A9_014_预览不改库(self, ds):
        sla = _sla(ds)

        first = scan_escalations(ds, now=_at(61), apply=False)
        second = scan_escalations(ds, now=_at(61), apply=False)

        assert [f["rung"] for f in first] == [RUNG_BREACH]
        assert first == second                                   # 预览可重复
        assert get_sla(ds, sla["id"])["last_escalation_rung"] == 0

    def test_TC_A9_015_暂停中不越线(self, ds):
        sla = _sla(ds)
        pause_sla(ds, sla["id"], at=_at(10))

        findings = scan_escalations(ds, now=_at(120))   # 业务时间仅 10min

        assert findings == []
        assert get_sla(ds, sla["id"])["has_breached"] == 0

    def test_TC_A9_016_已完成不扫(self, ds):
        sla = _sla(ds)
        close_sla(ds, sla["id"], achieved=True, at=_at(10))

        assert scan_escalations(ds, now=_at(999)) == []
        assert get_sla(ds, sla["id"])["last_escalation_rung"] == 0

    def test_TC_A9_017_警戒线梯级(self, ds):
        _sla(ds, alert=90, on_breach="notify")

        findings = scan_escalations(ds, now=_at(55))    # ≈91.7% → alert（未越线）

        assert [f["rung"] for f in findings] == [RUNG_ALERT]
        assert findings[0]["pct_used"] >= 90


# ─────────────────────────────────────────────────────────────────────────────
# 只读聚合
# ─────────────────────────────────────────────────────────────────────────────

class TestStatus:
    """TC-A9-020 仪表盘聚合（只读）"""

    def test_TC_A9_020_梯级状态聚合(self, ds):
        a = _sla(ds, task_id="T-1")
        b = _sla(ds, task_id="T-2", target=60)

        status = {s["task_id"]: s for s in ladder_status(ds, now=_at(61))}

        assert status["T-1"]["rung_name"] == "breach"
        assert status["T-2"]["rung_name"] == "breach"      # grace=0 → 不设死信梯队
        assert status["T-2"]["rung"] == RUNG_BREACH        # grace=0 → 同刻越线不折叠为死信
        # 只读：未推进任何升级进度
        assert get_sla(ds, a["id"])["last_escalation_rung"] == 0
        assert get_sla(ds, b["id"])["last_escalation_rung"] == 0