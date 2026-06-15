# BMRD DEFER 解锁指南 (v1.0)

> **目的**: 当前 11 个 DEFER 项的解锁路径明确化, 前端实现后可立即激活
> **状态**: 2026-06-14 更新

## 当前 DEFER 项总览

| ID | 类别 | 解锁条件 | 影响文件 | 优先级 |
|----|------|---------|---------|--------|
| C01-DEEP | deep-insert UI | Frontend ObjectChildSection 实现 | `_protection_rules.yaml` | P1 |
| C02-DEEP | deep-insert UI | Frontend ObjectChildSection 实现 | `_protection_rules.yaml` | P1 |
| BUG-V005 | deep-insert 校验 | Frontend createChild 客户端空 name 校验 | `_protection_rules.yaml` | P1 |
| C01-DEEP (audit) | deep-insert UI | 同上 | `_audit_i18n_fk_rules.yaml` | P1 |
| C02-DEEP (audit) | deep-insert UI | 同上 | `_audit_i18n_fk_rules.yaml` | P1 |

## 解锁流程 (3 步)

### Step 1: 修改 YAML

把规则的 `status: DEFER` 改为 `status: ACTIVE`, 同时从 `deferred` 列表中移除对应项。

**示例** (ObjectChildSection 修复后):

```yaml
# 之前 (_protection_rules.yaml)
- id: C01-DEEP
  status: DEFER
  test_templates:
    - title: 深插入: 创建父+子

# 之后
- id: C01-DEEP
  status: ACTIVE
  test_templates:
    - title: 深插入: 创建父+子
```

### Step 2: 重新生成 spec

```bash
cd d:\filework\excel-to-diagram
python scripts/fix_yaml_colons.py
python scripts/generate-protection-tests.py
```

输出会显示新的测试数 (例如从 47 增加到 49)。

### Step 3: 跑测试验证

```bash
npx playwright test e2e/business-flow/protection-rules.spec.js --reporter=list
```

期望: 新测试 PASS (不再 skip)。

## 监控/触发条件 (建议)

### 自动监控建议

1. **前端 ObjectChildSection 实现 PR 合并时**:
   - GitHub Action: 检测 `ObjectChildSection.vue` 文件有实质变更
   - 触发: 改 BMRD YAML 状态 DEFER → ACTIVE

2. **AUDIT_WRITE_FAILED 计数归零时**:
   - 已完成 (2026-06-14): 新写入已恢复, 历史 867 条仍未清理
   - 后续: 写清理脚本标记历史失败为 `resolved=1`

### 手动监控清单

- [ ] **每月 1 次**: 检查 DEFER 项, 评估解锁可行性
- [ ] **每次前端 release**: 扫描是否包含 ObjectChildSection 相关 PR
- [ ] **每次后端 release**: 检查是否有 `AUDIT_WRITE_FAILED` 修复

## 解锁后预期效果

| 操作 | 当前 | 解锁后 |
|------|------|--------|
| BMRD 总规则 | 36 | 36 (数量不变) |
| BMRD ACTIVE | 33 | 36 (+3) |
| BMRD DEFER (pending) | 11 | 8 (-3) |
| 生成测试 | 47 | 50 (+3) |
| 真正执行的测试 | 21 | 24 (+3) |
| 跳过的测试 | 26 | 23 (-3) |

## 扩展 DEFER 项的指南

当新发现需要 DEFER 的项时, 按以下格式记录:

```yaml
- id: NEW-DEFER-ID
  reason: '简明原因'
  blocking: '阻塞条件描述'
  unlock_action: |
    详细解锁步骤:
    1. 检查 X
    2. 改 Y 为 Z
    3. 重跑生成器
```

**好 DEFER 项的特征**:
- ✅ 阻塞条件明确 (前端组件未实现/后端 bug 已知)
- ✅ 解锁路径清晰 (改 1-2 处即可)
- ✅ 不影响其他规则 (独立)

**坏 DEFER 项的特征** (应避免):
- ❌ 阻塞条件模糊 ("等业务确认")
- ❌ 解锁路径长 (改 5+ 处)
- ❌ 与其他规则耦合

## 团队沟通

- **DEFER 项状态**: 每月在团队周会同步 1 次
- **解锁 PR**: 标题前缀 `[BMRD-UNLOCK]`, 描述用 `closes #<issue>`
- **新增 DEFER 项**: PR 标题 `[BMRD-DEFER]`, 必须填解锁条件

## 参考

- `_protection_rules.yaml` - 业务保护规则源
- `_crud_lifecycle_rules.yaml` - CRUD + 生命周期规则源
- `_audit_i18n_fk_rules.yaml` - 审计 + i18n + FK 规则源
- `scripts/generate-protection-tests.py` - BMRD 生成器
- `scripts/fix_yaml_colons.py` - YAML 引号修复工具
