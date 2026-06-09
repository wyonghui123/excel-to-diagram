## 目录

1. [一、概述](#一-概述)
2. [二、脚本清单](#二-脚本清单)
3. [三、集成方式](#三-集成方式)
4. [四、测试用例](#四-测试用例)
5. [五、报告输出](#五-报告输出)
6. [六、使用示例](#六-使用示例)
7. [七、故障排查](#七-故障排查)
8. [八、扩展测试](#八-扩展测试)
9. [九、更新记录](#九-更新记录)

---
# CI/CD 自动化测试集成方案

> **文档版本**: v1.0
> **更新日期**: 2026-04-29
> **适用范围**: 部署流程自动化

---

## 一、概述

本文档描述如何将自动化测试集成到部署流程中，实现部署后自动验证。

### 1.1 目标

- 部署完成后自动执行健康检查
- 验证所有服务正常运行
- 验证API功能正常
- 生成测试报告
- 失败时自动回滚（可选）

### 1.2 集成架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CI/CD 集成架构                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  部署流程                                                                    │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐               │
│  │  备份   │ -> │  解压   │ -> │  切换   │ -> │  启动   │               │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘               │
│                                                            │               │
│                                                            ▼               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    自动化测试验证                                    │   │
│  │                                                                      │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐      │   │
│  │  │ 服务端口  │  │ HTTP端点  │  │ API功能   │  │ 数据库    │      │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘      │   │
│  │                                                                      │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                      │   │
│  │  │ 文件系统  │  │ 资源使用  │  │ 版本信息  │                      │   │
│  │  └───────────┘  └───────────┘  └───────────┘                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                            │               │
│                                      ┌───────────────────────┼───────┐      │
│                                      ▼                       ▼       ▼      │
│                               ┌──────────┐           ┌─────────┐  ┌────┐  │
│                               │  通过    │           │  失败   │  │ 报告│  │
│                               └──────────┘           └────┬────┘  └────┘  │
│                                                            │                │
│                                                            ▼                │
│                                                     ┌──────────┐            │
│                                                     │ 自动回滚 │            │
│                                                     │ (可选)   │            │
│                                                     └──────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、脚本清单

| 脚本 | 功能 | 位置 |
|------|------|------|
| `ci-cd-test.sh` | 自动化测试主脚本 | `/opt/app/scripts/ci-cd-test.sh` |
| `health-check.sh` | 健康检查脚本 | `/opt/app/scripts/health-check.sh` |
| `post-deploy-verify.sh` | 部署后验证脚本 | `/opt/app/scripts/post-deploy-verify.sh` |
| `rollback-enhanced.sh` | 回滚脚本 | `/opt/app/scripts/rollback-enhanced.sh` |

---

## 三、集成方式

### 3.1 方式一：集成到部署脚本

修改 `deploy-auto.sh`，在末尾添加测试调用：

```bash
# 在 deploy-auto.sh 末尾添加

# ============================================================
# 自动化测试验证
# ============================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  执行自动化测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ -f "$APP_DIR/scripts/ci-cd-test.sh" ]]; then
    bash "$APP_DIR/scripts/ci-cd-test.sh"
    TEST_RESULT=$?

    if [[ $TEST_RESULT -ne 0 ]]; then
        echo ""
        echo -e "${RED}[✗] 测试失败，正在回滚...${NC}"
        # 可选：自动回滚
        # bash "$APP_DIR/scripts/rollback-enhanced.sh" -a -f
        exit 1
    fi
else
    echo -e "${YELLOW}[!] 测试脚本不存在，跳过测试${NC}"
fi
```

### 3.2 方式二：独立测试脚本

使用 `post-deploy-verify.sh` 作为独立验证流程：

```bash
# 部署完成后执行
/opt/app/scripts/post-deploy-verify.sh
```

### 3.3 方式三：定时健康检查

使用 crontab 设置定时测试：

```bash
# 每小时执行一次健康检查
0 * * * * /opt/app/scripts/ci-cd-test.sh -q >> /opt/app/shared/logs/ci-cd-test-cron.log 2>&1

# 如果测试失败，发送告警（需要配置邮件或 webhook）
```

---

## 四、测试用例

### 4.1 服务端口测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 前端服务 (8081) | 端口监听中 | 重启服务 |
| 后端服务 (5001) | 端口监听中 | 重启服务 |
| Admin服务 (8080) | 端口监听中 | 重启服务 |

### 4.2 HTTP端点测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 前端首页 | HTTP 200 | 检查前端服务 |
| 后端健康检查 | HTTP 200 | 检查后端服务 |
| Schema API | HTTP 200 | 检查后端路由 |
| Admin页面 | HTTP 200/302 | 检查Admin服务 |

### 4.3 API功能测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 获取产品列表 | 返回有效JSON | 检查API逻辑 |
| 获取Schema列表 | 返回有效数据 | 检查Schema加载 |
| 统计数据API | 返回有效数据 | 检查统计数据 |

### 4.4 数据库测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 数据库文件存在 | 文件存在且非空 | 检查数据库 |
| 数据库连接 | 连接成功 | 检查数据库服务 |
| 数据库表数量 | 至少5个表 | 检查表创建 |

### 4.5 文件系统测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 关键目录存在 | 目录可访问 | 检查部署 |
| 日志目录可写 | 有写权限 | 修复权限 |

### 4.6 资源测试

| 测试项 | 期望结果 | 失败处理 |
|--------|----------|----------|
| 磁盘空间 | 使用率 < 90% | 清理磁盘 |
| 内存使用 | 使用率 < 90% | 检查内存泄漏 |

---

## 五、报告输出

### 5.1 JSON报告

```json
{
    "timestamp": "2026-04-29T12:00:00Z",
    "duration_seconds": 15,
    "overall_status": "PASSED",
    "summary": {
        "total": 18,
        "passed": 18,
        "failed": 0,
        "skipped": 0
    },
    "tests": [
        {"name": "前端服务端口 (8081)", "status": "PASS", "message": "端口监听中, PID: 1234"},
        {"name": "后端服务端口 (5001)", "status": "PASS", "message": "端口监听中, PID: 1235"},
        ...
    ]
}
```

### 5.2 报告存储位置

| 类型 | 位置 |
|------|------|
| JSON报告 | `/opt/app/state/test-results/test-report-YYYYMMDD_HHMMSS.json` |
| HTML报告 | `/opt/app/state/test-results/test-report-YYYYMMDD_HHMMSS.html` |
| Cron日志 | `/opt/app/shared/logs/ci-cd-test-cron.log` |

---

## 六、使用示例

### 6.1 部署后自动测试

```bash
# 执行部署
./deploy-auto.sh deploy-v20260429_001.zip

# 部署脚本会自动执行测试
# 失败时显示失败的测试项并询问是否回滚
```

### 6.2 独立执行测试

```bash
# 在服务器上执行
/opt/app/scripts/ci-cd-test.sh

# 静默模式（只输出结果）
/opt/app/scripts/ci-cd-test.sh -q

# 只输出JSON
/opt/app/scripts/ci-cd-test.sh -j

# 只测试特定类型
/opt/app/scripts/ci-cd-test.sh -t http
```

### 6.3 集成到CI/CD Pipeline

```yaml
# .gitlab-ci.yml 示例
deploy:
  stage: deploy
  script:
    - bash deploy-auto.sh deploy-v${CI_COMMIT_SHORT_SHA}.zip
    - bash /opt/app/scripts/ci-cd-test.sh -j > test-result.json
  artifacts:
    reports:
      junit: test-result.json
  when: manual
```

---

## 七、故障排查

### 7.1 测试失败常见原因

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 端口未监听 | 服务启动失败 | 检查日志 `less /opt/app/shared/logs/` |
| HTTP 502/504 | 后端服务异常 | 检查后端进程和日志 |
| 数据库连接失败 | 数据库文件损坏 | 检查 `sqlite3 /opt/app/shared/data/architecture.db` |
| API返回空数据 | Schema未加载 | 调用 reload API 或重启服务 |

### 7.2 手动验证

```bash
# 1. 检查服务进程
ps aux | grep python

# 2. 检查端口占用
netstat -tlnp | grep -E "8081|5001|8080"

# 3. 测试HTTP端点
curl http://localhost:8081/
curl http://localhost:5001/api/v1/health

# 4. 检查日志
tail -f /opt/app/shared/logs/*.log

# 5. 直接运行测试并查看详细输出
bash /opt/app/scripts/ci-cd-test.sh
```

---

## 八、扩展测试

### 8.1 添加自定义测试

编辑 `ci-cd-test.sh`，在适当位置添加新测试函数：

```bash
# 添加自定义测试
test_custom() {
    log_step "执行自定义测试..."

    # 你的测试逻辑
    local result=$(curl -s http://localhost:5001/api/v1/custom)

    if [[ "$result" == "expected" ]]; then
        record_test "自定义测试" "PASS" "符合预期"
    else
        record_test "自定义测试" "FAIL" "结果不符合预期"
    fi
}
```

### 8.2 集成性能测试（可选）

```bash
# 使用 Apache Bench 进行压力测试
ab -n 100 -c 10 http://localhost:8081/

# 集成到测试脚本
test_performance() {
    local response_time=$(curl -o /dev/null -s -w '%{time_total}' http://localhost:5001/api/v1/health)
    if (( $(echo "$response_time < 1.0" | bc -l) )); then
        record_test "API响应时间" "PASS" "${response_time}s"
    else
        record_test "API响应时间" "FAIL" "${response_time}s > 1.0s"
    fi
}
```

---

## 九、更新记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-29 | 1.0 | 初始版本 |
