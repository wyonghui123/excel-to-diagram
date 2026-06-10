# AA图导航 + 数据流问题复盘（2026-06-10）

## TL;DR

本次修复涵盖了 **6 个相互独立又相互关联的 bug**，涉及路由导航、sessionStorage 数据传递、init hook 调用、mermaid 渲染、annotation panel 等。最终用户体验：**架构数据管理 → 选 "采购管理" + "所有关系" → 点 "展示图表" → 3 步骤导航 → 25 BO + 28 关系渲染**。

修复耗时 ~3 小时。**核心反思：高频反复改动 mermaid layout + 没做足测试隔离是最大的返工原因**。

---

## 修复时间线（按 v 版本）

### v1-v3：路由迁移 + 全局修复（用户已确认这部分已 OK）

### v20：`mermaid-container` 高度修复（保留）
- `.mermaid-container { height: 100% }` 让 annotation panel 可见
- 这是**唯一对 mermaid layout 的合法改动**

### v21：tooltip 全屏移动（保留）
- `fullscreenchange` 时把 `#mermaid-tooltip` 移入 `mermaidContainerEl`
- 解决"全屏时 tooltip 被 top layer 遮挡"

### v22：node label 格式 + fixNodeRectSize（**已回退**）

修改：
- node label: `${name}<br/>(${code})` → `${name} · (${code})`
- `wrappingWidth: 200 → 1000`
- 加 `fixNodeRectSize`：用 `div.scrollWidth` 算内容宽度，强制 `rect/foreignObject` 同步

**回退原因**：用户反馈"节点文字超出右边 + 连线端点错位"。根因：`fixNodeRectSize` 改 `rect` 宽度但 mermaid ELK layout 内部 endpoint 计算基于原 rect，端点位置不对齐。**这种 JS 干预 mermaid 内部 layout 产物的方案不可取**。

教训：**mermaid layout 问题优先用其自身配置（nodeWidth / wrappingWidth / htmlLabels）调参，不要在 processSvg 后 JS 改 rect/foreignObject**。

### v23：annotation panel 修复
- 根因：`chartType.value || 'businessObject'`（空字符串 fallback 缺失）
- 解决 line 148 fallback

### v24：onMounted 双重调用 + 同名函数误判

**修复了两次**（先误判后纠正）：

**第一次误判**（v23 末尾）：
- 我看到 `AADiagramApp/index.vue:303` 调用 `initFromArchDataManager()` 无参
- 推断这是 useDiagramData 的 `initFromArchDataManager(archData)`（被重命名为 `initDataFromArch`）
- 认为无参调用导致 `archData=undefined` 解构抛 TypeError
- **错误地删了 line 303**

**真相**（v24 纠正）：
- `useDiagramSteps.js:36` 也有同名 `initFromArchDataManager()`（切 3 步骤模式，无参正确）
- `useDiagramData.js:1584` 的同名函数（被 line 98 重命名为 `initDataFromArch`，带参加载数据）
- line 60 解构 `initFromArchDataManager` from `useDiagramSteps()`
- line 98 解构 `initFromArchDataManager: initDataFromArch` from `useDiagramData()`
- 两个函数 **完全不同的来源**，各自有用
- 删 line 303 导致 3 步骤模式没切 → 用户看到 6 步骤导航

**第二次正确修复**：恢复 line 303 调 useDiagramSteps 版本（无参 = 步骤模式切换），保留 line 304 调 useDiagramData 版本（带参 = 数据加载）。

教训：**同名函数必须先查引用源头，不能凭"看起来参数对不上"推断**。应该 grep `function initFromArchDataManager` 看有几个定义。

### v24.1：PowerShell mojibake 注释吞代码（2 处）

之前用 PowerShell `-replace '<br/>', ' · '` 批量修改 `useBusinessObjectSyntax.js`，PowerShell 在 UTF-8 ↔ UTF-16 转换时把**几处原本正常的换行符（`\n`）破坏了**，导致：

**Bug 1**：`isGroupEnabled` 未定义
```js
// 修复前 (mojibake):
// 清除 directNodes �?containers，避免后续生成子�?    const isGroupEnabled = group.enabled !== false
// ↑ 注释吞掉了 const isGroupEnabled = ...，整个表达式被注释掉

// 修复后:
const isGroupEnabled = group.enabled !== false
// 如果分组被禁用，不创建 virtualContainer
```

**Bug 2**：`linkSourceCode` 未定义
```js
// 修复前 (mojibake):
// 判断源和目标是否在中心范�?            const linkSourceCode = link.sourceCode || link.sourceName
// ↑ 注释吞掉了 const linkSourceCode，mermaid 渲染中断 → 0 个 edge

// 修复后:
// 判断源和目标是否在中心范围内
const linkSourceCode = link.sourceCode || link.sourceName
```

**修复路径**：用 Edit 工具精确替换，绕开 PowerShell 编码。

教训：**绝对禁止 PowerShell `-replace` 编辑中文混 UTF-8 文件**。已有 `.trae/rules/powershell-rules.md` 规则说明这一点。

### v25：`convertToRelationNodeIds` null check 缺失

```js
// 修复前:
} else if (typeof filter === 'object' && filter.id) {  // null.id → TypeError
  nodeIds.push(filter.id)
}

// 修复后:
} else if (filter && typeof filter === 'object' && filter.id) {
  nodeIds.push(filter.id)
}
```

`typeof null === 'object'` —— null 进入这个分支读 `filter.id` 抛错。

教训：**所有 `typeof x === 'object'` 检查都必须先做 null guard**（`x && typeof x === 'object'`）。

---

## 反思：高频反复改动是最大返工原因

### 重复劳动清单

| 改动 | 用户反馈 | 回退/修复 | 耗时 |
|------|---------|---------|------|
| v22 fixNodeRectSize | 端点错位 | 完全回退 | ~30min |
| v23 删 line 303 initFromArchDataManager | 仍 6 步骤 | 恢复 | ~15min |
| v24 PowerShell mojibake 1 | isGroupEnabled | 修注释 | ~15min |
| v24 PowerShell mojibake 2 | linkSourceCode | 修注释 | ~15min |
| v25 null check | TypeError | 加 guard | ~10min |

**5 次重复劳动** = 约 85 分钟。如果一开始**做足单元测试**（每个改动用 5 行 Playwright 测试验证），大部分问题能在第一轮就发现。

### 根因分析

1. **没意识到 mermaid11 ELK layout 是黑盒**：fixNodeRectSize 改了 rect 但 endpoint 位置不知道，**改动 mermaid 内部产物是高风险行为**。
2. **同名函数陷阱**：useDiagramSteps 和 useDiagramData 都有 `initFromArchDataManager`，命名空间混乱。
3. **PowerShell 编码陷阱**：跨 shell 工具链的中文处理不稳定，应统一用 Edit 工具。
4. **测试覆盖不足**：每次只测"是否抛错"，没测"最终输出是否对"。
5. **修改注释的连锁反应**：之前批量 `-replace '<br/>'` 顺带破坏了无关注释，下次类似操作要用 Edit 工具按行修改。

---

## 改进建议（给未来类似任务）

### 1. 严格遵守 mermaid 边界
- ✅ 用 mermaid 配置（nodeWidth / wrappingWidth / htmlLabels）调 layout
- ❌ 不在 processSvg 后 JS 改 rect/foreignObject/svg attribute
- ❌ 不改 mermaid.config 内部 layout 算法的产物

### 2. 同名函数必须查源头
- 看到 `initFromArchDataManager()` 不要假设是哪个模块的
- 先 `Grep -n "function initFromArchDataManager"` 看定义数量
- 然后看 line X 解构来源：`const X = useDiagramY()` 后才能确定

### 3. 禁止 PowerShell `-replace` 编辑源代码
- 所有源码改动用 **Edit 工具精确替换**
- 批量改动（如 `<br/>` → ` · `）用 Edit 工具**逐行替换**
- 中文混 UTF-8 文件尤其要避免 PowerShell 编码转换

### 4. 测试模式
- 每次修改 5 行代码 → 写 30 行 Playwright 测试验证
- 测试应该断言**最终输出**（linkCount > 0, panel visible），不是只断言"不抛错"
- 浏览器资源耗尽（ERR_INSUFFICIENT_RESOURCES）→ 清理 playwright/chrome 进程

### 5. 工具选择
- **navigation 测试**：用 Playwright 完整模拟 SPA 流程（navigate → reload → 走步骤 → 看 output）
- **data flow 诊断**：往 `window.__diagramApp` 暴露诊断字段（centerScope, relationFilteredBoCodes 等）
- **不抛错的 silent bug**：console 加 `[generateDiagram] filteredRelations=X filteredRelationships=Y` log

---

## 相关文件清单

| 文件 | 作用 | 关键修复 |
|------|------|---------|
| [src/views/AADiagramApp/index.vue:295-319](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/index.vue#L295-L319) | onMounted sessionStorage 初始化 | 恢复 initFromArchDataManager() + initDataFromArch(archData) |
| [src/views/AADiagramApp/composables/useDiagramSteps.js:36-39](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramSteps.js#L36-L39) | 切 3 步骤模式 | initFromArchDataManager() |
| [src/views/AADiagramApp/composables/useDiagramData.js:1584-1687](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramData.js#L1584-L1687) | 从 archData 加载数据 | initFromArchDataManager(archData) |
| [src/services/archDataConverter.js:205-225](file:///d:/filework/excel-to-diagram/src/services/archDataConverter.js#L205-L225) | 关系类型 filter 转换 | 加 null check |
| [src/composables/useMermaid/syntax/useBusinessObjectSyntax.js:864-868](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBusinessObjectSyntax.js#L864-L868) | node label 文字处理 | 修复 mojibake 注释 |
| [src/composables/useMermaid/syntax/useBusinessObjectSyntax.js:258](file:///d:/filework/excel-to-diagram/src/composables/useMermaid/syntax/useBusinessObjectSyntax.js#L258) | group 启用判断 | 修复 mojibake 注释 |
| [src/views/AADiagramApp/index.vue:148](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/index.vue#L148) | chartType fallback | `chartType: chartType.value || 'businessObject'` |
| [src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue:309-310](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L309-L310) | 架构管理 chart action | sessionStorage.setItem + router.push |

---

## 后续 TODO

- [ ] 拆分 useDiagramSteps 和 useDiagramData 的同名 `initFromArchDataManager`，改名为 `switchToArchMode()` 和 `loadArchData()`
- [ ] 给 `__diagramApp` 暴露诊断字段标准化（relationFilteredBoCodes, centerScope, selectedRelationNodeIds）
- [ ] 把 `useBusinessObjectSyntax.js` 的 `\\n`/`◆`/`centerMark` 等修复回归测试加到 e2e/features/mermaid-drag.spec.js