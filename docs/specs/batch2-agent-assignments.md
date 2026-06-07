# 批次 2 多 Agent 并行开发协调手册（v1 批次 2 — 后端能力扩展）

> **版本**: v1.1 | **日期**: 2026-06-07 | **状态**: 🟡 Agent A 实施中
> **配套文档**:
> - [spec-batch2-detailed-plan-v2.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md) — 详细实施 v2（**实施权威**）
> - [spec-batch2-backend-capabilities.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-backend-capabilities.md) — 12 任务详细实施
> - [spec-pre-deployment-optimization.md (v1.1.0)](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) — 原始规格
> - [.trae/rules/multi-agent-coordination.md](file:///d:/filework/.trae/rules/multi-agent-coordination.md) — 协作铁律

---

## 〇、前置状态（2026-06-07）

**批次 1 已完成**（v1 规格第 11 行）：FR-1 + FR-5 共 10 任务。

**批次 2 范围**（v1 规格第 12 行）：FR-2 + FR-3 + FR-4 共 12 任务，**全部后端**。

**git 状态**：已修复（main 分支创建 + 初始 commit `55f1508` + `batch2/wave1` 分支未 checkout）。

**v1 批次 2 当前状态**（2026-06-07 下午）：
- **已落地（5/13 子任务）**：Agent A 完成 FR-2.1/2.2/2.3/2.4/4.5a 代码，未提交
- **未开始（8/13）**：FR-3.1/3.2/3.3 + FR-4.1/4.2/4.3/4.4/4.5
- **基础设施已就绪**：QueryInterceptor / FieldPolicyEngine / RequiredPolicy / safe_evaluate / useMetaList / useFieldPolicy

**git worktree 方案作废**：Windows + PowerShell 环境下 `git worktree add` 失败（HEAD unborn SHA 0000000），改用单仓库顺序开发。

---

## 〇.B、Agent A 战报（5 任务已落地）

**已写代码**：
- `meta/api/bo_action_api.py:538-665` `_generate_action_openapi()` 提取（FR-2.1）
- `meta/api/bo_action_api.py:668-680` `openapi_spec()` 端点简化（FR-2.1）
- `meta/api/bo_api.py:1112-1156` `get_full_openapi()` 端点（FR-2.4）
- `meta/api/bo_api.py:1180-1211` `conditional_required` 字段追加（FR-4.5a）
- `meta/api/bo_api.py:1870-2030` 4 个工具函数 `_TYPE_MAP` / `_map_field_type` / `_generate_bo_schema` / `_generate_bo_crud_paths`（FR-2.2/2.3）

**调试战报 4 bug**：
1. ✅ SyntaxError: 锚点缩进陷阱（Edit 工具误插 try 块内）
2. ✅ AttributeError 'MetaField.type': v1 假设 `.type` 实际是 `.field_type`（FieldType enum）
3. ✅ AttributeError 'UIAnnotation.get': v1 假设 `ui` 是 dict，实际是 dataclass
4. ❌ AttributeError 'str.get' at L1904: `field.enum_values` 元素可能是 str（**待修复**）

**修复方法详见**：[spec-batch2-detailed-plan-v2.md §2.3](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md)

**当前分支**：`batch2/agent-a-openapi`（0 commit，待 500 错误修复后一次性提交）

---

## 一、4 Agent 分配（FR-3 拆分为 B+C）

> **变更**：v1.1 将原 3 Agent 调整为 4 Agent。理由：FR-3.1/3.2（后端）与 FR-3.3（前端）分属不同文件集；FR-4.5（前端）也可与 FR-4.1/4.2/4.3/4.4（后端）拆开。**4 个 Agent 文件集完全无重叠**。

| Agent | 任务 | 文件 | 端口 |
|-------|------|------|------|
| **A**（实施中）| FR-2 OpenAPI（4）+ FR-4.5a（顺手）| `bo_action_api.py` + `bo_api.py` | 3010 |
| **B** | FR-3.1/3.2 display_values 后端 | `query_interceptor.py` | 3011 |
| **C** | FR-3.3 + FR-4.5 前端 | `useMetaList.js` + `useFieldPolicy.js` | 3012 |
| **D** | FR-4.1/4.2/4.3/4.4 conditional_required 后端 | `constraint_engine.py` + `field_policy_engine.py` + `business_object.yaml` | 3013 |

**冲突分析**：
- 4 个 Agent 文件集**完全无重叠**
- Agent C 依赖 Agent B（前端需先有后端 display_values）
- Agent D 可与 Agent B/C 并行（无文件冲突）
- 合并到 main 时按 A → B → C → D 顺序

**worktree 方案**：废弃（PowerShell + Windows 失败），改用单仓库顺序开发。**每次切分支前 stop 服务、切完再 start**（service_manager.ps1 持锁）。

---

## 二、Agent 串行任务链

### 2.1 Agent A（FR-2）

```
FR-2.1 提取 _generate_action_openapi()     [bo_action_api.py:538-671]
   ↓
FR-2.2 _generate_bo_crud_paths()           [bo_api.py]
   ↓
FR-2.3 _generate_bo_schema()               [bo_api.py]
   ↓
FR-2.4 @meta_v2_bp.route('/_openapi.json') [bo_api.py]
```

### 2.2 Agent B（FR-3）

```
FR-3.1 _inject_display_values()            [query_interceptor.py]
   ↓
FR-3.2 after_action 接入                   [query_interceptor.py]
   ↓
FR-3.3 useMetaList.js 读 display_values    [useMetaList.js]
```

### 2.3 Agent C（FR-4）

```
FR-4.1 _check_conditional_required()       [constraint_engine.py]
   ↓
FR-4.2 _check_constraint() 路由             [constraint_engine.py]
   ↓
FR-4.3 is_field_required() 联动            [field_policy_engine.py]
   ↓
FR-4.4 YAML 示例                           [business_object.yaml]   ─┐
   ↓                                                            并行
FR-4.5 useFieldPolicy.js 读 conditional_required [useFieldPolicy.js] ─┘
```

---

## 三、启动模板（3 个 Agent 通用）

### 3.1 Agent A 启动（端口 3010）

```bash
# Step 1: 创建 worktree
cd d:\filework\excel-to-diagram
git fetch origin
git worktree add d:/workplace/agent-a-openapi -b batch2/agent-a-openapi main
cd d:/workplace/agent-a-openapi

# Step 2: 启动服务
$env:AGENT_PORT = 3010
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3010
pip install -r d:\filework\excel-to-diagram\requirements.txt   # 首次

# Step 3: 实施（按 spec 第五章 5.1-5.4）
# TBD-1 确认: meta_v2_bp 是否已存在？
# TBD-2 确认: meta.services.meta_object_registry.registry.all() 是否可用？

# Step 4: 验证
python -c "from meta.api.bo_action_api import _generate_action_openapi; print(_generate_action_openapi()['openapi'])"
curl http://localhost:3010/api/v2/bo/_openapi.json | head -c 500
python d:\filework\test.py --port 3010 --failed

# Step 5: 提交
git add -A
git commit -m "batch2(FR-2): OpenAPI auto-gen for BO CRUD + MetaObject"
git push -u origin batch2/agent-a-openapi

# Step 6: 关闭
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop -Port 3010
```

### 3.2 Agent B 启动（端口 3011）

```bash
cd d:\filework\excel-to-diagram
git worktree add d:/workplace/agent-b-display -b batch2/agent-b-display main
cd d:/workplace/agent-b-display
$env:AGENT_PORT = 3011
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3011

# 实施（按 spec 第五章 5.5-5.7）
# 验证
curl http://localhost:3010/api/v2/bo/business_object | python -c "import json,sys; d=json.load(sys.stdin); assert 'display_values' in d['items'][0] or len(d['items'])==0; print('OK')"
python d:\filework\test.py --port 3011 --failed

git add -A
git commit -m "batch2(FR-3): display_values 注入 + 前端读取"
git push -u origin batch2/agent-b-display
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop -Port 3011
```

### 3.3 Agent C 启动（端口 3012）

```bash
cd d:\filework\excel-to-diagram
git worktree add d:/workplace/agent-c-conditional -b batch2/agent-c-conditional main
cd d:/workplace/agent-c-conditional
$env:AGENT_PORT = 3012
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3012

# 实施（按 spec 第五章 5.8-5.12）
# TBD-3 确认: /field-policies API 是否能返回 conditional_required？
#            如不能，FR-4.5 仅写占位接口

# 验证
curl -X POST http://localhost:3010/api/v2/bo/sub_domain -d '{"domain_id":"d1","sub_domain_id":null}' -H "Content-Type: application/json"
# 应返回 400 + "选择领域后，子领域不能为空"
python d:\filework\test.py --port 3012 --failed

git add -A
git commit -m "batch2(FR-4): conditional_required 条件必填校验"
git push -u origin batch2/agent-c-conditional
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop -Port 3012
```

---

## 四、每个 Agent 详细任务卡

### 4.1 Agent A — FR-2 OpenAPI + FR-4.5a（端口 3010）🟡 实施中

**目标文件**:
- [meta/api/bo_action_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_action_api.py) — FR-2.1
- [meta/api/bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py) — FR-2.2/2.3/2.4/4.5a

**任务清单**:
1. bo_action_api.py: 提取 L538-671 `/_openapi.json` 内部生成为 `_generate_action_openapi()` ✅
2. bo_action_api.py: 端点改为 `return jsonify(_generate_action_openapi())` ✅
3. bo_api.py: 新增 `_generate_bo_crud_paths(meta_objects)` 函数 ✅
4. bo_api.py: 新增 `_map_field_type()` 和 `_generate_bo_schema()` 函数 ✅
5. bo_api.py: 新增 `@meta_v2_bp.route('/_openapi.json')` 端点（**全量**）✅
6. bo_api.py: `get_field_policies` 字典追加 `conditional_required`（FR-4.5a 顺手）✅

**当前状态**：代码 100% 写完，500 错误待修（v2 §2.3 bug #4）
**下一步**：
1. 修 bug #4（`field.enum_values` 兼容 str）
2. 重启 backend + curl 200 OK
3. `python d:\filework\test.py --port 3010 --failed` 回归
4. git add + commit + merge main + delete branch

**详细实施**：见 [spec-batch2-detailed-plan-v2.md §2](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md)

### 4.2 Agent B — FR-3.1/3.2 display_values 后端（端口 3011）⏳ 待启动

**目标文件**:
- [meta/core/interceptors/query_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) — FR-3.1/3.2

**任务清单**:
1. query_interceptor.py: 新增 `_inject_display_values()` 方法（v2 §3.1 含完整代码）
2. query_interceptor.py: `after_action()` 中 `_enrich_records` 之后、`_compute_columns` 之前调用

**启动条件**: Agent A 已合并
**风险点**: query_interceptor.py 性能影响（O(N) 操作）、enum_values 兼容（与 Agent A bug #4 同源）
**验证**:
```bash
curl.exe -b "auth_token=xxx" "http://localhost:3010/api/v2/bo/user?page=1&page_size=2" | python -c "
import json, sys
d = json.load(sys.stdin)
for it in d.get('items', []):
    print('id:', it.get('id'), 'display_values keys:', list((it.get('display_values') or {}).keys()))
"
```
**详细实施**：见 [spec-batch2-detailed-plan-v2.md §3.1](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md)

### 4.3 Agent C — FR-3.3 + FR-4.5 前端（端口 3012）⏳ 待启动

**目标文件**:
- [src/composables/useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) — FR-3.3
- [src/composables/useFieldPolicy.js](file:///d:/filework/excel-to-diagram/src/composables/useFieldPolicy.js) — FR-4.5

**任务清单**:
1. useMetaList.js:1646 `getCellValue` 优先读 `row.display_values?.[fieldName]`（编辑模式 draftValues 优先）
2. useFieldPolicy.js: 追加 `requiredMap` 状态 + `evaluateConditionalRequired()` 方法

**启动条件**: Agent B 已合并（FR-3.3 依赖后端 display_values）
**风险点**: 前端 `new Function` 沙箱（生产环境应换 JEXL）
**验证**:
- 浏览器打开 `http://localhost:5173/user`，检查列表中 FK 字段显示 display_name 而非 ID
- 检查 boolean 字段显示"是/否"
- 表单提交时检查条件必填触发

**详细实施**：见 [spec-batch2-detailed-plan-v2.md §3.1/3.2](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md)

### 4.4 Agent D — FR-4.1/4.2/4.3/4.4 conditional_required 后端（端口 3013）⏳ 待启动

**目标文件**:
- [meta/core/constraint_engine.py](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py) — FR-4.1/4.2
- [meta/services/field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py) — FR-4.3
- [meta/schemas/business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml) — FR-4.4

**任务清单**:
1. constraint_engine.py: 新增 `_check_conditional_required()` 方法（v2 §3.3 含完整代码）
2. constraint_engine.py: `_check_constraint()` 路由追加 `conditional_required` 分支
3. field_policy_engine.py: `is_field_required()` 中检查 `conditional_required`（保守策略：返回 True）
4. business_object.yaml: examples 段追加 `conditional_required_demo` 示例

**启动条件**: 立即（无依赖 Agent B/C，可与 Agent B/C 并行）
**风险点**: field_policy_engine.py 改动影响范围广
**验证**:
```bash
# 1. 加载新 YAML 后，调 POST /api/v2/bo/conditional_required_demo
#    body: {"domain_id":"finance","sub_domain_id":null} → 期望 400 + "选择领域后，子领域必填"
# 2. GET /api/v2/meta/conditional_required_demo/field-policies
#    → 检查 conditional_required 数组非空
```
**详细实施**：见 [spec-batch2-detailed-plan-v2.md §3.3](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-detailed-plan-v2.md)

---

## 五、合并顺序（4 Agent 串行 → main）

```
4 个 PR 全部 ready 后:
  PR-A (FR-2 + FR-4.5a) → main  ← 先合（OpenAPI 改动最独立）
  PR-B (FR-3.1/3.2)      → main  ← 第二合（query_interceptor 独立）
  PR-C (FR-3.3 + FR-4.5) → main  ← 第三合（前端，依赖 B 后端）
  PR-D (FR-4.1-4.4)      → main  ← 最后合（constraint_engine + field_policy 双文件）
```

**实际可并行性**（单仓库顺序开发约束下）：
- A 必须最早
- B 和 D 文件完全不重叠，可同时切到各自分支**顺序**实施（不是并行 worktree）
- C 依赖 B（前端读后端字段）
- 合并顺序：A → (B ∥ D) → C → D

**合并冲突检测**（PM 执行，单仓库顺序开发）:
```bash
# 每个 Agent 实施完成后，由 PM 在 Agent 退出前直接合并到 main
git checkout main
git merge --no-ff batch2/agent-a-openapi   # 合并后删除
git branch -d batch2/agent-a-openapi
# 下一个 Agent
git checkout -b batch2/agent-b-display main
# ... Agent B 实施
git checkout main
git merge --no-ff batch2/agent-b-display
git branch -d batch2/agent-b-display
# 等等
```

**实际冲突概率**:
- A 与 B：0%（bo_api.py vs query_interceptor.py）
- A 与 C：0%（bo_api.py vs useMetaList.js / useFieldPolicy.js）
- A 与 D：0%（bo_api.py vs constraint_engine.py + field_policy_engine.py + yaml）
- B 与 C：0%（query_interceptor.py vs useMetaList.js）
- B 与 D：0%（query_interceptor.py vs constraint_engine.py）
- C 与 D：0%（useFieldPolicy.js vs constraint_engine.py + yaml）
- **结论：4 PR 可放心顺序合并（单仓库约束下不并行）**

---

## 六、关键风险与缓解（v1.1 更新）

| 风险 | 状态 | 缓解 |
|------|------|------|
| TBD-1 `meta_v2_bp` 是否存在 | ✅ 已确认存在（bo_api.py:16）| — |
| TBD-2 `registry.all()` 是否可用 | ✅ 已确认存在 | `meta_objects = list(registry.all()) if hasattr(registry, 'all') else []` 防御 |
| TBD-3 `/field-policies` 返回 `conditional_required` | ✅ Agent A 顺手追加（FR-4.5a）| — |
| **新发现 bug #4**: `field.enum_values` 元素是 str 不是 dict | ❌ Agent A 修复中 | v2 §2.3 兼容写法（isinstance + getattr）|
| **新发现风险**: 前端 `new Function` 表达式注入 | 🟡 低（FR-4.5）| MVP 用基础白名单 + with 沙箱；生产换 JEXL |
| **新发现风险**: FR-3.1 FK 字段依赖 enrichment_engine | 🟡 中 | 实施时 grep 确认输出；缺失则补 |
| **新发现风险**: git worktree 失败 | 🟢 已规避 | 改用单仓库顺序开发 |
| **新发现风险**: service_manager 陈旧状态 | 🟢 已规避 | 启动失败时清 `.service_status_3010.json` + 手动 Start-Process |
| 批次 1 与批次 2 改动有冲突 | ✅ 无冲突 | 4 个 Agent 文件集无重叠 |
| 显示注入性能 | 🟡 中 | `_inject_display_values` 仅在 `is_query_action` 触发；空 records 提前 return |
| `field_policy_engine.is_field_required()` 改动 | 🟡 中 | 2.5 步追加，已有的 1-2 步不变；新逻辑只读不改 |

---

## 七、状态检查命令（PM 视角，单仓库版）

```bash
# 1. 查看当前分支（单仓库顺序开发）
cd d:\filework\excel-to-diagram
git branch --show-current
git status --short

# 2. 查看所有 service 状态
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 3. 查看 batch2 分支
git branch -a | grep batch2

# 4. 查看每个 Agent 的最近 commit
git log --oneline -1 batch2/agent-a-openapi
git log --oneline -1 batch2/agent-b-display
git log --oneline -1 batch2/agent-c-frontend
git log --oneline -1 batch2/agent-d-conditional

# 5. 查看 test.py 整体状态
python d:\filework\test.py --status

# 6. 查看 backend 是否运行
curl.exe -s -o /dev/null -w "%{http_code}" http://localhost:3010/api/v2/action/_openapi.json
# 期望 200
```

---

## 八、关键检查清单（Agent 复制）

```
[ ] Agent 已阅读 spec-batch2-backend-capabilities.md
[ ] Agent 已创建 worktree + 分配端口
[ ] Agent 已启动 service_manager
[ ] Agent 已处理 TBD（如 Agent A 的 TBD-1/TBD-2）
[ ] Agent 已按 spec 实施代码
[ ] Agent 已跑该 Agent 涉及的单测（--single）
[ ] Agent 已跑 --failed 验证
[ ] Agent 已提交 1 个 commit + push 到远程分支
[ ] Agent 已通知 PM 准备合并
[ ] PM 已验证 PR 无冲突
[ ] PM 已合并 PR
[ ] Agent 已关闭 worktree（保留分支）
```

---

## 九、附录

### 9.1 完整文件路径

- v1 规格: [spec-pre-deployment-optimization.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-pre-deployment-optimization.md) (v1.1.0)
- 批次 2 实施细节: [spec-batch2-backend-capabilities.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-batch2-backend-capabilities.md)
- 协作铁律: [.trae/rules/multi-agent-coordination.md](file:///d:/filework/.trae/rules/multi-agent-coordination.md)
- 服务管理: `d:\filework\excel-to-diagram\scripts\service_manager.ps1`

### 9.2 端口速查

| 端口 | Agent | 任务 |
|------|-------|------|
| 3010 | A | FR-2 OpenAPI（4 任务）|
| 3011 | B | FR-3 display_values（3 任务）|
| 3012 | C | FR-4 conditional_required（5 任务）|

### 9.3 任务清单

| Agent | 任务数 | 文件 | 改动行数估算 |
|-------|--------|------|------------|
| A (FR-2) | 4 | bo_action_api.py + bo_api.py | +130 |
| B (FR-3) | 3 | query_interceptor.py + useMetaList.js | +60 |
| C (FR-4) | 5 | constraint_engine.py + field_policy_engine.py + business_object.yaml + useFieldPolicy.js | +70 |
| **总计** | **12** | **8 文件** | **+260** |

### 9.4 单 Agent vs 多 Agent 决策

**单 Agent 方案**（推荐用于此场景）:
- 1 个 worktree + 端口 3010
- 顺序完成 A → B → C 3 个 FR（12 任务）
- 优势：冲突面 0，合并简单，回归面 1 个 PR

**多 Agent 并行方案**（可选，用于加速）:
- 3 个 worktree + 端口 3010/3011/3012
- 3 个 Agent 同时启动
- 优势：速度 3x；劣势：3 个 PR 管理

如果只有 1 个 AI Agent 实施，推荐单 Agent 方案（避免无意义并行）。如果有多 Agent 实施资源，用 3 Agent 并行。
