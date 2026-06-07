# Playwright 录屏脚本调试与培训内容生成

## 时间
2026-04-17

## 背景

用户需要为 AA图 应用创建自动化录屏脚本，用于生成产品培训介绍内容。

## 主要内容

### 1. 录屏脚本开发

**目标**：创建 Playwright 脚本自动录制应用操作流程

**文件**：
- `record-demo.js` - 自动化演示脚本
- `record-operations.js` - 操作录制脚本（监听用户操作）
- `record-manual.js` - 手动录制模式

**关键问题**：
- 浏览器启动后立即关闭的问题
- 需要添加 `--no-sandbox` 参数解决权限问题
- 使用 `setInterval` 定期截图保持录制
- 使用 `page.on('close')` 监听页面关闭事件

### 2. 自动化脚本流程

用户指定的操作流程：
1. 上传 Excel 文件
2. 选择供应链云领域
3. 点击下一步
4. 展开并全选
5. 选择图表类型（业务对象图）- **双击**
6. 配置参数
7. 生成图表
8. 全屏、缩放
9. 导出 HTML

### 3. 手动录制成功

运行 `record-operations.js`，用户手动操作完成完整流程。

**生成文件**：
- 视频：`page@bb5ddf60a680a91ad939b2961bce4861.webm` (27MB)
- 截图：28张自动截图

### 4. 培训文档生成

**Markdown 文档**：`videos\manual-session\培训介绍.md`

包含：
- 产品介绍
- 8个功能特性
- 7个操作步骤
- 数据格式要求
- 使用场景和注意事项

**Word 文档**：`videos\manual-session\培训介绍.docx` (0.52MB)

生成脚本：`videos\manual-session\generate_doc.py`

使用 python-docx 库生成，包含：
- 8张关键截图
- 格式化的表格（业务对象/关系 Sheet）
- 完整的操作流程说明

### 5. 关键截图

| 截图 | 步骤 |
|------|------|
| screenshot_001.png | 上传Excel |
| screenshot_009.png | 选择供应链云 |
| screenshot_013.png | 展开供应链云 |
| screenshot_015.png | 全选 |
| screenshot_017.png | 选择业务对象图 |
| screenshot_023.png | 配置参数 |
| screenshot_025.png | 图表生成成功 |
| screenshot_028.png | 最终状态 |

## 技术细节

### Playwright 浏览器启动参数
```javascript
browser = await chromium.launch({
  headless: false,
  args: ['--no-sandbox', '--disable-setuid-sandbox']
});
```

### 定期截图
```javascript
const screenshotInterval = setInterval(async () => {
  await page.screenshot({ path: `screenshot_${index}.png` });
}, 10000);
```

### 监听页面关闭
```javascript
page.on('close', () => {
  clearInterval(screenshotInterval);
});
```

## 输出文件

| 文件 | 路径 |
|------|------|
| 培训介绍.md | `videos\manual-session\培训介绍.md` |
| 培训介绍.docx | `videos\manual-session\培训介绍.docx` |
| 操作视频 | `videos\manual-session\page@bb5ddf60a680a91ad939b2961bce4861.webm` |
| 截图目录 | `videos\manual-session\screenshots\` |
| 生成脚本 | `videos\manual-session\generate_doc.py` |

## 后续工作

- [ ] 继续完善自动化脚本 `record-demo.js`
- [ ] 测试方案 B（自动化脚本录制）
- [ ] 根据用户反馈调整培训内容

## 相关文件

- `src/components/MermaidComponent.vue` - Mermaid 导出功能
- `src/composables/useMermaid/interaction/useInteraction.js` - 交互功能
- `.trae/specs/mermaid-export/spec.md` - 功能规范文档
