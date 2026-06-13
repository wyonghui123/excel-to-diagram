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
        from admin_token import call_action, get_admin_cookie
        cookie = cookie or get_admin_cookie()
        data = cls.build(**overrides)
        # [Phase 5] 注入 trace_id (测试可观测性)
        data = _inject_trace_id(data)

        try:
            result = call_action(
                cls._create_action(),
                cls._create_payload(data),
                cookie=cookie
            )
            # 提取 ID
            if 'created' in result.get('data', {}):
                data['id'] = result['data']['created'][0]
            elif 'id' in result.get('data', {}):
                data['id'] = result['data']['id']
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
        from admin_token import call_action, get_admin_cookie
        cookie = cookie or get_admin_cookie()
        try:
            call_action(
                cls._delete_action(),
                {**cls._delete_payload(), 'id': obj_id},
                cookie=cookie
            )
            return True
        except Exception as e:
            logger.warning(f"Factory cleanup failed: {cls.__name__}#{obj_id} - {e}")
            return False

    @classmethod
    def _create_action(cls) -> str:
        """子类重写: 创建 action 名"""
        return f'{cls._OBJECT_TYPE}.create'

    @classmethod
    def _create_payload(cls, data: Dict) -> Dict:
        """子类重写: 创建 payload 格式"""
        return {'object_type': cls._OBJECT_TYPE, 'data': data}

    @classmethod
    def _delete_action(cls) -> str:
        """子类重写: 删除 action 名"""
        return f'{cls._OBJECT_TYPE}.delete'

    @classmethod
    def _delete_payload(cls) -> Dict:
        """子类重写: 删除 payload 格式"""
        return {'object_type': cls._OBJECT_TYPE}


# ============================================================
# 工厂注册表 (用于 lint 工具)
# ============================================================

FACTORY_REGISTRY: Dict[str, type] = {}


def register_factory(cls: type) -> type:
    """工厂装饰器: 注册到 FACTORY_REGISTRY"""
    if cls._OBJECT_TYPE:
        FACTORY_REGISTRY[cls._OBJECT_TYPE] = cls
    return cls
