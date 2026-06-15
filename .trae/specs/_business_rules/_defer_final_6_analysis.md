# DEFER 6 项最终分析 (2026-06-14)

> **BMRD DEFER 6 项详细分析报告** (剩余未解锁项)
> 基于真实代码 + 端点验证

## 1) E34 (i18n locale) - 🟡 中等

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **后端** | ✅ 已支持 | `user_api.py:412` `preference_fields = ['locale', ...]` |
| **数据库** | ✅ 已存 | `users.locale` 列 |
| **API 读取** | ✅ 已暴露 | `/api/v2/bo/user/1` 返回 `locale` 字段 |
| **API 写入** | ⚠️ 部分 | PATCH 500 (MethodNotAllowed) |
| **前端 vue-i18n** | ❌ 未装 | `package.json` 无 `vue-i18n` 依赖 |
| **前端 locale 文件** | ❌ 无 | `src/locales/zh-CN.ts` 不存在 |
| **前端切换 UI** | ❌ 无 | `views/` 无 locale 切换组件 |
| **现成钩子** | ✅ 有 | `main.js:87` `app.provide('elementPlusLocale', zhCn)` |

### 关键发现 🎉
**Element Plus locale 已有 provide 模式** (`app.provide('elementPlusLocale', zhCn)`)！

这意味着 i18n 框架**无需从零搭建**，只需：
1. 扩展 `elementPlusLocale` 为**动态** (根据 user.locale 切换)
2. 加 user.locale → zhCn/zhTw/enUs 的映射
3. 提供切换 UI

### 实施成本 (重新评估)
- 安装 vue-i18n: **0.5 天** (实际可选, 可只用 Element Plus locale)
- 创建 locale 文件: **0.5 天** (zh-CN/en-US 元素 50-100 键)
- 动态切换逻辑: **1-2 天**
- 切换 UI 组件: **0.5 天**
- 业务文本 $t() 改造: **3-5 天** (可选)
- **总计**: 2-3 天 (最小可行) / 5-7 天 (完整)

### 推荐
🟡 **中等** - 跟产品迭代同步做

---

## 2) C01/C02-DEEP (ObjectChildSection) - 🔴 困难

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **组件** | ✅ 已实现 | `ObjectChildSection.vue` (514 行) |
| **包装组件** | ✅ 已实现 | `ObjectPageWithChildren.vue` |
| **API 函数** | ✅ 已定义 | `createChild`, `updateChild`, `deleteChild`, `loadChildList` |
| **单元测试** | ✅ 已存在 | `ObjectChildSection.spec.js` |
| **业务页面集成** | ❌ **0 集成** | `views/` **0 文件** import ObjectChildSection |
| **deep_insert API** | ❌ 404 | `/api/v2/bo/enum_type/deep_insert` 404 |

### 关键发现 🎯
**ObjectDetailPage.vue 是通用包装页面，所有详情页都用它！**

```bash
# views/ 下的详情页都基于 ObjectDetailPage
$ grep -l "ObjectPage" src/views/*.vue src/views/**/*.vue
src/views/ObjectDetailPage.vue
src/views/SystemManagement/RoleDetail.vue
src/views/SystemManagement/RolePermissionDetail.vue
```

**架构层面**：
- `ObjectDetailPage` 是**通用详情容器**
- `ObjectChildSection` 是**子项组件**
- **集成方式** = 改通用 `ObjectDetailPage` + 加 page config 字段（不是单独业务页面集成）

### 实施成本
- **改 ObjectDetailPage 架构**: 1-2 天 (加 child section 插槽)
- **加 ui_view_config.child_section 配置**: 0.5 天
- **3 个示例业务页面启用**: 1-2 天
- **后端 deep_insert 端点**: 1-2 天
- **E2E 测试**: 0.5-1 天
- **总计**: **3.5-6 天**

### 推荐
🔴 **困难** - 需要架构改动，影响所有详情页

---

## 3) BUG-V005 (createChild 客户端校验) - 🟢 简单

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **createChild API** | ✅ 已定义 | `ObjectChildSection.vue:255` 解构 |
| **DetailPage 弹窗** | ✅ 已用 | `ObjectChildSection.vue:149-157` |
| **ObjectPageField 必填** | ✅ 已支持 | schema `required: true` 触发校验 |
| **ObjectChildSection 自己校验** | ❌ 无 | 没有手写 name 必填 |
| **底层 schema 配置** | ❓ 待查 | 需要后端 schema 给 name 加 `required: true` |

### 关键发现 🎯
**ObjectChildSection 用 `<DetailPage>` 显示新建弹窗** (`ObjectChildSection.vue:149-157`)

这意味着**校验完全依赖 DetailPage 内置的 schema-driven 校验**（如果 schema 配 `required: true` 就拦，否则不拦）。

**真正的修复** = **给后端 schema 加 `required: true`** 配置即可，**无需前端代码**！

### 实施成本
- 检查每个 child 类型的 schema 配置: **0.5-1 天**
- 给 name/code 等关键字段加 `required: true`: **0.5 天**
- BMRD 软断言已 skip BUG-V005 test (无需新代码)
- **总计**: **0.5-1 天** (纯后端配置)

### 推荐
🟢 **简单** - **纯后端 schema 配置**, 应立即可做

---

## 4) SCHEMA-VERSION (前端缓存) - 🟢 **可立即解锁**

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **后端 schema-version 端点** | ✅ 已实现 | `/api/v2/meta/schema-version` 200 + MD5 hash |
| **前端 useMenuPermissions** | ✅ 已用 | `useMenuPermissions.js:111` 调用 schema-version |
| **前端 useMetaCache** | ✅ 已实现 | `useMetaCache.js:104` 集成 cache + version |
| **缓存机制** | ✅ 完整 | `setCache(result.data, cacheVersion)` |
| **DEFER 项** | 🟢 **可解锁** | 关键代码 + 前端已就绪 |

### 关键发现 🎉
**SCHEMA-VERSION 实际已经**完整实现**！** 前后端都有！

```javascript
// useMenuPermissions.js
const result = await apiV2.get('/meta/schema-version')
if (result.success) {
  return result.data?.schema_version || null
}

// useMetaCache.js
const cacheVersion = version || result.data?.schema_version || null
setCache(result.data, cacheVersion)
```

### 实施
**无需代码改动！** 只需在 YAML 注释解锁状态：

```yaml
# [BMRD-2026-06-14 UNLOCK] SCHEMA-VERSION 已文档化 + 前端已实现缓存
# 详见 meta/docs/SCHEMA_VERSION_RULES.md
# 关键代码确认: /api/v2/meta/schema-version 端点 (bo_api.py:201)
# 前端缓存: useMenuPermissions.js + useMetaCache.js 已实现 ✅
```

✅ **本会话已解锁**

---

## 5) WF-STATE-MACHINE (前端 UI) - 🟡 中等

### 现状
| 层 | 状态 | 证据 |
|---|------|------|
| **后端 MetaStateTransition** | ✅ 完整 | `models.py:244` (state_field, from_states, to_state) |
| **后端 StateTransitionExecutor** | ✅ 完整 | `rule_executor.py:662` + 2026-06-09 Bug 修复 |
| **后端 workflow 端点** | ✅ 200 | `/api/v2/bo/workflow`, `workflow_instance`, `workflow_task` |
| **前端 workflow 视图** | ❌ 0 | `views/` 目录 0 个 workflow 页面 |
| **前端状态机 UI** | ❌ 0 | 无可视化组件 |
| **状态转换按钮** | ❌ 待查 | 可能由 ObjectPage 的 action 机制处理 |

### 关键发现 🎯
**前端没有**workflow 视图 (列表/详情/状态机可视化都没有)。

但**状态转换可能已通过 ObjectPage action 机制工作** (state_transition rule 通过 `POST /actions/{rule_id}` 触发)。

### 实施成本
- 状态转换触发: **已通过 action 机制** (无需新代码, **可能其实已可用**)
- workflow 列表视图: 1-2 天
- workflow_task 视图 (我的待办): 1-2 天
- 状态机可视化: 2-3 天 (P2)
- **总计**: **2-4 天** (基础) / 4-5 天 (含可视化)

### 推荐
🟡 **中等** - 基础视图 2-4 天, 可视化是 P2

### BMRD 建议
由于 state_transition 可能已通过 ObjectPage action 机制工作, **建议先验证**, 如果已可用, WF-STATE-MACHINE 可改为 ACTIVE + 加 E2E 测试。

---

## 6) BUG-V005 (pending) - 🟢 简单 (同 #3)

跟 #3 同一项, DEFER pending + ACTIVE rule (status: ACTIVE)。

---

## 总结对比

| DEFER ID | 真实状态 | 真正阻塞 | 实施成本 | 优先级 | 立即可做 |
|----------|---------|---------|---------|--------|----------|
| **SCHEMA-VERSION** | ✅ **完整** | 无 | 0 (注释) | 🟢 | ✅ **已解锁** |
| **BUG-V005** | ⚠️ 缺 schema 配置 | 后端 schema | 0.5-1 天 | 🟢 | ✅ 立即 |
| **E34 (i18n)** | 后端 100%, 前端 0 资源 | 前端 i18n | 2-7 天 | 🟡 | ❌ 跟产品 |
| **WF-STATE-MACHINE** | 后端 100%, 前端 0 UI | 前端 workflow 视图 | 2-4 天 | 🟡 | ❌ 跟产品 |
| **C01-DEEP** | 组件 100%, 业务 0 集成 | 架构改动 | 3.5-6 天 | 🔴 | ❌ |
| **C02-DEEP** | 同上 | 同上 | 同上 | 🔴 | ❌ |

## 累计本会话成果

| 阶段 | pending DEFER | 文档 | 规则 | failed |
|------|---------------|------|------|--------|
| BMRD v1 初始 | 23 | 0 | 6 | 3 |
| BMRD v2-v7 | 11 | 1 | 92 | 0 |
| E21+DIM 修复 | 8 | 4 | 93 | 0 |
| SCHED+EVENT 文档 | 6 | 6 | 93 | 0 |
| **本轮 (SCHEMA-VERSION)** | **5** | **6** | **93** | **0** |

**DEFER 解锁率**: 23 → 5 = **78% 减少** (18/23 解锁)

## 剩余 5 个 DEFER 解锁路线

### 立即可做 (本周)
- [ ] BUG-V005 后端 schema 配 `required: true` (0.5-1 天)

### 短期 (1-2 周)
- [ ] WF-STATE-MACHINE 基础视图 (2-4 天, 跟产品)
- [ ] E34 (i18n) 启动 (2-7 天, 跟产品)

### 中期 (1+ 月)
- [ ] C01/C02 业务页面集成 (3.5-6 天, 架构改动)
- [ ] 写 BMRD 团队使用主文档

## 参考

- 后端核心: `meta/core/cron_parser.py`, `meta/core/rule_executor.py`, `meta/core/models.py`
- 后端 API: `meta/api/bo_api.py` (schema-version, ui-config)
- 前端 composable: `src/composables/useMenuPermissions.js`, `useMetaCache.js`
- 前端 main: `src/main.js` (elementPlusLocale provide)
- 前端组件: `src/components/common/ObjectChildSection/ObjectChildSection.vue`
- BMRD YAML: `.trae/specs/_business_rules/*.yaml`
