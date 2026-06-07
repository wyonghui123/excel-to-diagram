# 测试运行标准模板 [NEW 2026-06-05]

> [!!!] 所有 Agent 跑测试前必读 [!!!]
> [!!!] 真实踩坑：测试输出被截断，看不到 pass/fail 结果，智能体误判成功 [!!!]

---

## 一、真实案例（2026-06-05）

**症状**：跑测试后输出被截断在 `[YAML Loader] Loaded: business_object from ...`，看不到 `= X passed in Y s =`

**根因链**：
```
test.py 输出大量 YAML Loader 日志（>500 行）
    ↓
PowerShell 终端显示截断（按 First 50 行）
    ↓
智能体看不到最后 5-10 行的 "= X passed ="
    ↓
误判测试成功 / 失败
```

---

## 二、标准模板（3 选 1）

### 2.1 模板 A：单文件快速验证（推荐）

```powershell
# 1. 跑测试 + 同时 tee 到文件
cd d:\filework\excel-to-diagram
python d:\filework\test.py --file meta/tests/test_X.py 2>&1 | Tee-Object d:\filework\test_x.log | Out-Null

# 2. 必须用 Select-String 验证结果
$result = Select-String -Pattern "passed|failed" d:\filework\test_x.log
Write-Host "=== Test Result ==="
$result | Select-Object -First 3

# 3. 必须检查 [DEBUG] 行的快照使用
Select-String -Pattern "snapshot|Test environment" d:\filework\test_x.log | Select-Object -First 3
```

### 2.2 模板 B：分批 + 进度监控（长测试）

```powershell
# 1. 跑测试（后台）
cd d:\filework\excel-to-diagram
python d:\filework\test.py --all 2>&1 | Tee-Object d:\filework\test_all.log | Out-Null

# 2. 等待 + 检查进度
powershell -Command "Start-Sleep 60; Select-String -Pattern 'passed|failed|ERROR' d:\filework\test_all.log | Select-Object -Last 5"

# 3. 跑完后再查 failed
python d:\filework\test.py --failed 2>&1 | Tee-Object d:\filework\test_failed.log | Out-Null
Select-String -Pattern "passed|failed" d:\filework\test_failed.log | Select-Object -First 5
```

### 2.3 模板 C：批量验证多个文件

```powershell
# 1. 准备文件列表
$files = @(
    "meta/tests/test_transaction_basic.py",
    "meta/tests/test_transaction_advanced.py",
    "meta/tests/test_connection_pool.py"
)

# 2. 逐个跑 + 收集结果
$results = @()
foreach ($f in $files) {
    $log = "d:\filework\test_$(Split-Path $f -Leaf).log"
    cd d:\filework\excel-to-diagram
    python d:\filework\test.py --file $f 2>&1 | Tee-Object $log | Out-Null
    $result = (Select-String -Pattern "passed|failed" $log | Select-Object -First 1).ToString()
    $results += [PSCustomObject]@{File=$f; Result=$result}
}

# 3. 输出汇总
$results | Format-Table -AutoSize
```

---

## 三、常见错误模式

### 3.1 错误：只看退出码

```powershell
# [X] 错误
python d:\filework\test.py --file X.py 2>&1
# 退出码 0 = 成功？
# NO！test.py 退出码 0 = 跑完，**不代表测试通过**

# [OK] 正确
python d:\filework\test.py --file X.py 2>&1 | Tee-Object X.log
Select-String -Pattern "passed|failed" X.log
```

### 3.2 错误：只看前 N 行

```powershell
# [X] 错误（YAML Loader 日志 > 500 行）
python d:\filework\test.py --file X.py 2>&1 | Select-Object -First 50
# 看不到 "= X passed ="

# [OK] 正确（用 Tail + Select-String）
python d:\filework\test.py --file X.py 2>&1 | Tee-Object X.log
Get-Content X.log -Tail 20
```

### 3.3 错误：忘记检查 snapshot

```powershell
# 实际：test.py 自动用 snapshot
# 但如果 snapshot 不存在，会用生产 DB → 污染数据

# [OK] 正确（验证 snapshot 使用）
Select-String -Pattern "snapshot|production DB" X.log | Select-Object -First 3
```

---

## 四、必须输出的 3 项验证

任何测试跑完，**必须输出**：

| 项 | 来源 | 用途 |
|----|------|------|
| `= X passed in Y s =` | pytest 输出 | 测试结果 |
| `[DEBUG] Using snapshot: ...` | test.py 输出 | 确认用 snapshot |
| `[DEBUG] Done — ...` | test.py 输出 | 确认跑完 |

**模板**：
```powershell
$log = "d:\filework\test_run.log"
python d:\filework\test.py --file X.py 2>&1 | Tee-Object $log | Out-Null

Write-Host "=== 1. Test Result ==="
Select-String -Pattern "passed|failed" $log | Select-Object -First 3
Write-Host ""
Write-Host "=== 2. Snapshot ==="
Select-String -Pattern "snapshot|production DB" $log | Select-Object -First 3
Write-Host ""
Write-Host "=== 3. Done ==="
Select-String -Pattern "Done" $log | Select-Object -First 3
```

---

## 五、与 Round/Step 工作流集成

### Round N Step M 模板

```powershell
# 1. 改代码（用 Read + SearchReplace + ast.parse 验证）
# 2. 跑测试（用模板 A）
$log = "d:\filework\test_round${N}_step${M}.log"
cd d:\filework\excel-to-diagram
python d:\filework\test.py --file X.py 2>&1 | Tee-Object $log | Out-Null

# 3. 验证（必须 3 项）
$result = Select-String -Pattern "passed|failed" $log | Select-Object -First 1
$snap = Select-String -Pattern "snapshot" $log | Select-Object -First 1
$done = Select-String -Pattern "Done" $log | Select-Object -First 1

if ($result -match "passed" -and $snap -and $done) {
    Write-Host "[OK] Round $N Step $M PASSED"
} else {
    Write-Host "[FAIL] Round $N Step $M FAILED"
    Get-Content $log -Tail 30
}
```

---

## 六、回退到原始铁律 14

如果 `Tee-Object` 不可用（某些环境），最低标准：

```powershell
# 1. 跑测试到文件
python d:\filework\test.py --file X.py > d:\filework\test_x.log 2>&1

# 2. 看文件 tail
Get-Content d:\filework\test_x.log -Tail 30

# 3. 找 pass/fail
Select-String -Pattern "passed|failed" d:\filework\test_x.log
```

---

## 七、规范更新

| 铁律 | 更新内容 |
|------|---------|
| **14a** | 测试跑完必须用 `Select-String` 验证 pass/fail，不能只看退出码 |
| **14b** | 必须用 `Tee-Object` 或 `> log` 持久化输出 |
| **14c** | 必须验证 [DEBUG] 行确认 test.py 正确加载 |

**已落地**：[SESSION_REMINDER.md L48](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md#L48) 新增铁律 14a

---

_本文档基于 2026-06-05 实际踩坑，所有 Agent 跑测试必读_
