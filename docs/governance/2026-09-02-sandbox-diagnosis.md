# Trae Sandbox 配置诊断与优化报告 (v5.4.1)

> **日期**: 2026-09-02
> **触发**: 用户重启 Trae IDE 后报告"sandbox 的问题很大"
> **范围**: `~/.trae-cn/` 全局配置 + `excel-to-diagram/.trae/` 项目配置
> **优化包**: v5.4.1 sandbox cleanup

---

## 一、诊断结论

| 严重度 | 问题 | 文件 |
|--------|------|------|
| 🔴 P1 | activeProfileId 指向不存在的 profile "full_access" | `permission/global.json` |
| 🔴 P1 | commandRules 膨胀到 100+ 条碎片规则（Python 变量名误识别）| `permission/global.json` |
| 🔴 P1 | hooks.json 引用不存在的 scripts/debug/*.ps1 | `excel-to-diagram/.trae/hooks.json` |
| 🟡 P2 | argv.json 含 JSON 注释（解析可能失败）| `~/.trae-cn/argv.json` |
| 🟡 P2 | 全局 skill-config.json 未同步禁用 deprecated Skill | `~/.trae-cn/skill-config.json` |
| 🟡 P2 | readWrite 路径过宽（特定 worktree 路径、调试路径泄漏）| `permission/global.json` |

---

## 二、修复内容（v5.4.1）

### 2.1 `~/.trae-cn/permission/global.json`（主修复）

| 项 | 修复前 | 修复后 |
|----|-------|-------|
| activeProfileId | `"full_access"`（不存在）| `"defaultCustomProfile"` |
| commandRules 数量 | 100+ 条碎片规则 | **14 条核心规则**（git/npm/npx/node/pip/python/pythonw/powershell/cmd/bash/curl.exe/curl/ssh/scp）|
| sceneRules | shellFileProtection: false, deleteToolApproval: false | **shellFileProtection: true, deleteToolApproval: true** |
| readWrite 路径 | 18 条（含调试路径、特定 worktree）| **6 条核心路径**（workspace + temp + .trae-cn + Trae CN User）|

### 2.2 `excel-to-diagram/.trae/hooks.json`

- 简化：`{"hooks": {}}`（移除引用失效脚本的 SessionStart + PreToolUse）

### 2.3 `~/.trae-cn/argv.json`

- 移除 JSON 注释 `//`

### 2.4 `~/.trae-cn/skill-config.json`

- 添加 disabledSkills: mcp-frontend-testing + browser-use-testing
- 移除 16 个 lark-* marketplace（项目不使用）

### 2.5 `excel-to-diagram/.trae/rules/.deprecated/trae-sandbox-behavior.md`

- 删除（已被 `powershell-execution-guide.md` 整合）

---

## 三、备份位置

修复前的所有文件备份到 `<原路径>.v5.4.1.bak`：

```
~/.trae-cn/permission/global.json.v5.4.1.bak
~/.trae-cn/argv.json.v5.4.1.bak
~/.trae-cn/skill-config.json.v5.4.1.bak
~/.trae-cn/sandbox.json.v5.4.1.bak
excel-to-diagram/.trae/hooks.json.v5.4.1.bak
```

如需回滚：`cp <bak> <原路径>`

---

## 四、修复后预期效果

| 现象 | 修复前 | 修复后 |
|------|-------|-------|
| AI 反复请求批准 Python `print(f'...')` | ❌ 大量误识别 | ✅ 默认沙箱拦截 + 用户 1 次批准 |
| hooks.json 启动报错 | ❌ 引用失效脚本 | ✅ 空 hooks 配置，无报错 |
| argv.json 解析失败 | ⚠️ 含注释 | ✅ 标准 JSON |
| 沙箱行为不可预期 | ❌ activeProfileId 漂移 | ✅ 明确指向 defaultCustomProfile |
| 删除文件需手动批准 | ❌ deleteToolApproval: false | ✅ 启用 |
| 特定 worktree 路径硬编码 | ❌ | ✅ 移除（依赖 $WORKSPACE_FOLDER 变量）|

---

## 五、未解决问题

### 5.1 sandbox.json 配置仍极简

```json
{
    "filesystem": {
        "readWrite": ["$WORKSPACE_FOLDER", "$WORKSPACE_FOLDER\\.git"],
        "readOnly": []
    },
    "network": {
        "default": "allow",
        "allow": [],
        "deny": []
    }
}
```

**问题**：未声明 `.trae-cn/`、`AppData/Local/Temp` 等 AI 必须可写的路径。

**现状**：这些路径由 `permission/global.json` 的 `resourceAuthorization.filesystem.readWrite` 控制，sandbox.json 仅声明基础 workspace 权限。两者分工：sandbox.json 是 Trae IDE 沙箱默认，permission/global.json 是用户级覆盖。

### 5.2 长期改进建议

1. **建立 commandRules 定期清理机制**（每月）
2. **统一项目内 + 全局 Skill 配置**
3. **建立 sandbox 配置变更审计日志**

---

## 六、待用户验证

修复完成后，请重启 Trae IDE 验证：

1. **启动不再报错**（hooks.json 空配置）
2. **AI 执行 git/python/node 等命令无需反复批准**（核心白名单生效）
3. **删除文件需手动批准**（deleteToolApproval 启用）
4. **argv.json 不再解析失败**

如有问题，回滚命令：
```powershell
cp C:\Users\Administrator\.trae-cn\permission\global.json.v5.4.1.bak C:\Users\Administrator\.trae-cn\permission\global.json
# 同样其他 4 个文件
```

---

## 七、参考

- [docs.trae.cn/ide/sandbox](https://docs.trae.cn/ide/sandbox)
- [docs.trae.cn/ide_permission-and-approval](https://docs.trae.cn/ide_permission-and-approval)
- v5.4 深度研究：[2026-09-02-trae-ide-v5.4-deep-research.md](file:///d:/filework/excel-to-diagram/docs/governance/2026-09-02-trae-ide-v5.4-deep-research.md)
- 沙箱行为规范：[powershell-execution-guide.md](file:///d:/filework/.trae/rules/scenarios/8-meta-trae/powershell-execution-guide.md)