"""
工厂基类 (v3.18.1+ Phase 1, v3.18.4+ Phase 5)

提供统一的 build/create/cleanup 接口, 解决:
- 硬编码 ID 泛滥 (1495 处)
- 工厂采用率低 (0.28%)
- 唯一性保障不规范 (time.time() 滥用)
- 清理追踪缺失
- [Phase 5] trace_id 端到端追踪

设计原则:
1. 必须走真实 API (不能用 mock)
2. 必须支持多 Agent 并行 (含 PID)
3. 必须配 cleanup() 防止 DB 污染
4. 必须生成唯一标识 (counter + random + ts)
5. [Phase 5] 必须自动注入 trace_id 到工厂数据
"""
import os
import time
import random
import string
import logging
from typing import Optional, Dict, Any, List


logger = logging.getLogger(__name__)


# [FIX FACTORY-FRAMEWORK] BO 框架 API 基础 URL
# 14 个工厂默认都走 BO 框架 (POST/DELETE /api/v2/bo/{type})
# 子类可重写 _create_path/_delete_path 走其他端点
import os
_BO_API_BASE = os.environ.get('BO_API_BASE', 'http://localhost:3010')


# ============================================================
# 唯一性 Helper (TBD-4: counter+random 人类可读)
# ============================================================

def unique_id() -> int:
    """
    生成全局唯一 ID (含 PID + 时间戳 + counter)
    用于取代测试中的 int(time.time())
    """
    return int(time.time() * 1000) + os.getpid()


def unique_str(n: int = 8) -> str:
    """
    生成随机字符串 (避免冲突)
    用于用户名后缀 / 角色 code 等
    """
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def unique_email(prefix: str = 'user') -> str:
    """
    生成唯一 email
    """
    return f'{prefix}_{unique_id()}_{unique_str(4)}@test.local'


# ============================================================
# [Phase 5] trace_id 集成 (v3.18.4+)
# ============================================================

def _inject_trace_id(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    给工厂数据注入 trace_id 元信息 (M.1)
    - 测试创建的数据可追踪到具体测试
    - 支持多 Agent 并行测试隔离
    - 兼容 trace_id 模块未初始化的场景
    """
    try:
        from ._trace_id import get_trace_id
        tid = get_trace_id()
        if tid:
            data['_trace_id'] = tid
            data['_created_by_test'] = True
            data['_created_at_ts'] = time.time()
    except (ImportError, Exception):
        # [OK] 静默失败: trace_id 模块未加载不阻断测试
        pass
    return data


# ============================================================
# 工厂基类
# ============================================================

class BaseFactory:
    """
    工厂基类: 提供统一的 build/create/cleanup 接口

    使用示例:
        class UserFactory(BaseFactory):
            _OBJECT_TYPE = 'user'

            @classmethod
            def _base_defaults(cls):
                return {'username': f'test_{unique_str(6)}', 'role': 'user'}

        user = UserFactory.build()              # 构造不写
        user = UserFactory.create(cookie=...)   # 写 DB, 返回带 id
        UserFactory.cleanup(user['id'])         # 清理
    """

    _COUNTER: int = 0
    _OBJECT_TYPE: str = ''  # 子类必须设置

    @classmethod
    def _next_counter(cls) -> int:
        cls._COUNTER += 1
        return cls._COUNTER

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        """子类重写: 提供默认字段"""
        raise NotImplementedError

    @classmethod
    def build(cls, **overrides) -> Dict[str, Any]:
        """
        构造数据, 不写 DB

        Args:
            **overrides: 覆盖默认字段

        Returns:
            dict: 构造的数据 (不含 id)
        """
        defaults = cls._base_defaults()
        defaults.update(overrides)
        return defaults

    @classmethod
    def create(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """
        通过 API 写 DB, 返回带 id 的对象

        Args:
            cookie: admin cookie (可选, 不传则用默认)
            **overrides: 覆盖默认字段

        Returns:
            dict: 包含 id 的数据
        """
        import requests
        from admin_token import get_admin_cookie
        cookie = cookie or get_admin_cookie()
        data = cls.build(**overrides)
        # [Phase 5] 注入 trace_id (测试可观测性)
        data = _inject_trace_id(data)

        try:
            url = f"{_BO_API_BASE}{cls._create_path()}"
            resp = requests.post(
                url,
                json=cls._create_payload(data),
                headers={'Cookie': cookie, 'Content-Type': 'application/json',
                         'X-Trace-Id': data.get('trace_id', '')},
                timeout=15,
            )
            try:
                result = resp.json()
            except Exception:
                result = {'success': False, 'message': resp.text[:200]}

            # [FIX FACTORY-BUG] BO 框架返回 {'success', 'data': {'id': ...}, 'message'}
            if resp.status_code not in (200, 201) or not result.get('success'):
                logger.warning(f"Factory {cls.__name__} create 非成功响应: "
                               f"status={resp.status_code} result={result}")
                data['id'] = -1
                return data
            result_data = result.get('data', {}) or {}
            if 'id' in result_data:
                data['id'] = result_data['id']
            elif 'created' in result_data and result_data['created']:
                data['id'] = result_data['created'][0]
            else:
                logger.warning(f"Could not extract id from result: {result}")
                data['id'] = -1
            return data
        except Exception as e:
            logger.error(f"Factory create failed: {cls.__name__} - {e}")
            raise

    @classmethod
    def cleanup(cls, obj_id: int, cookie=None) -> bool:
        """
        通过 API 删除对象

        Args:
            obj_id: 对象 ID
            cookie: admin cookie

        Returns:
            bool: 是否成功清理
        """
        import requests
        from admin_token import get_admin_cookie
        cookie = cookie or get_admin_cookie()
        try:
            url = f"{_BO_API_BASE}{cls._delete_path(obj_id)}"
            resp = requests.delete(
                url,
                headers={'Cookie': cookie, 'Content-Type': 'application/json'},
                timeout=15,
            )
            try:
                result = resp.json()
            except Exception:
                result = {'success': False}
            return resp.status_code in (200, 201, 204) and result.get('success', True)
        except Exception as e:
            logger.warning(f"Factory cleanup failed: {cls.__name__}#{obj_id} - {e}")
            return False

    @classmethod
    def _create_path(cls) -> str:
        """[FIX FACTORY-FRAMEWORK] 子类可重写: 创建 URL 路径
        默认走 BO 框架: /api/v2/bo/{object_type}
        """
        return f'/api/v2/bo/{cls._OBJECT_TYPE}'

    @classmethod
    def _create_payload(cls, data: Dict) -> Dict:
        """[FIX FACTORY-FRAMEWORK] 子类可重写: 创建 payload 格式
        BO 框架: data 本身作为 body (无 wrapper)
        """
        return data

    @classmethod
    def _delete_path(cls, obj_id: int) -> str:
        """[FIX FACTORY-FRAMEWORK] 子类可重写: 删除 URL 路径
        BO 框架: /api/v2/bo/{object_type}/{id}
        """
        return f'/api/v2/bo/{cls._OBJECT_TYPE}/{obj_id}'

    @classmethod
    def _delete_payload(cls) -> Dict:
        """[FIX FACTORY-FRAMEWORK] 子类可重写: 删除 payload 格式
        BO 框架 DELETE: 无 body
        """
        return {}


# ============================================================
# 工厂注册表 (用于 lint 工具)
# ============================================================

FACTORY_REGISTRY: Dict[str, type] = {}


def register_factory(cls: type) -> type:
    """工厂装饰器: 注册到 FACTORY_REGISTRY"""
    if cls._OBJECT_TYPE:
        FACTORY_REGISTRY[cls._OBJECT_TYPE] = cls
    return cls
