# -*- coding: utf-8 -*-
"""
P4.3 TDD 测试: 推导管道 + 求值引擎 性能基准测试

[目标]
  为灰度切换前提供性能验收门禁, 确保:
  - 单次权限检查延迟在可接受范围 (P95 < 5ms)
  - 推导管道批量处理能力满足生产需求 (100 角色 × 10 规则 < 1s)
  - 性能基线可保存/加载/对比, 支持回归检测

[设计原则]
  - TDD: 先写测试, 定义 PerformanceBenchmarkSuite 接口契约
  - 复用现有 performance_base.py 基础设施
  - 阈值宽松 (避免 CI 环境抖动), 但能捕获重大回归
  - 不污染主数据库, 使用临时 SQLite DB
"""
import os
import sys
import json
import time
import sqlite3
import tempfile
import shutil

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'


# ============================================================================
# Fixtures: 创建性能测试专用 DB (含一定规模数据)
# ============================================================================

@pytest.fixture(scope="module")
def perf_db():
    """性能测试 DB: 100 条记录, 5 个角色, 每个 10 条规则"""
    tmp_dir = tempfile.mkdtemp(prefix='perf_bench_')
    db_path = os.path.join(tmp_dir, 'perf.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        -- Layer 2: 规则表
        CREATE TABLE permission_rules_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            permission_level VARCHAR(50) DEFAULT 'read',
            include_conditions TEXT,
            exclude_conditions TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Layer 1: 事实表
        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name)
        );

        -- 业务对象表 (100 条记录, 用于权限检查)
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT, code TEXT,
            domain_id INTEGER,
            sub_domain_id INTEGER,
            risk_level INTEGER,
            status TEXT,
            owner_id INTEGER,
            created_by INTEGER
        );

        CREATE TABLE domains (id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, code TEXT);

        -- 5 个 domain, 每个 5 个 sub_domain, 共 25 个 sub_domain
        INSERT INTO domains VALUES (1, 'D1'), (2, 'D2'), (3, 'D3'), (4, 'D4'), (5, 'D5');
        INSERT INTO sub_domains VALUES
            (101, 1, 'SD11'), (102, 1, 'SD12'), (103, 1, 'SD13'),
            (201, 2, 'SD21'), (202, 2, 'SD22'), (203, 2, 'SD23'),
            (301, 3, 'SD31'), (302, 3, 'SD32'), (303, 3, 'SD33'),
            (401, 4, 'SD41'), (402, 4, 'SD42'), (403, 4, 'SD43'),
            (501, 5, 'SD51'), (502, 5, 'SD52'), (503, 5, 'SD53');

        -- 100 条 product 记录, owner 在 1-50 之间循环
        INSERT INTO products (id, name, code, domain_id, sub_domain_id, risk_level, status, owner_id, created_by)
        VALUES
            (1, 'P1', 'C1', 1, 101, 1, 'active', 1, 1),
            (2, 'P2', 'C2', 1, 102, 2, 'active', 2, 2),
            (3, 'P3', 'C3', 2, 201, 3, 'archived', 3, 3);
        -- 用程序批量插入剩余 97 条
    ''')

    # 批量插入剩余记录
    cursor = conn.cursor()
    rows = []
    for i in range(4, 101):
        domain_id = ((i - 1) % 5) + 1
        sub_domain_id = 100 + domain_id * 100 + ((i - 1) % 3) + 1
        risk = ((i - 1) % 5) + 1
        status = 'active' if i % 3 != 0 else 'archived'
        owner = ((i - 1) % 50) + 1
        rows.append((i, f'P{i}', f'C{i}', domain_id, sub_domain_id, risk, status, owner, owner))
    cursor.executemany(
        'INSERT INTO products (id, name, code, domain_id, sub_domain_id, risk_level, status, owner_id, created_by) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        rows,
    )
    conn.commit()
    conn.close()

    yield db_path

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def seeded_perf_db(perf_db):
    """预先填充 5 角色 × 10 规则到 perf_db"""
    conn = sqlite3.connect(perf_db)
    cursor = conn.cursor()
    # 5 角色 × 2 资源类型 × 5 级别 = 50 条规则
    for role_id in range(1, 6):
        for resource in ['product', 'domain']:
            for level_idx, level in enumerate(['read', 'write', 'admin']):
                include = json.dumps([
                    {'field': 'domain_id', 'op': 'IN', 'value': [1, 2, 3]},
                    {'field': 'risk_level', 'op': '<=', 'value': 3},
                ])
                exclude = json.dumps([
                    {'field': 'status', 'op': '=', 'value': 'archived'},
                ])
                cursor.execute(
                    'INSERT INTO permission_rules_v2 '
                    '(role_id, resource_type, permission_level, include_conditions, '
                    ' exclude_conditions, derivation_mode, source) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (role_id, resource, level, include, exclude, 'static', 'manual'),
                )
    conn.commit()
    conn.close()
    return perf_db


# ============================================================================
# 1. PerformanceBenchmarkSuite 接口契约
# ============================================================================

class TestPerformanceBenchmarkSuiteInterface:
    """PerformanceBenchmarkSuite 模块可导入 + 接口契约"""

    def test_module_importable(self):
        """模块可导入"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        assert PerformanceBenchmarkSuite is not None

    def test_constructor_accepts_db_path(self, perf_db):
        """构造函数接受 db_path"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        suite = PerformanceBenchmarkSuite(db_path=perf_db)
        assert suite is not None

    def test_benchmark_effective_intent_checker_returns_metric(self, seeded_perf_db):
        """benchmark_check_single 返回 PerformanceMetric"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.tests.performance.performance_base import PerformanceMetric

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        # 先写入 1 条 Intent 用于检查
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        dao = EffectiveIntentDAO(seeded_perf_db)
        dao.upsert(
            role_id=1, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}],
                'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
            },
            derivation_mode='static', source='derived',
        )

        metric = suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=10,
        )
        assert isinstance(metric, PerformanceMetric)
        assert metric.name.startswith('check_single')
        assert metric.iterations == 10
        assert metric.value > 0  # 平均耗时 (ms)
        assert metric.unit == 'ms'

    def test_benchmark_check_multi_role_returns_metric(self, seeded_perf_db):
        """benchmark_check_multi_role 返回 PerformanceMetric"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.tests.performance.performance_base import PerformanceMetric

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_check_multi_role(
            role_ids=[1, 2, 3],
            bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=10,
        )
        assert isinstance(metric, PerformanceMetric)
        assert metric.iterations == 10

    def test_benchmark_derivation_pipeline_returns_metric(self, seeded_perf_db):
        """benchmark_derive_role 返回 PerformanceMetric"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.tests.performance.performance_base import PerformanceMetric

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_derive_role(role_id=1, iterations=5)
        assert isinstance(metric, PerformanceMetric)
        assert metric.iterations == 5


# ============================================================================
# 2. EffectiveIntentChecker 性能门禁
# ============================================================================

class TestEffectiveIntentCheckerPerformance:
    """求值引擎性能门禁: 单次检查 P95 < 阈值"""

    def test_check_single_p95_under_50ms(self, seeded_perf_db):
        """[门禁] 单次 check P95 < 50ms (宽松阈值, 含 SQLite IO)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        # 准备 Intent
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        dao = EffectiveIntentDAO(seeded_perf_db)
        dao.upsert(
            role_id=1, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2, 3]}],
                'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
            },
            derivation_mode='static', source='derived',
        )

        metric = suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=50,
        )
        # P95 必须 < 50ms (CI 容忍度)
        assert metric.percentile_95 < 50.0, (
            f'P95={metric.percentile_95:.2f}ms exceeds 50ms threshold'
        )

    def test_check_multi_role_p95_under_100ms(self, seeded_perf_db):
        """[门禁] 多角色 check_multi_role P95 < 100ms (3 角色)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        # 给 3 个角色都写入 Intent
        dao = EffectiveIntentDAO(seeded_perf_db)
        for rid in [1, 2, 3]:
            dao.upsert(
                role_id=rid, bo_id='product', action_name='read',
                data_scope={
                    'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}],
                    'exclude': [],
                },
                derivation_mode='static', source='derived',
            )

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_check_multi_role(
            role_ids=[1, 2, 3],
            bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=30,
        )
        # P95 < 100ms (3 角色 = 3 倍单角色开销 + 余量)
        assert metric.percentile_95 < 100.0, (
            f'P95={metric.percentile_95:.2f}ms exceeds 100ms threshold'
        )

    def test_check_qps_at_least_20(self, seeded_perf_db):
        """[门禁] 单次 check QPS ≥ 20 (50ms/call 的倒数)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(seeded_perf_db)
        dao.upsert(
            role_id=1, bo_id='product', action_name='read',
            data_scope={'include': [], 'exclude': []},
            derivation_mode='static', source='derived',
        )

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=50,
        )
        # value 是 ms/call, QPS = 1000 / value
        qps = 1000.0 / metric.value if metric.value > 0 else 0
        assert qps >= 20, f'QPS={qps:.1f} below 20 threshold (avg={metric.value:.2f}ms)'

    def test_check_owner_path_is_fastest(self, seeded_perf_db):
        """[对比] Owner 命中应比 Include 匹配快 (短路)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        from meta.core.effective_intent_dao import EffectiveIntentDAO

        dao = EffectiveIntentDAO(seeded_perf_db)
        # Owner 命中场景
        dao.upsert(
            role_id=10, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'domain_id', 'op': 'IN', 'value': list(range(1, 6))}],
                'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
            },
            derivation_mode='static', source='derived',
        )

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        # Owner 命中 (user_id=1 是 product#1 的 owner)
        owner_metric = suite.benchmark_check_single(
            role_id=10, bo_id='product', action_name='read',
            record_id=1, user_id=1,  # owner_id=1
            iterations=30,
        )
        # Include 匹配 (user_id=999 不是 owner, 走 include 检查)
        include_metric = suite.benchmark_check_single(
            role_id=10, bo_id='product', action_name='read',
            record_id=1, user_id=999,
            iterations=30,
        )
        # Owner 路径应 ≤ Include 路径 (允许抖动, 用平均值比较)
        # 注意: SQLite 自身有抖动, 不做强 ≤, 只验证 owner 不显著慢
        assert owner_metric.value <= include_metric.value * 1.5, (
            f'Owner path ({owner_metric.value:.2f}ms) should not be much slower than '
            f'include path ({include_metric.value:.2f}ms)'
        )


# ============================================================================
# 3. PermissionDerivationPipeline 性能门禁
# ============================================================================

class TestDerivationPipelinePerformance:
    """推导管道性能门禁"""

    def test_derive_single_role_under_500ms(self, seeded_perf_db):
        """[门禁] 单角色推导 (6 规则) P95 < 500ms"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_derive_role(role_id=1, iterations=10)
        # 6 规则 × 展开为多个 Intent, 应 < 500ms (含 DB 写)
        assert metric.percentile_95 < 500.0, (
            f'P95={metric.percentile_95:.2f}ms exceeds 500ms threshold'
        )

    def test_derive_larger_rule_set_under_threshold(self, perf_db):
        """[门禁] 30 规则推导 P95 < 2s (扩容场景)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite
        import sqlite3 as _sqlite3

        # 在 perf_db 上为 role 100 插入 30 条规则 (10 BO × 3 级别)
        conn = _sqlite3.connect(perf_db)
        cursor = conn.cursor()
        for bo_idx in range(10):
            bo_id = f'bo_{bo_idx}'
            for level in ['read', 'write', 'admin']:
                include = json.dumps([{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}])
                cursor.execute(
                    'INSERT INTO permission_rules_v2 '
                    '(role_id, resource_type, permission_level, include_conditions, '
                    ' derivation_mode, source) VALUES (?, ?, ?, ?, ?, ?)',
                    (100, bo_id, level, include, 'static', 'manual'),
                )
        conn.commit()
        conn.close()

        suite = PerformanceBenchmarkSuite(db_path=perf_db)
        metric = suite.benchmark_derive_role(role_id=100, iterations=5)
        # 30 规则 → 30 × ~4 actions = ~120 Intents, 应 < 2s
        assert metric.percentile_95 < 2000.0, (
            f'P95={metric.percentile_95:.2f}ms exceeds 2000ms threshold'
        )

    def test_derive_multi_role_bulk_performance(self, seeded_perf_db):
        """[门禁] 批量 5 角色推导 < 3s (顺序执行)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_derive_multi_roles(
            role_ids=[1, 2, 3, 4, 5],
            iterations=3,
        )
        # 5 角色 × 6 规则, 总耗时 < 3s
        assert metric.percentile_95 < 3000.0, (
            f'P95={metric.percentile_95:.2f}ms exceeds 3000ms threshold'
        )

    def test_derive_idempotent_repeated_runs(self, seeded_perf_db):
        """[稳定性] 多次重复推导性能稳定 (std_dev/mean < 1.0)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        metric = suite.benchmark_derive_role(role_id=1, iterations=10)
        # 变异系数 (CV) < 1.0 (允许较大抖动, 但不应失控)
        if metric.value > 0:
            cv = metric.std_dev / metric.value
            assert cv < 1.0, (
                f'Coefficient of variation={cv:.2f} too high (unstable performance)'
            )


# ============================================================================
# 4. 性能基线 + 回归检测
# ============================================================================

class TestPerformanceBaselineAndRegression:
    """性能基线保存/加载 + 回归检测"""

    def test_save_baseline_to_json(self, seeded_perf_db, tmp_path):
        """保存基线到 JSON 文件"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=5,
        )
        # 不预先写入 Intent 也能产生 metric (default_deny)

        baseline_path = str(tmp_path / 'baseline.json')
        suite.save_baseline(baseline_path)

        assert os.path.exists(baseline_path)
        with open(baseline_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert 'scenarios' in data
        assert 'timestamp' in data
        assert len(data['scenarios']) > 0

    def test_load_baseline_from_json(self, seeded_perf_db, tmp_path):
        """从 JSON 文件加载基线"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=5,
        )
        baseline_path = str(tmp_path / 'baseline.json')
        suite.save_baseline(baseline_path)

        # 重新加载
        suite2 = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        loaded = suite2.load_baseline(baseline_path)
        assert loaded is not None
        assert 'scenarios' in loaded
        assert len(loaded['scenarios']) > 0

    def test_check_regression_no_baseline(self, seeded_perf_db):
        """无基线时返回 status=no_baseline"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        result = suite.check_regression(baseline_path='/nonexistent/baseline.json')
        assert result['status'] == 'no_baseline'

    def test_check_regression_with_baseline(self, seeded_perf_db, tmp_path):
        """有基线时检测回归 (阈值内 = ok)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        # 第一次运行 + 保存基线
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=10,
        )
        baseline_path = str(tmp_path / 'baseline.json')
        suite.save_baseline(baseline_path)

        # 第二次运行 + 检测回归 (同样代码, 阈值宽松)
        suite2 = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite2.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=10,
        )
        result = suite2.check_regression(baseline_path=baseline_path, threshold=2.0)
        # 阈值 200% — 同样代码不应触发回归
        assert result['status'] in ['ok', 'regression']
        # 不应有严重回归
        assert len(result.get('regressions', [])) == 0


# ============================================================================
# 5. 性能报告生成
# ============================================================================

class TestPerformanceReportGeneration:
    """性能报告生成 (JSON + Markdown)"""

    def test_generate_report_dict(self, seeded_perf_db):
        """生成性能报告 dict (含 metrics + summary)"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=10,
        )
        suite.benchmark_derive_role(role_id=1, iterations=5)

        report = suite.generate_report()
        assert isinstance(report, dict)
        assert 'name' in report
        assert 'timestamp' in report
        assert 'metrics' in report
        assert 'summary' in report
        assert len(report['metrics']) >= 2
        # summary 包含总场景数
        assert 'scenario_count' in report['summary']

    def test_save_report_to_json_file(self, seeded_perf_db, tmp_path):
        """保存报告到 JSON 文件"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=10,
        )

        report_path = str(tmp_path / 'report.json')
        suite.save_report(report_path)

        assert os.path.exists(report_path)
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert 'metrics' in data
        assert len(data['metrics']) >= 1

    def test_generate_markdown_report(self, seeded_perf_db):
        """生成 Markdown 格式报告"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=10,
        )
        suite.benchmark_derive_role(role_id=1, iterations=5)

        md = suite.generate_markdown_report()
        assert isinstance(md, str)
        assert '# ' in md or '## ' in md  # 含标题
        assert 'check_single' in md or 'derive_role' in md  # 含场景名
        assert '|' in md  # 含表格


# ============================================================================
# 6. 综合场景: 模拟灰度切换前的性能验收
# ============================================================================

class TestGrayscaleReadinessAcceptance:
    """模拟灰度切换前的性能验收门禁 (一站式跑完所有场景)"""

    def test_run_full_acceptance_suite(self, seeded_perf_db, tmp_path):
        """[一站式] 跑完所有性能场景并生成报告"""
        from meta.core.permission_benchmark_suite import PerformanceBenchmarkSuite

        suite = PerformanceBenchmarkSuite(db_path=seeded_perf_db)

        # 准备 Intent 数据
        from meta.core.effective_intent_dao import EffectiveIntentDAO
        dao = EffectiveIntentDAO(seeded_perf_db)
        dao.upsert(
            role_id=1, bo_id='product', action_name='read',
            data_scope={
                'include': [{'field': 'domain_id', 'op': 'IN', 'value': [1, 2]}],
                'exclude': [{'field': 'status', 'op': '=', 'value': 'archived'}],
            },
            derivation_mode='static', source='derived',
        )

        # 运行所有场景
        suite.benchmark_check_single(
            role_id=1, bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=30,
        )
        suite.benchmark_check_multi_role(
            role_ids=[1, 2, 3], bo_id='product', action_name='read',
            record_id=1, user_id=999, iterations=20,
        )
        suite.benchmark_derive_role(role_id=1, iterations=5)
        suite.benchmark_derive_multi_roles(role_ids=[1, 2, 3, 4, 5], iterations=2)

        # 生成报告
        report_path = str(tmp_path / 'acceptance_report.json')
        suite.save_report(report_path)

        # 加载报告验证
        with open(report_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data['metrics']) >= 4  # 至少 4 个场景
        # 所有场景都应有有效的平均值
        for m in data['metrics']:
            assert m['value'] > 0, f"Scenario {m['name']} has zero value"
            assert m['iterations'] > 0

        # 保存基线 (供后续回归检测使用)
        baseline_path = str(tmp_path / 'acceptance_baseline.json')
        suite.save_baseline(baseline_path)
        assert os.path.exists(baseline_path)
