# 用友YonDesign设计系统规范

> **版本**: v1.0
> **基于**: 用友企业级设计系统 YonDesign
> **参考**: https://yondesign.yonyoucloud.com/

---

## 1. 颜色系统 (来自YonDesign官网)

YonDesign提供了完整的颜色体系，包括：

### 1.1 Orange 橙色系 (主色调)

| 色阶 | 色值 | 用途 |
|------|------|------|
| Orange-50 | `#fff7ed` | 极浅背景 |
| Orange-100 | `#ffedd5` | 浅色背景 |
| Orange-200 | `#fed7aa` | 禁用状态背景 |
| Orange-300 | `#fdba74` | 悬停背景 |
| Orange-400 | `#fb923c` | 高亮 |
| Orange-500 | `#f97316` | 强调 |
| **Orange-600** | `#ea580c` | **主色 Primary** |
| Orange-700 | `#c2410c` | 激活/按下 |
| Orange-800 | `#9a3412` | 深色强调 |
| Orange-900 | `#7c2d12` | 最深色 |

**CSS变量**:
```css
--color-primary: var(--yonyou-orange-600);        /* #ea580c */
--color-primary-hover: var(--yonyou-orange-500);  /* #f97316 */
--color-primary-active: var(--yonyou-orange-700); /* #c2410c */
```

### 1.2 Amber 琥珀色

| 色阶 | 色值 |
|------|------|
| Amber-50 | `#fffbeb` |
| Amber-100 | `#fef3c7` |
| Amber-200 | `#fde68a` |
| Amber-300 | `#fcd34d` |
| Amber-400 | `#fbbf24` |
| **Amber-500** | `#f59e0b` |
| Amber-600 | `#d97706` |
| Amber-700 | `#b45309` |
| Amber-800 | `#92400e` |
| Amber-900 | `#78350f` |

### 1.3 Yellow 黄色

| 色阶 | 色值 |
|------|------|
| Yellow-50 | `#fefce8` |
| Yellow-100 | `#fef9c3` |
| Yellow-200 | `#fef08a` |
| Yellow-300 | `#fde047` |
| Yellow-400 | `#facc15` |
| **Yellow-500** | `#eab308` |
| Yellow-600 | `#ca8a04` |
| Yellow-700 | `#a16207` |
| Yellow-800 | `#854d0e` |
| Yellow-900 | `#713f12` |

### 1.4 Lime 青柠色

| 色阶 | 色值 |
|------|------|
| Lime-50 | `#f7fee7` |
| Lime-100 | `#ecfccb` |
| Lime-200 | `#d9f99d` |
| Lime-300 | `#bef264` |
| Lime-400 | `#a3e635` |
| **Lime-500** | `#84cc16` |
| Lime-600 | `#65a30d` |
| Lime-700 | `#4d7c0f` |
| Lime-800 | `#3f6212` |
| Lime-900 | `#365314` |

### 1.5 Green 绿色

| 色阶 | 色值 |
|------|------|
| Green-50 | `#F0FDF4` |
| Green-100 | `#DCFCE7` |
| Green-200 | `#BBF7D0` |
| Green-300 | `#86EFAC` |
| Green-400 | `#4ADE80` |
| **Green-500** | `#22C55E` |
| Green-600 | `#16A34A` |
| Green-700 | `#15803D` |
| Green-800 | `#166534` |
| Green-900 | `#14532D` |

---

## 2. 语义化颜色映射

基于YonDesign的颜色体系，我们建立了以下语义化映射：

| 语义 | 映射 | 色值 |
|------|------|------|
| **Primary** | Orange-600 | `#ea580c` |
| **Secondary** | Amber-500 | `#f59e0b` |
| **Accent** | Yellow-500 | `#eab308` |
| **Success** | Green-500 | `#22c55e` |
| **Warning** | Amber-500 | `#f59e0b` |
| **Error** | Orange-700 | `#c2410c` |
| **Info** | Lime-600 | `#65a30d` |

---

## 3. 中性色系统

采用灰蓝色系作为中性色：

### 3.1 文本色

| 名称 | 色值 | 用途 |
|------|------|------|
| Text Primary | `#1f2937` | 主要文本、标题 |
| Text Secondary | `#4b5563` | 次要文本 |
| Text Tertiary | `#6b7280` | 辅助文本 |
| Text Quaternary | `#9ca3af` | 占位符、禁用 |
| Text Disabled | `rgba(0,0,0,0.25)` | 禁用状态 |
| Text Inverse | `#ffffff` | 深色背景上的文本 |

### 3.2 背景色

| 名称 | 色值 | 用途 |
|------|------|------|
| BG Base | `#ffffff` | 页面背景 |
| BG Container | `#ffffff` | 容器背景 |
| BG Layout | `#f3f4f6` | 布局背景 |
| BG Secondary | `#f3f4f6` | 次级背景 |
| BG Tertiary | `#e5e7eb` | 第三级背景 |

### 3.3 边框色

| 名称 | 色值 | 用途 |
|------|------|------|
| Border | `#d1d5db` | 默认边框 |
| Border Secondary | `#e5e7eb` | 次级边框 |
| Border Tertiary | `#f3f4f6` | 浅色边框 |

---

## 4. 字体系统

### 4.1 字体家族

```css
--font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
```

### 4.2 字体大小

| 名称 | 大小 | 用途 |
|------|------|------|
| XXL | 20px | 大标题 |
| XL | 18px | 标题 |
| LG | 16px | 小标题 |
| **MD** | **14px** | **正文** |
| SM | 13px | 辅助文本 |
| XS | 12px | 注释 |

---

## 5. 间距系统

基于 **4px** 基准网格。

| 名称 | 值 |
|------|-----|
| XS | 4px |
| SM | 8px |
| **MD** | **16px** |
| LG | 24px |
| XL | 32px |

---

## 6. 使用示例

### 6.1 按钮

```vue
<template>
  <!-- 主要按钮 - YonDesign Orange -->
  <AppButton variant="primary">主要操作</AppButton>

  <!-- 次要按钮 - Amber -->
  <AppButton variant="secondary">次要操作</AppButton>

  <!-- 危险按钮 - Orange深色 -->
  <AppButton variant="danger">删除</AppButton>
</template>
```

### 6.2 颜色使用

```scss
.my-component {
  // 使用YonDesign主色
  color: var(--color-primary);        // Orange-600 #ea580c
  background: var(--color-primary-bg); // Orange-50 #fff7ed

  // 使用中性色
  border-color: var(--color-border);   // 灰蓝边框 #d1d5db

  // 使用间距
  padding: var(--spacing-md);          // 16px
  border-radius: var(--radius-md);     // 4px
}
```

---

## 7. 相关文件

| 文件 | 说明 |
|------|------|
| `tokens-yonyou.scss` | YonDesign设计令牌完整定义 |
| `index.scss` | 样式入口 |
| `COMPONENT_STANDARDS.md` | 组件规范 |
| `STYLE_GUIDE.md` | 使用指南 |

---

## 8. 参考资源

- [用友YonDesign官网](https://yondesign.yonyoucloud.com/)
- [TinperM移动端组件库](https://yondesign.yonyoucloud.com/iuap-yondesign/ucf-wh/tinper-m/index.html)
