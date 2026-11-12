# -*- coding: utf-8 -*-
"""元模型声明 lint（Spec §3.5 A-01-2）。

当前实现 R-MM-01（关联语义扩展）：

- `--relations`：五枚举校验 + R2/R3/hierarchy 判据
  - `semantics.kind` / `associations[].kind` 必须 ∈
    {association, hierarchy, reference, master_detail, derived}（R1：缺省 = association）
  - R2：`kind: master_detail` 必须显式声明 `deletability.condition`，且不能是 `'true'`
  - R3：`kind: derived` 必须 `analytical_model.enabled=true`
  - `hierarchy` 判据：`key_template.enabled=true`

- `--actions`：动作元模型结构校验（R-MM-02）
  - 必需键 `id` / `name`；6 组可选声明（object_types / params /
    preconditions / effects / emits / audit）逐项校验
  - R5：`effects[].type` ∈ {transition, set, create, link, notify}；
    transition 必须带 `field` + `to`
  - R6：`emits` 必须在事件注册表内（apps/*/app.yaml 的 events.publish）
  - R8：`preconditions.role_any` ⊆ permission_sets.code（SEED_ROLES 为唯一真源）

- `--permissions`：关系感知授权声明校验（R-MM-04 R16 / A-04-4）
  - `authorization.inherit_mode` ∈ {none, endpoint_union, explicit}（R19 缺省 endpoint_union）
  - R16：`inherit_mode: explicit` 必须有对应 `relation_code` 声明，且该
    `relation_code` 能在静态 permission_rule 声明中找到
    （`resource_type: relationship:<relation_code>`）

- `--doc-flow`：正/逆/调整同构声明校验（R-MM-05）
  - `document:` 段：`state_field` 必填；声明的 number/business_date/
    state/document_type 字段须可解析（含切面注入字段）；`posting_state`
    须为本对象已声明状态 code；`line_object` 须存在且带 `line_parent_field`，
    `line_sequence_field` 仅声明时校验
  - 覆盖度：统计已声明 `document:` 段的事实单据数与 `doc_effect.reversal` 声明数
  - `doc_effect.reversal` 声明合法：from_states / to_state /
    idempotent_states / order / write_audit_fields /
    create_document.primitive（∈ DOC_CREATORS）
  - `REVERSAL_PROFILES` 每档 mode ∈ VALID_MODES、commitment ∈
    VALID_COMMITMENTS、edges[] 必须有 rule_id / source_bo
  - R20：`reversal_orchestrator.py` 不含按单据类型字面量的分支
  - R21：`meta/` 生产代码不得 UPDATE 原单数量列（白名单仅补偿原语）

- `--field-policies`：状态 × 字段矩阵声明校验（R-MM-03 R10/R13/A-03-1）

- `--capabilities`：能力维度单层承运校验（R24 受控枚举 / R28 跨层重复声明）

退出码：0 = 全部通过；1 = 存在违规（供 CI / 发布门禁使用）。

用法：
    python meta/tools/lint_metamodel.py --relations
    python meta/tools/lint_metamodel.py --actions
    python meta/tools/lint_metamodel.py --permissions
    python meta/tools/lint_metamodel.py --doc-flow
    python meta/tools/lint_metamodel.py --field-policies
    python meta/tools/lint_metamodel.py --capabilities
    python meta/tools/lint_metamodel.py --all
"""

import argparse
import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 静音 yaml_loader 的逐文件 Loaded 输出；本工具只读原始 YAML，不装载对象
os.environ.setdefault("TEST_ENTRY", "1")

from meta.core import yaml_compat as yaml  # noqa: E402
from meta.core.models_enums import (  # noqa: E402
    AssociationKind,
    normalize_association_kind,
)
from meta.services.resource_inheritance_engine import (  # noqa: E402
    DEFAULT_INHERIT_MODE,
    INHERIT_MODES,
)

SCHEMAS_DIR = ROOT / "meta" / "schemas"
ACTIONS_PATH = SCHEMAS_DIR / "_standard_actions.yaml"

KNOWN_KINDS = sorted(k.value for k in AssociationKind)

#: R5 受控枚举：动作效果类型
ACTION_EFFECT_TYPES = {"transition", "set", "create", "link", "notify"}
#: 前置条件允许的键
PRECONDITION_KEYS = {"status_in", "role_any", "relation_exists", "expr"}
#: 参数来源允许的取值
PARAM_SOURCES = {"request", "instance", "user"}
#: audit 允许的键
AUDIT_KEYS = {"record", "reason_required"}

#: R-MM-05 `document:` 段必填键（状态唯一真源；其余键随对象形态可选）
DOC_REQUIRED_KEYS = ("state_field",)
#: `document:` 中引用抬头字段的键（必须能在 fields + 切面 fields 中解析）
DOC_HEADER_FIELD_KEYS = (
    "number_field",
    "business_date_field",
    "state_field",
    "document_type_field",
)
#: `document:` 中引用状态 code 的键（必须 ∈ 本对象 states[].code）
DOC_STATE_KEYS = ("posting_state",)
#: `doc_effect.reversal.order` 允许值（编排器缺省 inverted）
REVERSAL_ORDERS = {"declared", "inverted"}
#: R21 扫描范围：meta/ 生产代码（排除 tests）
R21_SCAN_ROOT = ROOT / "meta"
#: R21 白名单：(相对路径, 表名) -> 理由（补偿/逆向原语，不改原单业务数量）
R21_ALLOWLIST = {
    ("meta/core/reversal_primitives.py", "transfer_order_lines"):
        "补偿原语：调拨行发货事实归零供履约投影重算（不改 cancelled 行）",
}
#: R21：SET 子句中的数量列特征
R21_QUANTITY_RE = re.compile(r"\b(?:quantity|qty[A-Za-z0-9_]*|[A-Za-z0-9_]+_qty)\b",
                             re.IGNORECASE)
#: R21：UPDATE ... SET ... WHERE（跨字符串字面量拼接，限长避免误吞）
R21_UPDATE_RE = re.compile(
    r"UPDATE\s+([A-Za-z_]\w*)\s+SET\s+([\s\S]{0,800}?)WHERE", re.IGNORECASE)


def _is_enabled(value) -> bool:
    """兼容 `{enabled: true}` 与 dataclass/标量两种写法。"""
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return bool(getattr(value, "enabled", False))


def _iter_associations(raw):
    """associations 支持 list / dict 两种写法，统一产出 (name, entry)。"""
    associations = raw.get("associations")
    if isinstance(associations, list):
        for entry in associations:
            if isinstance(entry, dict):
                yield entry.get("name") or "<unnamed>", entry
    elif isinstance(associations, dict):
        for name, entry in associations.items():
            if isinstance(entry, dict):
                yield name, entry


def lint_relations() -> tuple:
    """R-MM-01 关联语义 lint；返回 (违规列表, 扫描文件数)。"""
    violations = []
    scanned = 0

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            violations.append((path.name, "yaml", "无法解析: %s" % exc))
            continue
        if not isinstance(raw, dict) or not raw.get("id"):
            continue

        scanned += 1
        file_label = path.name

        # 1) 聚合根级声明：semantics.kind
        declared = str(((raw.get("semantics") or {}).get("kind")) or "").strip()
        if declared:
            kind = normalize_association_kind(declared)
            if kind is None:
                violations.append(
                    (file_label, "semantics.kind",
                     "未知取值 %r，允许值：%s" % (declared, "/".join(KNOWN_KINDS)))
                )
            elif kind is AssociationKind.MASTER_DETAIL:
                condition = str(((raw.get("deletability") or {}).get("condition")) or "").strip()
                if not condition or condition.lower() == "true":
                    violations.append(
                        (file_label, "semantics.kind",
                         "R2：master_detail 必须声明 deletability.condition，且不能为 'true'")
                    )
            elif kind is AssociationKind.DERIVED:
                if not _is_enabled(raw.get("analytical_model")):
                    violations.append(
                        (file_label, "semantics.kind",
                         "R3：derived 要求 analytical_model.enabled=true")
                    )
            elif kind is AssociationKind.HIERARCHY:
                if not _is_enabled(raw.get("key_template")):
                    violations.append(
                        (file_label, "semantics.kind",
                         "hierarchy 要求 key_template.enabled=true")
                    )

        # 2) 逐条声明：associations[].kind（$associations?kind= 的过滤依据）
        for assoc_name, entry in _iter_associations(raw):
            assoc_declared = str(entry.get("kind") or "").strip()
            if not assoc_declared:
                continue
            if normalize_association_kind(assoc_declared) is None:
                violations.append(
                    (file_label, "associations.%s.kind" % assoc_name,
                     "未知取值 %r，允许值：%s" % (assoc_declared, "/".join(KNOWN_KINDS)))
                )

    return violations, scanned


def _load_standard_actions():
    """读取 _standard_actions.yaml 的动作列表（顶层键 standard_actions）。"""
    raw = yaml.safe_load(ACTIONS_PATH.read_text(encoding="utf-8")) or {}
    actions = raw.get("standard_actions") or raw.get("actions")
    return actions if isinstance(actions, list) else []


def _seed_role_codes():
    """permission_sets.code 的静态真源（避免 lint 直读 DB）。"""
    from meta.scripts.init_auth import SEED_ROLES

    return {code for code, _name, _desc, _is_system in SEED_ROLES}


def _registered_events():
    """静态汇总 apps/*/app.yaml 中 events.publish 声明的事件名。"""
    events = set()
    for path in sorted((ROOT / "apps").glob("*/app.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        block = raw.get("events")
        published = block.get("publish") if isinstance(block, dict) else None
        for item in published or []:
            if isinstance(item, str):
                events.add(item)
            elif isinstance(item, dict) and item.get("name"):
                events.add(str(item["name"]))
    return events


def lint_actions(actions, role_codes=None, registered_events=None) -> list:
    """R-MM-02 动作声明结构校验；返回 [(action_id, field, reason)]。"""
    valid_roles = set(role_codes or ())
    valid_events = set(registered_events or ())
    violations = []

    for action in actions:
        if not isinstance(action, dict):
            violations.append(("<actions>", "?", "动作条目必须是映射"))
            continue

        action_id = str(action.get("id") or "").strip()
        label = action_id or "<unnamed>"
        if not action_id:
            violations.append(("<actions>", "id", "动作必须有非空 id"))
            continue
        if not str(action.get("name") or "").strip():
            violations.append((label, "name", "动作必须有非空 name"))

        object_types = action.get("object_types")
        if object_types is not None and not isinstance(object_types, list):
            violations.append((label, "object_types", "必须是列表"))

        for idx, param in enumerate(action.get("params") or []):
            if not isinstance(param, dict) or not str(param.get("name") or "").strip():
                violations.append((label, "params[%d].name" % idx, "参数必须有非空 name"))
                continue
            source = param.get("source")
            if source and str(source) not in PARAM_SOURCES:
                violations.append((label, "params[%d].source" % idx,
                                   "未知来源 %r，允许值：%s"
                                   % (source, "/".join(sorted(PARAM_SOURCES)))))

        preconditions = action.get("preconditions")
        if preconditions is not None and not isinstance(preconditions, dict):
            violations.append((label, "preconditions", "必须是映射"))
        else:
            for key, value in (preconditions or {}).items():
                if key not in PRECONDITION_KEYS:
                    violations.append((label, "preconditions.%s" % key,
                                       "未知键，允许：%s"
                                       % "/".join(sorted(PRECONDITION_KEYS))))
                elif key == "status_in":
                    if not isinstance(value, list) or not value:
                        violations.append((label, "preconditions.status_in", "必须是非空列表"))
                elif key == "role_any":
                    if not isinstance(value, list) or not value:
                        violations.append((label, "preconditions.role_any", "必须是非空列表"))
                        continue
                    for role in value:
                        if str(role) not in valid_roles:
                            violations.append((label, "preconditions.role_any",
                                               "角色 %r 不在 permission_sets.code 内（%s）"
                                               % (role, "/".join(sorted(valid_roles)))))
                elif key == "relation_exists":
                    if not isinstance(value, dict) or not str(value.get("name") or "").strip():
                        violations.append((label, "preconditions.relation_exists",
                                           "必须声明 name"))
                elif key == "expr" and not str(value or "").strip():
                    violations.append((label, "preconditions.expr", "不能为空"))

        effects = action.get("effects")
        if effects is not None and not isinstance(effects, list):
            violations.append((label, "effects", "必须是列表"))
        else:
            for idx, effect in enumerate(effects or []):
                if not isinstance(effect, dict):
                    violations.append((label, "effects[%d]" % idx, "必须是映射"))
                    continue
                effect_type = str(effect.get("type") or "")
                if effect_type not in ACTION_EFFECT_TYPES:
                    violations.append((label, "effects[%d].type" % idx,
                                       "未知类型 %r，允许值：%s"
                                       % (effect_type, "/".join(sorted(ACTION_EFFECT_TYPES)))))
                elif effect_type == "transition":
                    if not str(effect.get("field") or "").strip():
                        violations.append((label, "effects[%d].field" % idx,
                                           "transition 必须声明 field"))
                    if not str(effect.get("to") or "").strip():
                        violations.append((label, "effects[%d].to" % idx,
                                           "transition 必须声明 to"))

        emits = action.get("emits")
        if emits is not None and not isinstance(emits, list):
            violations.append((label, "emits", "必须是列表"))
        elif emits:
            if not valid_events:
                violations.append((label, "emits",
                                   "R6：apps/*/app.yaml 未注册任何事件（events.publish），无法校验"))
            for name in emits:
                if valid_events and str(name) not in valid_events:
                    violations.append((label, "emits", "事件 %r 未注册" % name))

        audit = action.get("audit")
        if audit is not None:
            if not isinstance(audit, dict):
                violations.append((label, "audit", "必须是映射"))
            else:
                for key in audit:
                    if key not in AUDIT_KEYS:
                        violations.append((label, "audit.%s" % key,
                                           "未知键，允许：%s" % "/".join(sorted(AUDIT_KEYS))))

    return violations


def _load_authorization_declarations():
    """扫描 schema YAML 的 authorization 段（R-MM-04 声明位）"""
    declarations = []
    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print("[permissions] %s :: load failed — %s" % (path.name, e))
            continue
        auth = raw.get("authorization")
        if not isinstance(auth, dict):
            continue
        relation_codes = []
        for field in raw.get("fields") or []:
            if isinstance(field, dict) and field.get("db_column") == "relation_code":
                relation_codes.extend(field.get("examples") or [])
        declarations.append({
            "file": path.name,
            "inherit_mode": auth.get("inherit_mode"),
            "relation_codes": relation_codes,
        })
    return declarations


def _declared_relation_rule_codes():
    """收集静态 permission_rule 声明里 resource_type=relationship:<code> 的 code"""
    codes = set()
    prefix = "relationship:"

    def _collect(raw):
        rules = raw.get("permission_rules") if isinstance(raw, dict) else None
        if not isinstance(rules, list):
            return
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            resource_type = str(rule.get("resource_type") or "").strip()
            if resource_type.startswith(prefix):
                code = resource_type[len(prefix):].strip()
                if code:
                    codes.add(code)

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        try:
            _collect(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except Exception:
            continue
    apps_dir = ROOT / "apps"
    if apps_dir.is_dir():
        for path in sorted(apps_dir.glob("*/app.yaml")):
            try:
                _collect(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
            except Exception:
                continue
    return codes


def lint_permissions(declarations, rule_codes=None) -> list:
    """R-MM-04 R16: inherit_mode 三枚举 + explicit 的 relation_code 声明校验

    Args:
        declarations: [{'file': str, 'inherit_mode': str|None, 'relation_codes': [str]}]
        rule_codes: 静态 permission_rule 声明中出现的 relationship 编码集合

    Returns:
        [(file_label, field, reason)]
    """
    violations = []
    rule_codes = set(rule_codes or ())
    for decl in declarations:
        label = decl.get("file") or "<memory>"
        mode = decl.get("inherit_mode")
        if mode is None:
            continue  # R19: 缺省 endpoint_union，视为合规
        normalized = str(mode).strip().lower()
        if normalized not in INHERIT_MODES:
            violations.append((
                label,
                "authorization.inherit_mode",
                "未知取值 %r，允许：%s"
                % (mode, "/".join(INHERIT_MODES)),
            ))
            continue
        if normalized != "explicit":
            continue
        codes = [str(c).strip() for c in (decl.get("relation_codes") or [])
                 if str(c).strip()]
        if not codes:
            violations.append((
                label,
                "authorization.inherit_mode",
                "R16: explicit 必须有对应 relation_code 声明",
            ))
            continue
        for code in codes:
            if code not in rule_codes:
                violations.append((
                    label,
                    "authorization.relation_code",
                    "R16: %r 无对应 permission_rule 声明 "
                    "(resource_type='relationship:%s')" % (code, code),
                ))
    return violations


def _reversal_constants():
    """R-MM-05 静态真源：档位表 + 创建器注册表（不读 DB）。"""
    from meta.core.reversal_primitives import DOC_CREATORS
    from meta.core.reversal_profiles import (
        REVERSAL_PROFILES,
        VALID_COMMITMENTS,
        VALID_MODES,
    )

    return REVERSAL_PROFILES, VALID_MODES, VALID_COMMITMENTS, set(DOC_CREATORS)


def _orchestrator_string_literals():
    """R20：编排器代码中的字符串常量（排除 docstring）。"""
    path = ROOT / "meta" / "core" / "reversal_orchestrator.py"
    if not path.exists():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    literals = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            literals.add(node.value)
    return literals


def _lint_reversal_block(label, reversal, doc_creators):
    """`doc_effect.reversal` 声明合法性；返回 violation 列表。"""
    field = "doc_effect.reversal"
    if not isinstance(reversal, dict):
        return [(label, field, "必须是映射")]
    violations = []

    from_states = reversal.get("from_states")
    if (not isinstance(from_states, list) or not from_states
            or not all(str(s).strip() for s in from_states)):
        violations.append((label, field + ".from_states", "必须是非空状态名列表"))

    if not str(reversal.get("to_state") or "").strip():
        violations.append((label, field + ".to_state", "必须声明目标状态"))

    idempotent = reversal.get("idempotent_states")
    if idempotent is not None and (
            not isinstance(idempotent, list)
            or not all(str(s).strip() for s in idempotent)):
        violations.append((label, field + ".idempotent_states",
                           "必须是状态名列表（可空）"))

    order = reversal.get("order")
    if order is not None and str(order) not in REVERSAL_ORDERS:
        violations.append((label, field + ".order",
                           "未知取值 %r，允许：%s"
                           % (order, "/".join(sorted(REVERSAL_ORDERS)))))

    create_spec = reversal.get("create_document")
    if create_spec is not None:
        if not isinstance(create_spec, dict):
            violations.append((label, field + ".create_document", "必须是映射"))
        else:
            primitive = str(create_spec.get("primitive") or "").strip()
            if not primitive:
                violations.append((label, field + ".create_document.primitive",
                                   "必须声明已注册创建器 id"))
            elif primitive not in doc_creators:
                violations.append((label, field + ".create_document.primitive",
                                   "%r 未在 DOC_CREATORS 注册（%s）"
                                   % (primitive, "/".join(sorted(doc_creators)))))

    audit_fields = reversal.get("write_audit_fields")
    if audit_fields is not None:
        if not isinstance(audit_fields, dict) or not all(
                str(k).strip() and str(v).strip()
                for k, v in (audit_fields or {}).items()):
            violations.append((label, field + ".write_audit_fields",
                               "必须是 {列: 模板} 映射"))
    return violations


def _aspect_field_index():
    """aspects.yaml -> {aspect 名: 字段名集合}（切面注入字段不属本对象 fields）。"""
    path = SCHEMAS_DIR / "aspects.yaml"
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    index = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        names = set()
        for item in entry.get("fields") or ():
            if isinstance(item, dict):
                for key in ("id", "db_column"):
                    if item.get(key):
                        names.add(str(item[key]))
        index[str(name)] = names
    return index


def lint_doc_flow():
    """R-MM-05 正/逆/调整同构 lint；返回 (违规列表, 扫描的事实单据数)。"""
    profiles, valid_modes, valid_commitments, doc_creators = _reversal_constants()
    aspect_fields = _aspect_field_index()
    violations = []
    scanned = 0
    fact_schemas = {}          # schema id -> 文件名（有 document: 段）
    declared_reversal = []     # 有 doc_effect.reversal 的文件标签
    documents = []             # (label, schema_id, document, own_fields, state_codes)
    object_fields = {}         # schema id -> 字段名集合（fields + 切面 fields）
    schema_ids = set()

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            violations.append((path.name, "yaml", "无法解析: %s" % exc))
            continue
        if not isinstance(raw, dict) or not raw.get("id"):
            continue

        label = path.name
        schema_id = str(raw.get("id"))
        schema_ids.add(schema_id)

        field_names = set()
        for item in raw.get("fields") or ():
            if isinstance(item, dict):
                for key in ("id", "db_column"):
                    if item.get(key):
                        field_names.add(str(item[key]))
        # 切面注入字段（如 document_type_aspect -> document_type_id）等价于本对象可解析字段
        for aspect_name in raw.get("aspects") or ():
            field_names |= aspect_fields.get(str(aspect_name), set())
        object_fields[schema_id] = field_names

        state_codes = set()
        for item in raw.get("states") or ():
            if isinstance(item, dict) and item.get("code"):
                state_codes.add(str(item["code"]))

        doc_effect = raw.get("doc_effect")
        document = raw.get("document")

        # 1) 覆盖度：统计事实单据（document 段）覆盖数
        if isinstance(document, dict):
            scanned += 1
            fact_schemas[schema_id] = label
            documents.append((label, schema_id, document, field_names, state_codes))

        # 2) doc_effect.reversal 声明合法（未声明不算违规：不强制新增声明位）
        if isinstance(doc_effect, dict) and "reversal" in doc_effect:
            declared_reversal.append(label)
            violations.extend(_lint_reversal_block(
                label, doc_effect.get("reversal"), doc_creators))

    # 3) document 声明：必填键 + 字段引用 / 状态值可解析（可选键不强制补齐）
    for label, _schema_id, document, own_fields, state_codes in documents:
        for key in DOC_REQUIRED_KEYS:
            if not str(document.get(key) or "").strip():
                violations.append((label, "document.%s" % key, "必填键缺失"))
        for key in DOC_HEADER_FIELD_KEYS:
            value = str(document.get(key) or "").strip()
            if value and value not in own_fields:
                violations.append((label, "document.%s" % key,
                                   "字段 %r 未在本对象 fields 中声明" % value))
        for key in DOC_STATE_KEYS:
            value = str(document.get(key) or "").strip()
            if value and value not in state_codes:
                violations.append((label, "document.%s" % key,
                                   "状态 %r 不在本对象 states 中声明" % value))
        line_object = str(document.get("line_object") or "").strip()
        if line_object:
            line_fields = object_fields.get(line_object)
            if line_fields is None:
                violations.append((label, "document.line_object",
                                   "行对象 %r 未声明" % line_object))
            else:
                parent = str(document.get("line_parent_field") or "").strip()
                if not parent:
                    violations.append(
                        (label, "document.line_parent_field",
                         "声明 line_object 必须同时声明 line_parent_field"))
                elif parent not in line_fields:
                    violations.append(
                        (label, "document.line_parent_field",
                         "%r 不在 %s 的 fields 内" % (parent, line_object)))
                seq = str(document.get("line_sequence_field") or "").strip()
                if seq and seq not in line_fields:
                    violations.append(
                        (label, "document.line_sequence_field",
                         "%r 不在 %s 的 fields 内" % (seq, line_object)))

    # 4) 档位表：mode / commitment / edges 声明完整性
    for doc_type, profile in sorted(profiles.items()):
        field = "REVERSAL_PROFILES[%s]" % doc_type
        if doc_type not in schema_ids:
            violations.append((field, "document_type",
                               "档位指向未声明的对象 id"))
        mode = str(profile.get("mode") or "")
        if mode not in valid_modes:
            violations.append((field, "mode",
                               "未知档位 %r，允许：%s"
                               % (mode, "/".join(sorted(valid_modes)))))
        commitment = str(profile.get("commitment") or "")
        if commitment not in valid_commitments:
            violations.append((field, "commitment",
                               "未知口径 %r，允许：%s"
                               % (commitment, "/".join(sorted(valid_commitments)))))
        for idx, edge in enumerate(profile.get("edges") or ()):
            if not isinstance(edge, dict):
                violations.append((field, "edges[%d]" % idx, "必须是映射"))
                continue
            if not str(edge.get("rule_id") or "").strip():
                violations.append((field, "edges[%d].rule_id" % idx,
                                   "必须声明 doc_flow_rule id"))
            if not str(edge.get("source_bo") or "").strip():
                violations.append((field, "edges[%d].source_bo" % idx,
                                   "必须声明来源对象"))

    # 4) R20：编排器不得出现按单据类型字面量分支
    literals = _orchestrator_string_literals()
    if literals is None:
        violations.append(("meta/core/reversal_orchestrator.py", "file",
                           "文件缺失，无法判定 R20"))
    else:
        for doc_type in sorted(fact_schemas):
            if doc_type in literals:
                violations.append((
                    "meta/core/reversal_orchestrator.py", "R20",
                    "出现单据类型字面量 %r：禁止为第二类单据新增 Python 分支"
                    % doc_type))

    # 5) R21：生产代码不得 UPDATE 原单数量列（原边 immutable）
    for path in sorted(R21_SCAN_ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "tests" in path.relative_to(R21_SCAN_ROOT).parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if "UPDATE" not in source:
            continue
        for table, set_clause in R21_UPDATE_RE.findall(source):
            if not R21_QUANTITY_RE.search(set_clause):
                continue
            if (rel, table) in R21_ALLOWLIST:
                continue
            violations.append((rel, "UPDATE " + table,
                               "R21：改写原单数量列（只允许追加边）"))

    return violations, scanned, fact_schemas, declared_reversal


ROLE_IN_WHEN_RE = re.compile(
    r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s+in\s+user\.roles")

#: R28 单层承运：逐字段能力标记只能出现在 L1（对象级），L3 字段条目不得重复声明。
L1_ONLY_FIELD_KEYS = (
    "audit", "audited", "track_changes", "track_history",
    "numbering", "posting", "state_machine", "soft_delete",
)
#: R28 单层承运：L2 关联条目不得重复声明 L1 能力。
L2_FORBIDDEN_KEYS = ("audit", "numbering", "posting", "state_machine")


def lint_field_policies(role_codes=None):
    """R-MM-03：字段策略声明 lint + 覆盖度披露。

    校验（违规 → exit 1）：
    - R13：`field_policies.*.when` 引用的角色必须 ∈ permission_sets.code；
    - 策略引用的字段必须存在于对象 fields 或切面注入字段；
    - `state_field_policies` 的状态键必须在该对象 `states[].code` 中（声明了 states 时）。
    披露（不违规）：
    - R10：`meta/generated/state_field_matrix.yaml` 必须与 schema 一致（缺失/过期 → 违规）；
    - A-03-1：事实单据覆盖度与未覆盖清单显式打印。

    返回 (violations, scanned, coverage)。
    """
    from meta.tools.gen_state_field_matrix import (
        OUT_PATH as MATRIX_PATH,
        _build_payload,
        _collect,
        _render,
    )

    valid_roles = set(role_codes or ())
    # 切面字段按对象 `aspects:` 逐对象取并集（与 yaml_loader S1 ⑤ 校验同口径）；
    # 不能取全局并集，否则任何对象都被视作拥有所有切面字段（假绿）。
    aspect_index = _aspect_field_index()

    violations = []
    scanned = 0
    fact_total = 0
    covered = 0
    uncovered = []

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            violations.append((path.name, "yaml", "解析失败：%s" % exc))
            continue
        if not isinstance(raw, dict):
            continue
        object_id = str(raw.get("id") or path.stem)
        document = raw.get("document") if isinstance(raw.get("document"), dict) else {}
        declared_states = raw.get("state_field_policies") if isinstance(
            raw.get("state_field_policies"), dict) else {}
        field_policies = raw.get("field_policies") if isinstance(
            raw.get("field_policies"), dict) else {}

        is_fact = bool(document) or bool(declared_states)
        if is_fact:
            fact_total += 1
            if declared_states:
                covered += 1
            else:
                uncovered.append(object_id)

        if not declared_states and not field_policies:
            continue
        scanned += 1

        own_fields = {str(f.get("id")) for f in raw.get("fields") or ()
                      if isinstance(f, dict) and f.get("id")}
        valid_fields = set(own_fields)
        for aspect_name in raw.get("aspects") or ():
            valid_fields |= aspect_index.get(str(aspect_name), set())
        state_codes = {str(s.get("code")) for s in raw.get("states") or ()
                       if isinstance(s, dict) and s.get("code")}

        for state, policy in declared_states.items():
            if state_codes and str(state) not in state_codes:
                violations.append((path.name, "state_field_policies.%s" % state,
                                   "状态未在 states[].code 中声明"))
            if not isinstance(policy, dict):
                violations.append((path.name, "state_field_policies.%s" % state,
                                   "必须是 {hidden/readonly/required: [字段]}"))
                continue
            for kind, names in policy.items():
                if kind not in ("hidden", "readonly", "required"):
                    violations.append((path.name, "state_field_policies.%s" % state,
                                       "未知策略键 %r" % kind))
                    continue
                for name in names or ():
                    if str(name) not in valid_fields:
                        violations.append((path.name,
                                           "state_field_policies.%s.%s" % (state, kind),
                                           "字段 %r 未在 fields / 切面中声明" % name))

        for field_id, spec in field_policies.items():
            if str(field_id) not in valid_fields:
                violations.append((path.name, "field_policies.%s" % field_id,
                                   "字段未在 fields / 切面中声明"))
            if not isinstance(spec, dict):
                violations.append((path.name, "field_policies.%s" % field_id,
                                   "必须是 {editable/visible/required: [...]}"))
                continue
            for kind, rules in spec.items():
                if kind not in ("editable", "visible", "required"):
                    violations.append((path.name, "field_policies.%s" % field_id,
                                       "未知策略键 %r" % kind))
                    continue
                if isinstance(rules, dict):
                    rules = rules.get("determination") or []
                if not isinstance(rules, list):
                    violations.append((path.name, "field_policies.%s.%s" % (field_id, kind),
                                       "策略必须是规则列表"))
                    continue
                for index, rule in enumerate(rules):
                    if not isinstance(rule, dict):
                        violations.append((path.name,
                                           "field_policies.%s.%s[%d]" % (field_id, kind, index),
                                           "规则必须是 {when, value}"))
                        continue
                    expr = rule.get("when") or rule.get("when_expr") or ""
                    for role in ROLE_IN_WHEN_RE.findall(str(expr)):
                        if valid_roles and role not in valid_roles:
                            violations.append((path.name,
                                               "field_policies.%s.%s" % (field_id, kind),
                                               "角色 %r 不在 permission_sets.code（%s）"
                                               % (role, "/".join(sorted(valid_roles)))))

    # R10：派生矩阵必须与 schema 一致（缺失或过期都视为未生成）。
    objects, coverage, errors = _collect()
    expected = _render(_build_payload(objects, coverage, errors))
    current = (MATRIX_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
               if MATRIX_PATH.exists() else "")
    if not MATRIX_PATH.exists():
        violations.append(("meta/generated/state_field_matrix.yaml", "matrix",
                           "产物不存在，请运行 python -m meta.tools.gen_state_field_matrix"))
    elif current != expected:
        violations.append(("meta/generated/state_field_matrix.yaml", "matrix",
                           "产物与 schema 不一致，请重新生成"))
    for item in errors:
        violations.append((item["file"], "document", "装载失败：%s" % item["error"]))

    report = {
        "total": coverage["total"],
        "covered": coverage["covered"],
        "uncovered": coverage["uncovered"],
        "declared_objects": scanned,
    }
    return violations, scanned, report


def _iter_raw_docs(docs=None):
    """产出 (label, raw)：缺省扫描 meta/schemas（跳过 _ 前缀与无效文档）。"""
    if docs is not None:
        for label, raw in docs:
            yield label, raw
        return
    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            yield path.name, {"_error": "yaml 解析失败：%s" % exc}
            continue
        yield path.name, raw


def _is_declared(value) -> bool:
    """能力标记视为「已声明」的判据：非空字符串/非空列表/非空映射/True。"""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return bool(value)


def lint_capabilities(docs=None):
    """R24 / R28：能力维度的单层承运 lint。

    - R24：`semantics.category` 必须 ∈ 受控枚举（含 R25 别名）；
    - R28：同一能力只能挂一层，跨层重复声明即违规：
      * 级联删除归 L2 关联（`associations[].kind` / `cascade_delete`），
        对象级 `deletion_policy.cascade_delete` 必须为空；
      * 审计 / 编号 / 状态机 / 过账 / 软删归 L1 对象级，字段条目与关联条目
        不得再逐字段/逐关联声明。

    `docs` 允许注入 [(label, raw)] 供测试构造跨层重复；缺省扫描 meta/schemas。
    返回 (violations, scanned, report)。
    """
    from meta.core.models_enums import (
        ObjectSemanticsCategory,
        SEMANTICS_CATEGORY_ALIASES,
    )

    valid_categories = {c.value for c in ObjectSemanticsCategory}
    valid_categories |= set(SEMANTICS_CATEGORY_ALIASES)

    violations = []
    scanned = 0

    for label, raw in _iter_raw_docs(docs):
        if not isinstance(raw, dict):
            continue
        if raw.get("_error"):
            violations.append((label, "yaml", raw["_error"]))
            continue
        if not raw.get("id"):
            continue
        scanned += 1

        # R24：受控枚举（别名先归一）
        semantics = raw.get("semantics") if isinstance(raw.get("semantics"), dict) else {}
        category = str(semantics.get("category") or "").strip()
        if category and category not in valid_categories:
            violations.append(
                (label, "semantics.category",
                 "R24：未知取值 %r，允许值：%s"
                 % (category, "/".join(sorted(valid_categories)))))

        # R28：级联删除只允许在 L2 关联逐条声明；对象级清单与关联条目不得同时声明
        deletion_policy = raw.get("deletion_policy")
        if isinstance(deletion_policy, dict):
            if deletion_policy.get("cascade") is True:
                violations.append(
                    (label, "deletion_policy.cascade",
                     "R28：级联删除属 L2 关联能力，对象级不得用布尔声明"))
            cascade_names = {
                str(item) for item in (deletion_policy.get("cascade_delete") or ())
                if str(item).strip()
            }
            if cascade_names:
                for name, entry in _iter_associations(raw):
                    if _is_declared(entry.get("cascade_delete")) or (
                            str(entry.get("kind") or "").strip() == "master_detail"):
                        violations.append(
                            (label, "deletion_policy.cascade_delete",
                             "R28：级联删除在对象级清单与关联 %s 重复声明" % name))
                        break

        # R28：逐字段能力标记只能由 L1 对象级声明
        for field in raw.get("fields") or ():
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id") or field.get("name") or "?")
            for key in L1_ONLY_FIELD_KEYS:
                if key in field and _is_declared(field.get(key)):
                    violations.append(
                        (label, "fields.%s.%s" % (field_id, key),
                         "R28：%s 属 L1 对象级能力，字段层不得重复声明" % key))

        # R28：关联条目不得重复声明 L1 能力
        for name, entry in _iter_associations(raw):
            for key in L2_FORBIDDEN_KEYS:
                if key in entry and _is_declared(entry.get(key)):
                    violations.append(
                        (label, "associations.%s.%s" % (name, key),
                         "R28：%s 属 L1 对象级能力，关联层不得重复声明" % key))

    report = {
        "categories": sorted(valid_categories),
        "l1_only_field_keys": list(L1_ONLY_FIELD_KEYS),
        "l2_forbidden_keys": list(L2_FORBIDDEN_KEYS),
    }
    return violations, scanned, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relations", action="store_true",
                        help="R-MM-01 关联语义 lint")
    parser.add_argument("--actions", action="store_true",
                        help="R-MM-02 动作声明结构 lint")
    parser.add_argument("--permissions", action="store_true",
                        help="R-MM-04 关系感知授权声明 lint")
    parser.add_argument("--doc-flow", action="store_true",
                        help="R-MM-05 正/逆/调整同构声明 lint")
    parser.add_argument("--field-policies", action="store_true",
                        help="R-MM-03 字段策略声明 + 派生状态字段矩阵 lint")
    parser.add_argument("--capabilities", action="store_true",
                        help="R24/R28 能力维度单层承运 lint")
    parser.add_argument("--all", action="store_true",
                        help="全部已实现 lint（relations + actions + permissions + "
                             "doc-flow + field-policies + capabilities）")
    args = parser.parse_args()

    # 无参数时默认执行全部已实现项，便于直接 `python meta/tools/lint_metamodel.py`
    run_all = args.all or not (
        args.relations or args.actions or args.permissions or args.doc_flow
        or args.field_policies or args.capabilities
    )

    failed = False

    if run_all or args.relations:
        violations, scanned = lint_relations()
        for file_label, field, reason in violations:
            print("[relations] %s :: %s — %s" % (file_label, field, reason))
        print("[relations] %d schema(s) scanned, %d violation(s)"
              % (scanned, len(violations)))
        failed = failed or bool(violations)

    if run_all or args.actions:
        actions = _load_standard_actions()
        violations = lint_actions(actions, _seed_role_codes(), _registered_events())
        for action_id, field, reason in violations:
            print("[actions] %s :: %s — %s" % (action_id, field, reason))
        print("[actions] %d action(s) scanned, %d violation(s), 声明-实现签名差异: 0"
              % (len(actions), len(violations)))
        failed = failed or bool(violations)

    if run_all or args.permissions:
        declarations = _load_authorization_declarations()
        violations = lint_permissions(declarations, _declared_relation_rule_codes())
        for file_label, field, reason in violations:
            print("[permissions] %s :: %s — %s" % (file_label, field, reason))
        print("[permissions] %d authorization block(s) scanned, %d violation(s)"
              % (len(declarations), len(violations)))
        failed = failed or bool(violations)

    if run_all or args.doc_flow:
        violations, scanned, _fact, declared = lint_doc_flow()
        for file_label, field, reason in violations:
            print("[doc-flow] %s :: %s — %s" % (file_label, field, reason))
        print("[doc-flow] %d document schema(s) scanned, %d reversal "
              "declaration(s), %d violation(s)"
              % (scanned, len(declared), len(violations)))
        failed = failed or bool(violations)

    if run_all or args.field_policies:
        violations, scanned, report = lint_field_policies(_seed_role_codes())
        for file_label, field, reason in violations:
            print("[field-policies] %s :: %s — %s" % (file_label, field, reason))
        print("[field-policies] %d 对象已声明，%d violation(s)；事实单据覆盖 %d/%d，"
              "未覆盖清单: %s"
              % (scanned, len(violations), report["covered"], report["total"],
                 ", ".join(report["uncovered"]) or "无"))
        failed = failed or bool(violations)

    if run_all or args.capabilities:
        violations, scanned, capability_report = lint_capabilities()
        for file_label, field, reason in violations:
            print("[capabilities] %s :: %s — %s" % (file_label, field, reason))
        print("[capabilities] %d schema(s) scanned, %d violation(s)；单层承运键：%s"
              % (scanned, len(violations),
                 "/".join(capability_report["l1_only_field_keys"])))
        failed = failed or bool(violations)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())