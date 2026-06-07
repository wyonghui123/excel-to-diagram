# Mermaid Direction 配置规范

## 重要提醒
请务必遵守以下规范，不要再弄错！

## 方向值含义

| Mermaid Direction | 含义 | 视觉表现 |
|-------------------|------|----------|
| `LR` | Left → Right（从左到右） | 分组之间**垂直排列**（上下排列） |
| `TB` | Top → Bottom（从上到下） | 分组之间**水平排列**（左右排列） |

## 常见误区
- ❌ 错误认为 `LR` = 水平排列
- ❌ 错误认为 `TB` = 垂直排列

## 正确理解
- `LR`：先画左边，再画右边 → 分组在垂直方向上依次排列（想象一列竖着的卡片）
- `TB`：先画上边，再画下边 → 分组在水平方向上依次排列（想象一行横着的卡片）

## UI 按钮映射（LayoutSelector.vue）

```javascript
// 垂直排列按钮 → LR
:class="{ active: overallDirection === 'LR' }"
@click="updateOverallDirection('LR')"

// 水平排列按钮 → TB
:class="{ active: overallDirection === 'TB' }"
@click="updateOverallDirection('TB')"
```

## 代码位置
- `src/views/AADiagramApp/components/LayoutSelector.vue`
- `src/composables/useMermaid/syntax/useServiceModuleSyntax.js`

## 修改历史
- 2026-04-20：修正按钮值映射，垂直->LR，水平->TB（颠倒之前的错误映射）
