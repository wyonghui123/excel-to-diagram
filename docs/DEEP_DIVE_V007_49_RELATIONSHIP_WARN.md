# V007.49 BO 图关系数量告警 (财务云 600+ 节点延伸思考)

> **日期**: 2026-07-09 18:00
> **作者**: V007.45 dev-agent (V007.49 P0 实施)
> **触发**: 用户在 V007.48 mermaid syntax 修复后, 进一步提出: "如果关系数量超过 100, 业务对象图最好能展示告警提示"
> **结论**: useDiagramData.js BO 图入口加 `warnTooManyRelationships()` → ElNotification 右下角通知 (阈值 100, wasAbove/isAbove 状态机防重复)

---

## 用户诉求

> "如果关系数量超过 100, 如果选择的是业务对象图, 在展示图表第一步这里最好能够展示这个告警提示: 关系数量多, 建议缩小对象和关系范围, 或采用服务模块图"

**触发场景** (用户已实测):
- 财务云 1610 BO + 范围内与外部关系 (199 BO + 689 关系) → 浏览器卡顿
- mermaid 11.13 渲染 600+ 节点 + 关系极慢

---

## 设计决策 (3 个问题 + 用户选择)

| 问题 | 选项 | 决策 |
|------|------|------|
| 告警形式 | ElMessage / ElNotification / 黄色警示条 / 模态 | **ElNotification 右下角** |
| 阈值配置 | 硬编码 / 后端配置 / 用户偏好 | **硬编码常量 100** |
| 跳转按钮 | 文字 / 切换按钮 / 切换+继续 | **只展示文字建议** (不增加复杂度) |

---

## V007.49 P0 实施

### 1. module-level 常量 + 状态机 (useDiagramData.js L48-49)

```js
const RELATIONSHIP_WARN_THRESHOLD = 100
let _lastWarnedKey = null  // 'bo:above' or null
```

### 2. `warnTooManyRelationships` 函数 (L51-92)

```js
function warnTooManyRelationships(count, chartType) {
  // 只在 BO 图告警
  if (chartType !== 'businessObject') return
  // [V007.49 P0 修复] 防重复告警状态机
  // 关键: 已在 above 状态 (数量 > threshold) 就不再告警
  // 即使 count 不同 (200 vs 300) 也不重复, 因为用户已看到告警
  const isAbove = count > RELATIONSHIP_WARN_THRESHOLD
  const wasAbove = _lastWarnedKey === 'bo:above'
  if (wasAbove && isAbove) {
    // 已经在 above 状态, 数量变化 (200→300) 不重复告警
    return
  }
  if (!isAbove) {
    // 数量回到阈值下, 重置状态允许下次再告警
    if (wasAbove) {
      _lastWarnedKey = null
    }
    return
  }
  // 第一次越过阈值 (≤100 → >100), 告警
  _lastWarnedKey = 'bo:above'
  ElNotification({
    title: '业务对象图关系数量过多',
    message: `当前关系数量 ${count} 条, 超过推荐阈值 ${RELATIONSHIP_WARN_THRESHOLD} 条, 可能影响图表加载和渲染性能。建议缩小对象和关系范围, 或采用服务模块图查看整体结构。`,
    type: 'warning',
    duration: 8000,
    position: 'bottom-right',
    showClose: true,
  })
}
```

### 3. 在 BO 图入口调用 (L1700)

```js
} else {
  // 业务对象图
  // [V007.49 P0 2026-07-09] 关系数量告警 (财务云 600+ BO 节点)
  //   finalRelationships 包含所有 active 关系 (filteredRelationships + internalRelationFilter)
  //   超过 100 触发右下角 ElNotification 建议
  warnTooManyRelationships(finalRelationships.length, 'businessObject')

  const useLegacy = diagramConfig.value.useLegacyGroupControl
  ...
}
```

### 4. import ElNotification (L2)

```js
import { ElNotification } from 'element-plus'
```

---

## 状态机设计 (wasAbove/isAbove)

**`module-level _lastWarnedKey` 状态机**:

| 状态转换 | 行为 |
|---------|------|
| null + count=50 (below) | 不告警, key=null |
| null + count=200 (above) | **告警**, key='bo:above' |
| 'bo:above' + count=300 | **不告警** (用户已看到) |
| 'bo:above' + count=400 | **不告警** |
| 'bo:above' + count=80 (below) | **不告警**, **重置 key=null** |
| null + count=150 (above) | **告警** (再次越阈值) |
| any + SM 图 (200 关系) | **不告警** (只 BO 图告警) |

---

## 状态机单测 (test_v007_49_warn_dedup.mjs)

11 个测试场景全 PASS:

```
✅ 1. 初始: 50 关系 (≤100)             notify=false, key=null
🔔 2. 增加到 200 关系 (>100)           notify=true,  key=bo:above
✅ 3. 200→300 (仍在 above)             notify=false, key=bo:above
✅ 4. 300→400 (仍在 above)             notify=false, key=bo:above
✅ 5. 400→80 (回到 below)              notify=false, key=null
🔔 6. 80→150 (再次越阈值)              notify=true,  key=bo:above
✅ 7. SM 图 200 关系 (不告警)           notify=false, key=bo:above
✅ 8. BO 图 100 关系 (边界 ≤) → reset  notify=false, key=null
🔔 9. BO 图 101 关系 (越阈值) → 告警   notify=true,  key=bo:above
✅ 10. 101→50 (重置)                   notify=false, key=null
🔔 11. 50→250 (越阈值)                 notify=true,  key=bo:above

总 ElNotification 调用次数: 4
```

**关键边界**:
- **count=100 (边界 ≤)**: 不告警, 但**重置** key 让下次能告警
- **count=101 (边界 >)**: 告警

---

## V8w~V8af 10/10 PASS

```
PASSED (10):
  + V8w: safe_connect.py _open_safe_connection 含 mmap_size=0
  + V8x: server.py _cleanup_resources 含 _cleanup_done 幂等守卫
  + V8y: query_service._apply_data_permission except 含 id=-1 拒绝
  + V8z: 3 文件 7 处裸连接全部改用 safe_connect_for_read
  + V8aa: import_export_service._flatten 含 leaf_op 参数
  + V8ab: 4 查询方法全部含 _apply_data_permission 调用
  + V8ac: db_health_monitor 2 处 + async_audit_writer 降级路径全部加固
  + V8ad: 4 个 db-level PRAGMA 全部有幂等保护
  + V8ae: mermaid 11.13 label 严格转义 (sanitizeMermaidLabel)
  + V8af (新): BO 图关系数量告警 (ElNotification + 阈值 100 + wasAbove/isAbove 防重复)
```

V8af 验证项:
- useDiagramData.js 包含 `ElNotification` + `from 'element-plus'`
- `RELATIONSHIP_WARN_THRESHOLD` 常量 = 100
- `warnTooManyRelationships` 函数存在
- BO 图入口调 `warnTooManyRelationships(finalRelationships.length, ...)`
- `_lastWarnedKey` 状态变量存在
- `wasAbove` + `isAbove` 状态机判断存在

---

## 涉及文件

| 文件 | 修改 |
|------|------|
| `src/views/AADiagramApp/composables/useDiagramData.js` | L2 import + L31-92 函数 + L1700 调用 |
| `tools/verify_v007_46_ioerror_recovery.py` | V8af invariant |
| `tools/test_v007_49_warn_dedup.mjs` | 状态机单测 (11 场景) |
| `docs/DEEP_DIVE_V007_49_RELATIONSHIP_WARN.md` | 本报告 |

---

## 部署后回归

- 选财务云 + 范围内与外部 (689 关系) → BO 图渲染时**右下角 ElNotification 弹出** "业务对象图关系数量过多 (689), 建议缩小..."
- 用户关掉告警后, 调整范围 (回到 50 关系) → 再选 200 关系 → **再次告警** (状态重置)
- 切到服务模块图 → **不告警** (chartType !== businessObject)
- 选 100 关系 (边界) → 不告警, 101 关系 → 告警

---

## 反思 (V007.45 → V007.49)

| 错误 | 反思 |
|------|------|
| 初版用 key = `bo:above:count` (含 count) → 200/300 会重复告警 | **状态机 key 不应含"不断变化的值"**, 只存"状态本身" (bo:above / null) |
| 用 `_lastWarnedKey` 全局变量 | module-level, OK, 简单可靠 |
| 边界 100/101 行为不对称 | **dev-agent 必须**测试**边界值**, 不能只测 200/300 |
| 用 eval 测试 module-level 函数 | **eval 闭包陷阱**: 局部变量不更新 globalThis, 用 getter 函数 |

---

**作者**: V007.45 dev-agent (V007.49 P0)
**报告时间**: 2026-07-09 18:10
**下一步**: 部署智能体按"部署后回归"步骤验证
