# AI 生成内容防护规则

> 最后更新: 2026-06-07 | 状态: 活跃
> 解决 M3 等 AI 模型在生成代码/Markdown 时自动添加中文/Emoji/特殊字符导致的运行时错误问题

## 一、问题背景

### 实际案例

```vue
<!-- [X] 错误：AI 生成的代码 -->
<el-table :data="data" :field-policy="policy">
  <!-- 🆕 v1 批次 3 / FR-6.7 -->   <-- HTML 注释中含 / 斜杠
  <el-table-column prop="name" />
</el-table>
```

**报错**：`Illegal '/' in tags` at L17

**根因**：
1. AI 模型训练时习惯在代码中加注释、版本号、批次号
2. 中文在 GBK/UTF-8 编码转换时出现乱码
3. Emoji 在某些终端/编译器显示异常
4. HTML 注释中的特殊字符（`/`, `(`, `)`, `<`, `>`）会被 Vue 模板编译器误解析

### 问题规模（2026-06-07 扫描）

| 类型 | 数量 | 占比 |
|------|------|------|
| 代码中 CJK 字符 | 382,482 | 97.2% |
| Emoji | 10,580 | 2.7% |
| 特殊标记 (🆕/✨/🚀 等) | 420 | 0.1% |
| 批次标记 (v1 批次) | 41 | 0.01% |
| HTML 注释含特殊字符 | 36 | 0.01% |
| **总问题数** | **393,559** | **100%** |
| **问题文件数** | **1,979** | - |

---

## 二、防护铁律（10 条）

### 铁律 1：[FORBIDDEN] 代码中禁止使用任何 CJK 字符

**适用范围**：
- `.py`, `.js`, `.ts`, `.vue`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java` 等所有代码文件
- **不适用**：注释、字符串字面量（用户文案）、i18n 文件

**错误示例**：
```python
# [X] 错误
def 获取用户(用户ID):  # 错误：函数名含中文
    return 用户列表  # 错误：变量名含中文
```

**正确示例**：
```python
# [OK] 正确
def get_user(user_id):
    return user_list
```

**例外**（允许中文）：
```python
# [OK] 允许：字符串字面量（用户可见的文案）
message = "用户不存在"  # 允许

# [OK] 允许：日志消息
logger.info(f"用户 {user_id} 创建成功")  # 允许

# [OK] 允许：异常消息
raise ValueError("用户名不能为空")  # 允许
```

### 铁律 2：[FORBIDDEN] 代码中禁止使用任何 Emoji

**适用范围**：所有代码文件（包括 .vue 模板）

**错误示例**：
```javascript
// [X] 错误
const messages = {
    success: "[OK] 操作成功",  // 含 ✅ emoji
    error: "[X] 操作失败",      // 含 ❌ emoji
}
```

**正确示例**：
```javascript
// [OK] 正确
const messages = {
    success: "[OK] 操作成功",  // 使用 [OK] 文本标记
    error: "[X] 操作失败",      // 使用 [X] 文本标记
}
```

**Emoji 替换映射表**：

| Emoji | 替换 | Emoji | 替换 |
|-------|------|-------|------|
| [OK] | [OK] | [X] | [X] |
| [WARNING] | [WARNING] | [INFO] | [INFO] |
| 🆕 | [NEW] | [REFRESH] | [REFRESH] |
| [NOTE] | [NOTE] | [PIN] | [PIN] |
| [CRITICAL] | [CRITICAL] | [HIGH] | [HIGH] |
| [MEDIUM] | [MEDIUM] | [LOW] | [LOW] |
| [TARGET] | [TARGET] | [DESIGN] | [DESIGN] |
| [BUG] | [BUG] | [ALERT] | [ALERT] |
| [FORBID] | [FORBID] | [TOOL] | [TOOL] |
| [BUILD] | [BUILD] | [FAST] | [FAST] |
| [SEARCH] | [SEARCH] | [EMAIL] | [EMAIL] |
| [PHONE] | [PHONE] | [CHART] | [CHART] |
| [TREND_UP] | [TREND_UP] | [TREND_DOWN] | [TREND_DOWN] |
| [DOC] | [DOC] | [PUZZLE] | [PUZZLE] |
| [CRYSTAL] | [CRYSTAL] | [PACKAGE] | [PACKAGE] |
| [CLIPBOARD] | [CLIPBOARD] | [BRUSH] | [BRUSH] |
| [COMPASS] | [COMPASS] | [ROBOT] | [ROBOT] |

### 铁律 3：[FORBIDDEN] Vue/HTML 注释禁止使用特殊字符

**错误示例**：
```vue
<!-- [X] 错误：注释中含 / -->
<!-- 🆕 v1 批次 3 / FR-6.7 -->

<!-- [X] 错误：注释中含 () -->
<!-- (v1.0 新增) 用户管理 -->

<!-- [X] 错误：注释中含 < > -->
<!-- <T001> 修复用户创建错误 -->
```

**正确示例**：
```vue
<!-- [OK] 正确：纯文本注释 -->
<!-- 用户管理 v1.0 新增 -->

<!-- [OK] 正确：使用方括号 -->
<!-- [NEW] 用户管理 v1.0 -->
```

**规则**：
- HTML 注释中只能包含：字母、数字、空格、连字符、下划线、中文标点（，。、）
- 禁止使用：`/`、`(`、`)`、`<`、`>`、`{`、`}`、`[`、`]`

### 铁律 4：[FORBIDDEN] 禁止使用 "vX 批次" 标记

**错误示例**：
```javascript
// [X] 错误
const policy = {  // v1 批次 3
    field: 'name'
}
```

**正确示例**：
```javascript
// [OK] 正确
// FR-6.7: 字段策略
const policy = {
    field: 'name'
}
```

**规则**：
- 使用规范的 Spec ID 引用（如 `FR-6.7`, `TC-001`）
- 不要添加 "v1 批次" 等非规范标记
- 版本信息应记录在 Git commit message 或 CHANGELOG.md

### 铁律 5：[REQUIRED] 所有代码必须通过 Pre-commit 检查

**配置**：
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: scan-ai-content
        name: Scan AI-generated problematic content
        entry: python scripts/scan_ai_content.py
        language: system
        pass_filenames: false
        always_run: true
```

**触发时机**：
- `git commit` 前
- `git push` 前
- CI/CD pipeline

### 铁律 6：[REQUIRED] Markdown 文档可使用 Emoji

**说明**：Markdown 文档中的 Emoji 是允许的，但仍建议使用文本标记以保持一致性

**优先级**：
1. GitHub README.md：可保留 Emoji
2. 项目内部文档：使用 [OK]/[X] 文本标记
3. CHANGELOG.md：可使用 Emoji

### 铁律 7：[FORBIDDEN] 禁止在代码中添加 "🆕"、"✨"、"🚀" 等装饰性 Emoji

**错误示例**：
```python
# [X] 错误
# 🆕 v1.0 新增功能
def new_feature():
    pass
```

**正确示例**：
```python
# [OK] 正确
# [NEW] v1.0 新增功能 (FR-6.7)
def new_feature():
    pass
```

### 铁律 8：[REQUIRED] 字符串中的中文必须使用 UTF-8 编码

**文件头声明**：
```python
# -*- coding: utf-8 -*-
```

**Python 3 默认 UTF-8**，但要确保：
- 编辑器保存为 UTF-8（无 BOM）
- 终端输出设置 UTF-8
- PowerShell：`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`

### 铁律 9：[REQUIRED] AI 生成的代码必须经过自动扫描

**强制流程**：
```
AI 生成代码
    ↓
1. 自动扫描（scan_ai_content.py）
    ↓
2. 发现问题 → 自动修复或人工处理
    ↓
3. 通过 → 提交
```

**人工处理清单**：
- [ ] 运行 `python scripts/scan_ai_content.py --fix`
- [ ] 检查 diff 确认修复正确
- [ ] 提交前 review

### 铁律 10：[REQUIRED] 在会话开始声明 AI 内容防护

**会话开始模板**：
```
【会话开始 - AI 内容防护声明】

我将遵守以下 AI 内容防护规则：
- [ ] 代码中禁止使用 CJK 字符（除字符串字面量外）
- [ ] 代码中禁止使用任何 Emoji
- [ ] HTML 注释禁止使用特殊字符 (/() <> [])
- [ ] 禁止使用 "vX 批次" 等非规范标记
- [ ] 所有代码必须通过 scan_ai_content.py 检查

如违反以上规则，将自动触发修复脚本。
```

---

## 三、检测与修复工具

### 3.1 扫描工具

```bash
# 扫描整个项目
python scripts/scan_ai_content.py

# 扫描指定文件
python scripts/scan_ai_content.py src/file.py src/file2.vue

# 输出 JSON 报告
python scripts/scan_ai_content.py --json > report.json
```

### 3.2 自动修复工具

```bash
# 自动修复（保留备份）
python scripts/fix_ai_content.py src/

# 强制修复（不提示）
python scripts/fix_ai_content.py --force src/

# 预览修复
python scripts/fix_ai_content.py --dry-run src/
```

### 3.3 Git Hook 集成

```bash
# 安装 pre-commit hook
python scripts/install_git_hooks.py

# 卸载
python scripts/install_git_hooks.py --uninstall
```

---

## 四、违规分级

| 级别 | 类型 | 处理 | 示例 |
|------|------|------|------|
| **[CRITICAL]** | HTML 注释含 `/` | 阻止提交 | `<!-- v1/批次 -->` |
| **[CRITICAL]** | v1 批次标记 | 阻止提交 | `// v1 批次 3` |
| **[HIGH]** | 代码中 Emoji | 警告 + 提示 | `// 🆕 新增` |
| **[MEDIUM]** | 代码中 CJK（变量名/函数名） | 警告 | `def 获取用户():` |
| **[LOW]** | Markdown 中 Emoji | 仅提示 | `# [OK] 标题` |
| **[LOW]** | 字符串中 CJK | 允许 | `message = "成功"` |

---

## 五、违规处理流程

### Step 1: 检测

```bash
python scripts/scan_ai_content.py
```

### Step 2: 查看问题

```
src/views/Foo.vue
  [CRITICAL] L17: HTML 注释含 /  - "<!-- v1 批次 3 / FR-6.7 -->"
  [HIGH] L18: Emoji              - "🆕"
  [MEDIUM] L20: 代码中 CJK       - "获取用户列表"
```

### Step 3: 自动修复（可选）

```bash
python scripts/fix_ai_content.py src/views/Foo.vue
```

**自动修复操作**：
- 移除 HTML 注释中的特殊字符
- 移除 v1 批次标记
- 替换 Emoji 为文本标记
- 保留字符串中的中文（需人工 review）

### Step 4: 人工 Review

```bash
git diff src/views/Foo.vue
```

**人工检查**：
- [ ] 字符串中的中文是否需要保留
- [ ] 函数/变量名是否需要重命名
- [ ] HTML 注释删除是否影响功能

### Step 5: 重新扫描确认

```bash
python scripts/scan_ai_content.py src/views/Foo.vue
```

---

## 六、常见违规案例

### 案例 1：Vue 模板 HTML 注释错误

```vue
<!-- [X] 错误 -->
<el-table :field-policy="policy">
  <!-- 🆕 v1 批次 3 / FR-6.7 -->
  <el-table-column prop="name" />
</el-table>
```

**报错**：`Illegal '/' in tags`

**修复**：
```vue
<!-- [OK] 正确 -->
<el-table :field-policy="policy">
  <!-- FR-6.7 字段策略 -->
  <el-table-column prop="name" />
</el-table>
```

### 案例 2：Python 函数名含中文

```python
# [X] 错误
def 获取用户列表():
    pass
```

**修复**：
```python
# [OK] 正确
def get_user_list():
    pass
```

### 案例 3：JavaScript 注释中 Emoji

```javascript
// [X] 错误
// 🆕 v1.0 新增
const newFeature = () => {}
```

**修复**：
```javascript
// [OK] 正确
// [NEW] v1.0 新增 (FR-6.7)
const newFeature = () => {}
```

### 案例 4：日志消息含 Emoji

```python
# [X] 错误
logger.info("[OK] 操作成功")
```

**修复**：
```python
# [OK] 正确
logger.info("[OK] 操作成功")  # 保留 [OK] 文本标记
```

### 案例 5：HTML 注释中含括号

```html
<!-- [X] 错误 -->
<!-- (v1.0) 用户管理 -->
```

**修复**：
```html
<!-- [OK] 正确 -->
<!-- 用户管理 v1.0 -->
```

---

## 七、预防机制

### 7.1 AI 提示词（Prompt）

**在 Prompt 中加入防护指令**：
```
[AI 内容防护]
- 代码中禁止使用 CJK 字符（除字符串字面量外）
- 代码中禁止使用任何 Emoji
- HTML 注释禁止使用特殊字符 /() <> []
- 禁止使用 "vX 批次" 等非规范标记
- 禁止添加版本号、日期、AI 标识等装饰性注释
- 提交前必须通过 scan_ai_content.py 检查
```

### 7.2 CI/CD 集成

```yaml
# .github/workflows/ci.yml
- name: Scan AI content
  run: python scripts/scan_ai_content.py
  continue-on-error: false
```

### 7.3 IDE 配置

**VS Code settings.json**：
```json
{
    "files.encoding": "utf8",
    "files.autoGuessEncoding": false,
    "[python]": {
        "editor.formatOnSave": true
    }
}
```

**Prettier 配置**：
```json
{
    "printWidth": 100,
    "singleQuote": true,
    "endOfLine": "lf"
}
```

---

## 八、相关规范

| 规范 | 文件 |
|------|------|
| 编码规范 | `.trae/rules/core/coding-standards.md` |
| UI 规范 | `.trae/rules/core/ui-standards.md` |
| 文件编码 | `.trae/rules/file-encoding-rules.md` |
| 表单调试 | `.trae/rules/core/form-debugging.md` |

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 创建 AI 内容防护规则（基于实际扫描数据 1979 文件、39万+ 问题） |
