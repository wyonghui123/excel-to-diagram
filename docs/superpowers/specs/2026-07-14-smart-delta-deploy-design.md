# SPEC: 智能 Delta 部署 (Smart Delta Deploy)

> **日期**: 2026-07-14
> **状态**: Draft → 待用户审阅
> **触发问题**: 当前部署每次都传 80MB+ zip（1252 文件），其中 90% 文件未变，传输慢、易 drift
> **目标**: 智能识别 changed files，**传输量减少 80-95%**，部署时间减少 50-80%

---

## TL;DR

| 项目 | 内容 |
|------|------|
| **当前** | 全量 zip 84MB / 1252 文件 / 每次都全量 unzip |
| **目标** | 智能 delta zip 1-5MB / ~10-50 changed files / 只解压 changed |
| **核心技术** | 内容寻址 (sha256) + git diff + 选择性 unzip |
| **工作流** | 打包阶段生成 MANIFEST (含每文件 sha256) → 远端 PHASE 0.5 读 MANIFEST 比对 → 只解压差异 + 删除多余文件 |
| **风险** | 中（破坏现有 deploy 流程）→ 0.5d 准备 + 1.5d 实施 + 1d 验证 |
| **向后兼容** | ✅ 保留全量 zip 选项（`--full` 标志） |

---

## 一、问题分析

### 1.1 当前部署模式（实测数据）

```
deploy-v20260713_008.zip: 84,639,133 bytes (80.7 MB)
├── MANIFEST                 1 个
├── frontend_dist_files/    117 个 (新 build, 几乎每次都变)
├── meta/                 1,012 个 (典型部署只改 5-20 个)
└── tools/                  122 个 (偶尔改)
```

**典型部署改动**:
- 前端 dist 100+ 文件（每次 build）
- 后端 meta 5-15 个文件
- tools 0-3 个文件
- **真正需要传输的: ~5-50 个文件，0.5-3MB**

**浪费时间**:
- 传输 80MB，传输 80% 是无用的
- 部署远端 unzip 1252 个文件，每次都全量覆盖
- MD5 验证只检查 2 个关键文件，其余 1250 个文件无验证

### 1.2 真实问题案例（来自 7/13 部署事件）

| 时间 | 问题 | 根因 |
|------|------|------|
| 14:44 | unzip silent failed, backend 跑旧版 | zip 完整但解压时某些文件被跳过 |
| 16:15 | core_service.py 被 multipart 污染 | upload 端点不解析 multipart |
| 16:25 | monitor_prod.py 被污染 | 同上 |
| 多次 | dist hash 不一致 (served != zip) | root dist 没被覆盖, 旧 unified 进程继续 serve |

**所有问题的共同根因**: 没有"逐文件验证 + 缺失重传"机制。

---

## 二、方案设计

### 2.1 总体架构

```
┌─────────────────────────────┐
│  本地 (worktree)            │
│                             │
│  rebuild_zip.py:            │
│  1. git diff HEAD~1..HEAD   │  ← 算出 changed files
│  2. 计算每文件 sha256        │
│  3. 写 MANIFEST (含完整 hash)│
│  4. 打包 delta zip           │
│     ├── MANIFEST            │
│     ├── changed/ (仅变更)   │
│     └── deleted.txt (已删)  │
│                             │
└─────────────────────────────┘
                ↓ upload
        ┌───────────────┐
        │ delta.zip 1MB │  (vs 80MB)
        └───────────────┘
                ↓
┌─────────────────────────────┐
│  远端 (yonaa)               │
│                             │
│  deploy.sh PHASE 0.5:       │
│  1. 解压 MANIFEST 到 tmp    │
│  2. 读 changed/ list        │
│  3. 对比 yonaa 当前 sha256  │
│  4. 只覆盖 mismatched files │
│  5. 删除 deleted.txt 里的   │
│  6. 写 MD5SUMS              │
│                             │
└─────────────────────────────┘
```

### 2.2 三种部署模式（互斥）

| 模式 | 触发条件 | 用途 |
|------|---------|------|
| **delta** (默认) | 上次部署后改动 < 50 文件 | 日常部署 |
| **full** | 首次部署 / yonaa 状态不可信 | 灾难恢复 |
| **hotfix** | 1-2 文件紧急修复 | 单文件 patch |

**CLI**:
```bash
bash deploy.sh --version v20260714_001 --port 5001              # 默认 delta
bash deploy.sh --version v20260714_001 --port 5001 --full       # 强制全量
bash deploy.sh --version v20260714_001 --port 5001 --hotfix meta/server.py  # 单文件
```

### 2.3 MANIFEST 升级 (V007.50+)

**当前 MANIFEST**:
```yaml
version: "v20260713_008"
git:
  head: "abc123"
  branch: "release/pre-2026-06-29"
  commits_count: "1180"
# 没有 file-level hash
```

**升级后 MANIFEST**:
```yaml
version: "v20260714_001"
deploy_id: "20260714_103045_abc12345_a1b2c3"
git:
  head: "def456"
  branch: "release/pre-2026-06-29"
  base_commit: "abc123"  # 上一部署的 commit (用于 delta 范围)
deployment_type: "delta"  # delta / full / hotfix
prev_version: "v20260713_008"  # 上一部署版本 (用于找 prev_manifest)

# ⭐ 新增: 完整文件清单
files:
  count: 1252
  total_size: 84639133
  entries:
    - path: "meta/server.py"
      sha256: "abc123..."
      size: 45821
      mode: "0644"
    - path: "meta/core/datasource.py"
      sha256: "def456..."
      size: 32891
      mode: "0644"
    - path: "frontend_dist_files/index.html"
      sha256: "789xyz..."
      size: 1842
      mode: "0644"
    # ... 1249 more

# ⭐ 新增: 变更统计
changes:
  since: "v20260713_008"  # 上一部署
  modified: 18
  added: 3
  deleted: 1
  modified_files:
    - "meta/server.py"
    - "meta/core/datasource.py"
    # ...
  deleted_files:
    - "tools/deprecated_script.py"
```

### 2.4 Delta zip 格式

```
deploy-v20260714_001-delta.zip
├── MANIFEST              # 完整文件清单 + 变更统计
├── CHANGES               # 简明变更列表 (text)
│   modified: server.py
│   modified: datasource.py
│   deleted: deprecated.py
├── changed/              # 仅包含 changed files (保留原路径)
│   ├── meta/
│   │   ├── server.py
│   │   └── core/
│   │       └── datasource.py
│   └── frontend_dist_files/
│       └── assets/
│           └── index-abc.js
└── DELETED.txt           # 要删除的文件列表 (相对路径, 1 行 1 个)
    tools/deprecated_script.py
```

**关键设计**:
- `changed/` 内的文件**保留原路径**（部署时不重组，节省时间）
- `DELETED.txt` 让远端知道要删什么
- `MANIFEST` 仍然是**完整文件清单**（远端可独立验证完整性）

### 2.5 远端 deploy.sh PHASE 0.5 改造

**当前 PHASE 0.5** (deploy.sh L169-263):
```bash
# 1. 检查 2 个关键文件 MD5，不匹配则 unzip -o $ZIP -d $DEPLOYMENTS_DIR
# 2. 解压后验证 dist hash
```

**改造后**:
```bash
PHASE 0.5: smart extract (delta / full / hotfix)

if [ "$DEPLOY_MODE" = "delta" ] && [ -f "$DEPLOYMENTS_DIR/MANIFEST" ]; then
    # 1. 解压新 MANIFEST 到 tmp
    unzip -p "$ZIP_PATH" MANIFEST > /tmp/new_MANIFEST
    
    # 2. 解析新 MANIFEST 的 files.entries
    NEW_FILES=$(parse_manifest_files /tmp/new_MANIFEST)
    
    # 3. 对比 yonaa 当前文件 sha256 vs 新 MANIFEST
    #    只对 changed files 算 sha256 (其余文件没动, 没必要)
    TO_UPDATE=()
    for entry in $NEW_FILES; do
        local_path="$DEPLOYMENTS_DIR/$entry.path"
        if [ -f "$local_path" ]; then
            local_sha=$(sha256sum "$local_path" | cut -d' ' -f1)
            if [ "$local_sha" != "$entry.sha256" ]; then
                TO_UPDATE+=("$entry.path")
            fi
        else
            TO_UPDATE+=("$entry.path")
        fi
    done
    
    # 4. 找出新 MANIFEST 里有但 yonaa 没有的文件 (新文件)
    #    这些也需要 update (覆盖或创建)
    #    已通过 step 3 处理 (sha256sum 不匹配 → update)
    
    # 5. 解压 changed/ 里所有文件到 DEPLOYMENTS_DIR
    unzip -o "$ZIP_PATH" "changed/*" -d "$DEPLOYMENTS_DIR/"
    
    # 6. 删除 DELETED.txt 里的文件
    if unzip -p "$ZIP_PATH" DELETED.txt 2>/dev/null; then
        unzip -p "$ZIP_PATH" DELETED.txt | while read -r f; do
            rm -f "$DEPLOYMENTS_DIR/$f"
        done
    fi
    
    # 7. 替换 MANIFEST
    cp /tmp/new_MANIFEST "$DEPLOYMENTS_DIR/MANIFEST"
    
    # 8. 写 MD5SUMS 缓存 (加速下次对比)
    unzip -p "$ZIP_PATH" MANIFEST | python3 -c "
import yaml, sys, hashlib
m = yaml.safe_load(sys.stdin)
with open('$DEPLOYMENTS_DIR/.delta_cache', 'w') as f:
    for e in m['files']['entries']:
        f.write(f\"{e['sha256']}  {e['path']}\n\")
"
    
    info "delta 部署: 更新 ${#TO_UPDATE[@]} 个文件"
elif [ "$DEPLOY_MODE" = "full" ] || [ ! -f "$DEPLOYMENTS_DIR/MANIFEST" ]; then
    # 退化: 全量解压 (与现状一致)
    unzip -o "$ZIP_PATH" -d "$DEPLOYMENTS_DIR/"
fi
```

**性能对比**:

| 场景 | 现状 (full) | 目标 (delta) |
|------|------------|--------------|
| 传输 80MB | 60-120s | 1-2MB / 1-5s |
| 解压 1252 文件 | 8-15s | 10-30 文件 / 0.5-2s |
| MD5 验证 | 只 2 文件 | **全部 1252 文件**（更可靠）|
| 总时间 | 70-135s | **2-7s** (提升 20-50x) |

### 2.6 完整 7 步工作流

| # | 阶段 | 内容 | 关键产出 |
|---|------|------|---------|
| **1** | 本地打包 | rebuild_zip.py 生成 delta zip | deploy-v*-delta.zip (1-5MB) |
| **2** | 本地对账 | post_deploy_check.py 验证 (L1+L2) | 报告无 drift |
| **3** | 上传 zip | log_service 9101 /api/upload | /opt/app/deploy-v*-delta.zip |
| **4** | 远端解包 | deploy.sh PHASE 0.5 smart extract | 写 yonaa 文件 |
| **5** | 远端验证 | PHASE 6.55 全量 MD5 验证 | 与新 MANIFEST 完全一致 |
| **6** | 重启服务 | PHASE 1+4+5+7 | 服务切到新版本 |
| **7** | 业务验证 | smoke_test.sh | 5 项真实功能 |

---

## 三、关键技术决策

### 3.1 文件内容寻址方案

**选择 sha256** (而非 md5):
- ✅ 抗碰撞 (git 用 sha256)
- ✅ 业界标准
- ✅ Python stdlib `hashlib.sha256` 支持
- ❌ 慢 1.2x (vs md5)，但 1252 文件 1-2s 可接受

**存储格式**:
- 打包时: `python3 -c "import hashlib; print(hashlib.sha256(open('f','rb').read()).hexdigest())"`
- 远端: `sha256sum file | cut -d' ' -f1`
- 缓存: 写入 `$DEPLOYMENTS_DIR/.delta_cache` (下次对比加速)

### 3.2 MANIFEST 兼容性

**向前兼容**:
- V007.50+ 生成的 MANIFEST 含 `files.entries` 字段
- 旧 deploy.sh 读不到这个字段 → 走"全量解压"分支（fallback）
- ✅ 不破坏旧部署脚本

**向后兼容**:
- V007.49 部署的 yonaa 上 MANIFEST 没 `files.entries`
- 新 deploy.sh 检测 → 走"全量解压"分支
- ✅ 升级到 V007.50+ 第一次部署就是 full

### 3.3 Git diff 算法选择

**场景**: 算出"上次部署后改了什么"

**方案 A**: git diff (使用上一部署的 git tag/commit)
```bash
git diff abc123..def456 --name-status
# 输出: M  meta/server.py
#        A  meta/api/new_api.py
#        D  tools/deprecated.py
```

**方案 B**: 完整文件列表 + sha256
- 不依赖 git 历史
- 远端用 sha256 对比（更可靠）
- 改文件路径无法被 git diff 捕获（如重命名）但 sha256 能

**选择 B** (sha256 对比) 作为主要机制，**A** (git diff) 作为提示。

### 3.4 Hotfix 模式

**场景**: 紧急修复 1-2 个文件 (e.g., `meta/server.py` 有 1 行 bug)

**CLI**:
```bash
bash deploy.sh --version v20260714_001 --port 5001 --hotfix meta/server.py
```

**实现**:
- 自动从 git HEAD 拉取指定文件
- 生成 1-文件 zip
- 远端只覆盖这 1 个文件
- MANIFEST 标记 `deployment_type: "hotfix"`

**优势**:
- 不需要 rebuild_zip.py 完整流程
- 1MB zip / 1 个文件 / 30s 部署

### 3.5 多机器部署 (future)

**当前架构**: 单 yonaa (172.20.59.7)

**未来扩展** (L17 灰度发布):
- 1 staging + 3 prod 节点
- delta zip 同样适用
- 可加 `--target prod-1,prod-2,prod-3` 并发部署

---

## 四、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| MANIFEST 解析失败 (yaml lib 不全) | 部署终止 | fallback 到全量解压 |
| sha256 计算慢 (1252 文件) | 部署 +1-2s | 缓存 `.delta_cache` (二次部署 0.5s) |
| yonaa 状态不可信 (中途有人手动改文件) | sha256 永久 mismatch, 每次都全量 | `--full` 强制重新 sync |
| git diff base_commit 不可知 (首次部署) | 无法算 changes | MANIFEST.deployment_type="full" |
| 删文件误操作 (DELETED.txt 错误) | 重要文件被删 | deploy.sh PHASE 0.5 加 `--dry-run` 模式 |
| multipart 污染 (L8.5) | 文件损坏 | L8.5 已修, 但 delta zip 也受同样保护 |
| zip 完整性 (传输中损坏) | 部署半途失败 | 远端解 zip 立即验证 MANIFEST sha256 |

---

## 五、实施计划 (2 天)

### Day 1: 打包端 + MANIFEST

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 1.1 扩展 MANIFEST 格式 (加 files.entries) | 0.25d | `rebuild_zip.py` 升级 |
| 1.2 生成 sha256 列表 (1252 文件) | 0.25d | MANIFEST 字段填充 |
| 1.3 单元测试 (MANIFEST 解析 + 校验) | 0.25d | `tests/test_manifest.py` |
| 1.4 delta zip 打包逻辑 (只含 changed/) | 0.25d | `--delta` 选项 |
| 1.5 local 验证 (rebuild_zip.py --delta) | 0.25d | zip 大小 < 5MB |

### Day 2: 远端 deploy.sh + 验证

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 2.1 deploy.sh PHASE 0.5 重构 (smart extract) | 0.5d | delta/full/hotfix 三个分支 |
| 2.2 远端 sha256 对比逻辑 | 0.25d | 缓存 `.delta_cache` |
| 2.3 DELETED.txt 处理 | 0.25d | 远端 rm 逻辑 |
| 2.4 staging 环境验证 (e2e_test 全 PASS) | 0.5d | health_check 18/18 + e2e 11/11 |
| 2.5 prod 灰度 (staging 验证后切 prod) | 0.5d | 真实部署 1 次 + 监控 24h |

**总工作量**: 2.5d (含 0.5d 缓冲)

---

## 六、向后兼容 & 回滚

### 6.1 启用策略

**Phase 1** (week 1):
- delta zip 默认生成 (`rebuild_zip.py --delta`)
- 但 deploy.sh 默认还是 full (`--full` 标志)
- 两者并存 1 周验证

**Phase 2** (week 2):
- deploy.sh 默认 delta (auto-detect 上次 MANIFEST)
- `--full` 强制全量
- `--hotfix FILE` 紧急单文件

**Phase 3** (week 3+):
- 删除 `--full` 选项
- 强制 delta
- 任何人都可触发 `bash deploy.sh --rebuild-full` 重建 yonaa

### 6.2 回滚方案

**回滚 1: 旧 deploy.sh 仍可用**
```bash
# 旧 deploy.sh 不读 MANIFEST.files.entries
# 自动 fallback 到 unzip -o 全量解压
bash /opt/app/_deploy_bundle_v049/deploy.sh --version v20260713_008 --port 5001
```

**回滚 2: git revert**
```bash
git revert <commit>  # 撤掉 rebuild_zip.py 的 delta 逻辑
```

**回滚 3: rebuild 旧版 zip**
```bash
python rebuild_zip.py --version v20260713_008  # 仍生成 V007.49 格式 zip
```

---

## 七、成功标准

| 指标 | 当前 | 目标 | 衡量方式 |
|------|------|------|---------|
| 部署包大小 | 80MB | < 5MB | `ls -la deploy-v*.zip` |
| 部署时间 (传输+解压) | 70-135s | < 10s | `time bash deploy.sh` |
| MD5 验证覆盖率 | 2/1252 (0.16%) | 1252/1252 (100%) | `cat MD5SUMS \| wc -l` |
| "假成功" 概率 | 5% (实测) | < 0.1% | 部署后 smoke_test 失败率 |
| 部署失败可恢复性 | 手动 rsync | 自动重试 | 部署失败后 retry 成功率 |
| 远端磁盘写盘量 | 80MB+ | < 5MB (delta) | `du -sh /opt/app/deployments` |

---

## 八、关联文档

- [DEPLOY_CHECKLIST.md](../../DEPLOY_CHECKLIST.md) - 部署 checklist
- [DEPLOY_SOP_V2.md](../../DEPLOY_SOP_V2.md) - 部署 SOP
- [OPS_MANUAL.md](../../OPS_MANUAL.md) - 运维手册
- [TODO_LONGTERM.md](../../TODO_LONGTERM.md) - 长期 todo (L8-L17)
- [rebuild_zip.py](../../../tools/rebuild_zip.py) - 现有打包工具 (L479-535 MANIFEST)
- [deploy.sh](../../../deploy_bundle/deploy.sh) - 远端部署脚本 (PHASE 0.5 L169-263)
- [post_deploy_check.py](../../../tools/post_deploy_check.py) - 部署后对账 (L10)
- [core_service.py _upload](../../../tools/core_service.py) - L8.5 multipart 修复

---

## 九、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-07-14 | AI Assistant | 初稿: 智能 Delta 部署方案 spec (基于用户需求 + 当前 deploy.sh 分析) |

---

## 十、待用户决策

| # | 问题 | 建议选项 |
|---|------|---------|
| 1 | 是否实施方案 A (delta 2d) | ✅ 推荐：先做 Day 1 (1d) 看效果再决定 Day 2 |
| 2 | MANIFEST 格式: yaml vs json | ✅ yaml（可读性 + git diff 友好） |
| 3 | hotfix 模式优先级 | P2（先 delta, hotfix 后做）|
| 4 | 多机部署 (L17 灰度) | 不在本次范围 (1 个月后再评估) |
| 5 | 是否删除 V007.49 全量 zip 选项 | ❌ 保留 1 周，确认稳定后再删 |

**请回复后开始实施。**
