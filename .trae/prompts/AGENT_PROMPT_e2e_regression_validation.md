# 任务: E2E 回归验证 (E21 修复 + DIM 路由迁移无回归)

> **目标**: 跑全部 v2 E2E 套件 (270+ 测试), 验证 E21 脏数据机制修复 + DIM 路由代码改动无回归
> **背景**: 2026-06-14 主 Agent 做了 2 个关键代码改动:
>   1. E21 脏数据修复 (ObjectPageShell + ObjectDetailPage 共 12 行)
>   2. DIM 路由迁移 (management_dimension_api.py url_prefix 改动)
> **期望**: 跑全部 E2E 确认无回归, 如有失败详细分析根因

## 关键改动详情 (必须知道的)

### 1. E21 脏数据机制
- **文件 1**: `src/components/common/ObjectPage/ObjectPageShell.vue`
  - line 414-419: `handleFieldUpdate` 加 `markFieldDirty(key)` 调用
  - 作用: 所有字段修改 (不只 code 字段) 都会触发 dirty=true
- **文件 2**: `src/views/ObjectDetailPage.vue`
  - line 295-301: `handleBeforeUnload` + `window.addEventListener('beforeunload', ...)`
  - line 314-316: `onUnmounted` 加 `removeEventListener`
  - line 213-217: `handleSaved` 加 `dirty.value = false` 重置

**潜在风险**:
- 修改字段时触发 dirty=true, 之前不触发 → tab 关闭时弹"有未保存的修改"可能影响现有 E2E
- beforeunload 监听可能影响浏览器关闭行为 (但仅在 dirty=true 时)
- 保存后重置 dirty → E2E 中保存后立即关闭的流程可能改变行为

### 2. DIM 路由迁移
- **文件**: `meta/api/management_dimension_api.py`
  - line 37: `url_prefix` 从 `/api/v1/management-dimensions` → `/api/v2/bo/management_dimension`
  - 作用: 旧 v1 端点继续返回 410 (migrated_to), v2 端点现在 200 OK (需重启 dev server)

**潜在风险**:
- 重启 dev server 加载新代码, 服务可能短暂不可用
- 已迁移的 v1 客户端可能受影响 (但前端代码未改, 仍走 v1 → 410)

## 任务清单

### 1. 重启 dev server (前置条件)

```bash
cd d:\filework\excel-to-diagram
powershell -File scripts/service_manager.ps1 restart
```

**验证**:
```bash
# 等 3 秒后
python -c "import urllib.request; r = urllib.request.urlopen('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5); print('login:', r.status)"
# 期望: 200

# 测试 DIM 路由迁移
python -c "
import urllib.request, http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
r = opener.open('http://localhost:3010/api/v2/bo/management_dimension?page_size=3')
print('v2 dim:', r.status, r.read().decode()[:200])
"
# 期望: 200 + 实际数据
```

### 2. 跑 BMRD 8 个 spec (先小范围验证)

```bash
cd d:\filework\excel-to-diagram
npx playwright test e2e/business-flow/protection-rules.spec.js e2e/business-flow/crud-lifecycle-rules.spec.js e2e/business-flow/audit-i18n-fk-rules.spec.js e2e/business-flow/permission-security-rules.spec.js e2e/business-flow/advanced-module-rules.spec.js e2e/business-flow/data-permission-dimension-rules.spec.js e2e/business-flow/masterdata-schema-workflow-rules.spec.js e2e/business-flow/bug-regression.spec.js --reporter=list
```

**期望结果** (基于 2026-06-14 基线):
- ~105 测试, ~80 passed + ~25 skipped + 0 failed
- 耗时 ~2.8 分钟

**如果失败**:
- 记录失败测试 ID + 错误信息
- 单独跑该测试看是否可重现: `npx playwright test <spec.js>:<line> --reporter=list`
- 报告根因 (前端代码改动? dev server? 测试代码过时?)

### 3. 跑 features/ 全部 spec (回归核心)

```bash
# 列出所有 features/
ls d:\filework\excel-to-diagram\e2e\features\*.spec.js
```

```bash
# 跑 features 全部
npx playwright test e2e/features/ --reporter=list
```

**期望**: ~150+ 测试, 绝大部分 passed

**如果失败**:
- 优先检查 E21 相关 (含 `field-update`, `close`, `cancel` 的测试)
- 检查 ObjectPage 相关 (含 `object-page`, `ObjectPageField` 的测试)
- 检查 tab 关闭相关 (含 `tab-close`, `navigate-away` 的测试)

### 4. 跑全部 e2e/ 套件 (最终回归)

```bash
# 包括 features/ + business-flow/
npx playwright test e2e/ --reporter=list
```

**期望**: ~270+ 测试, 绝大部分 passed

**如果失败**:
- 区分两类:
  - **回归 (regression)**: 之前 pass, 现在 fail → 必须修
  - **不稳定 (flaky)**: 重跑 1-2 次, 大部分 pass → 记录, 不必立刻修
- 用 `--retries=2` 重跑, 排除并发假失败

## 报告格式

完成后请用以下格式汇报:

```
## E2E 回归验证报告

### 1. 重启验证
- 重启状态: [OK / FAIL]
- DIM 路由迁移: [v2 200 / v2 仍 400 / 需手动]
- 备注:

### 2. BMRD 8 spec 验证
- 测试数: X
- passed: X (X%)
- skipped: X
- failed: X
- 失败明细: (id + 错误)

### 3. features/ 验证
- 测试数: X
- passed: X
- failed: X
- 失败明细:

### 4. 全量 e2e/ 验证
- 测试数: X
- passed: X
- failed: X
- 回归 vs 不稳定 区分:

### 5. 关键发现
- (列出值得注意的发现)
- (E21 行为变化是否影响业务?)
- (DIM 路由是否对前端调用有影响?)

### 6. 修复建议
- (如有回归, 给具体修复方案)
- (代码回滚? 前端适配? 测试更新?)
```

## 注意事项

1. **BMRD 框架不需运行** - 它只是测试生成器, 跑 E2E 不需要先生成
2. **dev server 重启** - DIM 路由代码改动必须重启才能生效
3. **保存后 dirty 重置** - E2E 中保存后关闭 tab 的流程, 弹窗应该不再触发
4. **beforeunload 监听** - 浏览器关闭时如果 dirty=true 会弹原生提示
5. **失败可接受** - 一些 flaky 测试是历史遗留, 不必立刻修, 记录即可

## 联系人 (遇到问题)

如发现 E21 改动导致关键业务流失败, 记录:
- 测试 ID + 完整错误堆栈
- 复现步骤 (打开哪个页面, 改了什么, 关闭 tab 是否弹窗)
- 建议回滚 / 修复 / 接受

主 Agent 收到报告后会评估。
