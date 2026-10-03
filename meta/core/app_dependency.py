# -*- coding: utf-8 -*-
"""[多产品平台 S6 / G5] 应用依赖校验（安装期 + 启用期）

契约（roadmap §五 S6）:

    应用包声明其依赖的 BO / 规则 / 列版本，安装前校验、缺失拒绝启用
    （行业先例：Dataverse 解决方案导入缺失依赖校验）

声明面（`app.yaml` 可选段 `requires:`，未声明 = 旧行为，零影响）:

    requires:
      bo: [outbound_order]            # 依赖的 BO id
      rules: [wh-outbound-to-wb-v1]   # 依赖的 doc_flow 规则 id
      column_version: "xxxx"          # 预留：hash 机制未落地，本版仅登记

校验项:
    ① 平台版本区间（platform.min_version / max_version，支持 "<1.0.0" 形态）
    ② requires.bo —— 依赖 BO 存在
    ③ requires.rules —— 依赖 doc_flow 规则存在
    ④ 本应用 doc_flow 规则引用的 source_bo / target_bo 存在

边界（如实声明，不扩范围）:
    - **纯函数**：不碰 DB / Flask → 可独立单测；可用集合由调用方给定
    - 只做「声明 → 校验 → 拒绝」，**不做** 应用 migrations 执行（另一独立大项）
    - column_version 仅登记不校验（schema hash 机制未落地）
    - 「规则是否存在」按调用方给定的可用集合判定，不主动查平台规则表

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §五 S6
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

#: 平台版本默认值（env PLATFORM_VERSION 可覆盖，供发布 / 测试注入）。
#: 现有 app.yaml 声明 min 0.9.0 / max <1.0.0 → 取 0.9.x 不破坏既有应用。
_DEFAULT_PLATFORM_VERSION = "0.9.5"
_ENV_PLATFORM_VERSION = "PLATFORM_VERSION"

#: 约束式：可选的比较操作符 + 点分数字版本（如 "0.9.0" / "<1.0.0"）
_VERSION_RE = re.compile(r"^\s*(<=|>=|<|>|==|=)?\s*(\d+(?:\.\d+)*)\s*$")


class DependencyError(RuntimeError):
    """依赖校验失败（安装 / 启用被拒）。"""

    def __init__(self, app_id: str, findings: Sequence["DependencyFinding"]):
        self.app_id = app_id
        self.findings = list(findings)
        detail = "; ".join(f"[{f.code}] {f.detail}" for f in self.findings)
        super().__init__(f"应用 '{app_id}' 依赖校验失败: {detail}")


@dataclass
class DependencyFinding:
    code: str
    severity: str          # "error"（本版只有 error；预留 warn）
    detail: str


def get_platform_version() -> str:
    """当前平台版本（env PLATFORM_VERSION 优先）。"""
    raw = (os.environ.get(_ENV_PLATFORM_VERSION) or "").strip()
    return raw or _DEFAULT_PLATFORM_VERSION


def _parse_version(text: str) -> Optional[Tuple[int, ...]]:
    """'0.9.1' → (0, 9, 1)；非法 → None。"""
    m = _VERSION_RE.match(text or "")
    if not m:
        return None
    return tuple(int(x) for x in m.group(2).split("."))


def _cmp(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    """点分元组比较（自动右侧补零，'1.0' == '1.0.0'）。"""
    n = max(len(a), len(b))
    pa = a + (0,) * (n - len(a))
    pb = b + (0,) * (n - len(b))
    return (pa > pb) - (pa < pb)


def _satisfies(current: Optional[Tuple[int, ...]], raw: str) -> Optional[bool]:
    """判定 current 是否满足约束式 raw；无法解析返回 None。"""
    m = _VERSION_RE.match(raw or "")
    if m is None or current is None:
        return None
    op = m.group(1) or ">="          # 无操作符按 min 语义（">="）解读
    ver = tuple(int(x) for x in m.group(2).split("."))
    c = _cmp(current, ver)
    return {
        ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0,
        "==": c == 0, "=": c == 0,
    }[op]


def _own_declared_bo_ids(manifest) -> List[str]:
    """应用自带 schema 的 BO id（读文件；失败降级为空，不阻断校验）。"""
    try:
        from meta.core.app_package import read_bo_ids
        return read_bo_ids(manifest)
    except Exception as e:  # noqa: BLE001 - 读不到自带 BO 不该误判为"依赖缺失"
        logger.debug("[AppDependency] 读取应用自带 BO 失败（降级）: %s", e)
        return []


def _check_platform_constraint(manifest, current_raw: str,
                               findings: List[DependencyFinding]) -> None:
    """校验 platform.min_version / max_version（现在完全没校验，S6 的一半）。"""
    cur = _parse_version(current_raw)
    if cur is None:
        logger.debug(
            "[AppDependency] 平台版本 %r 无法解析 → 跳过版本校验", current_raw)
        return
    for raw, label in (
        (getattr(manifest, "platform_min_version", ""), "min_version"),
        (getattr(manifest, "platform_max_version", ""), "max_version"),
    ):
        if not raw:
            continue
        ok = _satisfies(cur, raw)
        if ok is None:
            findings.append(DependencyFinding(
                "PLATFORM_CONSTRAINT_INVALID", "error",
                f"platform.{label} 无法解析: {raw!r}"))
        elif not ok:
            findings.append(DependencyFinding(
                "PLATFORM_VERSION_OUT_OF_RANGE", "error",
                f"平台版本 {current_raw} 不满足 platform.{label} = {raw!r}"))


def validate_dependencies(
    manifest,
    *,
    available_bo_ids: Optional[Set[str]] = None,
    available_rule_ids: Optional[Set[str]] = None,
    platform_version: Optional[str] = None,
    own_bo_ids: Optional[Sequence[str]] = None,
) -> List[DependencyFinding]:
    """校验单个应用的依赖声明；返回 findings（空 = 通过）。

    Args:
        manifest: AppManifest
        available_bo_ids: 环境中可用的 BO id 集合（他应用 / 平台）
        available_rule_ids: 环境中可用的 doc_flow 规则 id 集合
        platform_version: 平台版本；None 时取 get_platform_version()
        own_bo_ids: 应用自带 BO id；None 时读 manifest 的 schema 文件

    Returns:
        List[DependencyFinding]（纯函数，不改任何状态）
    """
    findings: List[DependencyFinding] = []
    current_raw = platform_version or get_platform_version()
    _check_platform_constraint(manifest, current_raw, findings)

    bos: Set[str] = set(available_bo_ids or ())
    if own_bo_ids is not None:
        bos.update(own_bo_ids)
    else:
        bos.update(_own_declared_bo_ids(manifest))
    rules: Set[str] = set(available_rule_ids or ())

    requires = getattr(manifest, "requires", None)
    for bo_id in (getattr(requires, "bo", None) or []):
        if bo_id not in bos:
            findings.append(DependencyFinding(
                "BO_DEPENDENCY_MISSING", "error",
                f"依赖的 BO '{bo_id}' 不存在（未启用或未声明该 schema）"))
    for rule_id in (getattr(requires, "rules", None) or []):
        if rule_id not in rules:
            findings.append(DependencyFinding(
                "RULE_DEPENDENCY_MISSING", "error",
                f"依赖的 doc_flow 规则 '{rule_id}' 不存在"))

    # 本应用规则引用的 BO 必须存在（防静默通过、运行期才炸）
    for rule in (getattr(manifest, "doc_flow_rules", None) or []):
        for bo_id, role in ((rule.source_bo, "source_bo"),
                            (rule.target_bo, "target_bo")):
            if bo_id and bo_id not in bos:
                findings.append(DependencyFinding(
                    "RULE_BO_MISSING", "error",
                    f"规则 '{rule.rule_id}' 的 {role}='{bo_id}' 不存在"))
    return findings


def collect_declared_ids(manifests) -> Tuple[Set[str], Set[str]]:
    """汇总一组 manifest 声明的 (BO id 集合, 规则 id 集合)。"""
    bos: Set[str] = set()
    rules: Set[str] = set()
    for m in manifests:
        bos.update(_own_declared_bo_ids(m))
        for r in (getattr(m, "doc_flow_rules", None) or []):
            rules.add(r.rule_id)
    return bos, rules


def validate_app_set(
    manifests,
    *,
    platform_bo_ids: Optional[Set[str]] = None,
    platform_version: Optional[str] = None,
) -> Dict[str, List[DependencyFinding]]:
    """校验一组 manifest；返回 {app_id: findings}（空 dict = 全通过）。

    可用集合 = 全部 manifest 声明并集 ∪ platform_bo_ids —— 因此应用引用
    自有 BO 不会被误判，跨应用引用则必须在同一启用集合内。
    """
    bos, rules = collect_declared_ids(manifests)
    bos |= set(platform_bo_ids or ())
    problems: Dict[str, List[DependencyFinding]] = {}
    for m in manifests:
        findings = validate_dependencies(
            m, available_bo_ids=bos, available_rule_ids=rules,
            platform_version=platform_version)
        if findings:
            problems[m.app_id] = findings
    return problems


def assert_app_set(
    manifests,
    *,
    platform_bo_ids: Optional[Set[str]] = None,
    platform_version: Optional[str] = None,
) -> int:
    """校验并在失败时 raise DependencyError（安装 / 启用共用入口）。

    Returns:
        通过校验的 manifest 数
    """
    problems = validate_app_set(
        manifests, platform_bo_ids=platform_bo_ids,
        platform_version=platform_version)
    if problems:
        app_id, findings = next(iter(problems.items()))
        raise DependencyError(app_id, findings)
    return len(manifests)
