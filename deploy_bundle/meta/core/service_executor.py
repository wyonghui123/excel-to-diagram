# -*- coding: utf-8 -*-
r"""
Service Executor — Service BO behaviors 执行器（P2-5 基础）

【背景 2026-06-04】
Spec v1.4 FR-017: Service BO behaviors 真正执行 steps
- 图表展示 = Composite Service (query_version_data → compute_chart_metrics → build_response)
- Service Executor 执行 steps

【当前阶段】
P2-5 提供基础架构：
- AtomicService 抽象
- ServiceRegistry 注册
- ServiceExecutor 调度
- 基础示例 service（query_version_data）

【v1.5+ 待实施】
- 真正连接 DB / API
- 异步执行
- 错误处理 + 重试
- 缓存层
"""
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AtomicService:
    """原子服务定义

    Args:
        id: Service 标识
        name: Service 显示名
        inputs: 输入参数 schema [{'name': 'version_id', 'type': 'string'}]
        outputs: 输出 schema
        handler: 执行函数（None 表示 stub）
    """

    def __init__(
        self,
        id: str,
        name: str,
        inputs: List[Dict[str, Any]],
        outputs: Dict[str, Any],
        handler: Optional[Callable] = None,
    ):
        self.id = id
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.handler = handler

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Service"""
        if self.handler is None:
            logger.debug(f"AtomicService {self.id}: stub execution")
            return {'stub': True, 'service_id': self.id, 'params': params}
        return self.handler(**params)


class ServiceRegistry:
    """Service 注册表（单例）"""

    def __init__(self):
        self._services: Dict[str, AtomicService] = {}

    def register(self, service: AtomicService) -> None:
        """注册 Service"""
        self._services[service.id] = service
        logger.debug(f"Registered atomic service: {service.id}")

    def get(self, service_id: str) -> Optional[AtomicService]:
        """获取 Service"""
        return self._services.get(service_id)

    def list(self) -> List[str]:
        """列出所有 Service ID"""
        return list(self._services.keys())


class ServiceExecutor:
    """Composite Service 执行器（P2-5 基础）

    执行 steps：
    [
        {'service': 'query_version_data', 'params': {'version_id': '$input.version_id'}},
        {'service': 'compute_chart_metrics', 'params': {'data': '$step1.data'}},
    ]
    """

    def __init__(self, registry: Optional[ServiceRegistry] = None):
        self.registry = registry or get_service_registry()

    def execute(
        self,
        composite_steps: List[Dict[str, Any]],
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行 composite steps

        Args:
            composite_steps: steps 列表
            input_params: 初始输入

        Returns:
            最终输出（最后一步的输出）
        """
        input_params = input_params or {}
        step_results = {'input': input_params}
        for i, step in enumerate(composite_steps):
            service_id = step.get('service')
            params = step.get('params') or {}
            # 解析 $input / $step<N> 引用
            params = self._resolve_params(params, step_results)
            service = self.registry.get(service_id)
            if not service:
                logger.error(f"Atomic service not found: {service_id}")
                return {'error': f'service {service_id} not found'}
            try:
                result = service.execute(params)
                step_results[f'step{i+1}'] = result
            except Exception as e:  # noqa: BLE001
                logger.error(f"Step {i+1} failed: {e}")
                return {'error': str(e), 'step': i+1}
        return step_results.get(f'step{len(composite_steps)}', step_results)

    @staticmethod
    def _resolve_params(
        params: Dict[str, Any],
        step_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """解析参数中的 $input.x / $step<N>.x 引用"""
        import copy
        resolved = copy.deepcopy(params)
        for key, value in resolved.items():
            resolved[key] = ServiceExecutor._resolve_value(
                value, step_results,
            )
        return resolved

    @staticmethod
    def _resolve_value(
        value: Any, step_results: Dict[str, Any],
    ) -> Any:
        """解析单个值（字符串形式的引用）"""
        if not isinstance(value, str):
            return value
        # $input.x
        if value.startswith('$input.'):
            path = value[7:]
            return step_results.get('input', {}).get(path)
        # $step<N>.x
        if value.startswith('$step'):
            # 解析 $step1.data 形式
            parts = value[5:].split('.', 1)
            if len(parts) == 2 and parts[0].isdigit():
                step_key = f'step{parts[0]}'
                field = parts[1]
                return step_results.get(step_key, {}).get(field)
        return value


# 单例
_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """获取全局 service registry"""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
        _register_default_services(_registry)
    return _registry


def _register_default_services(registry: ServiceRegistry) -> None:
    """注册默认 atomic services（图表展示场景）"""
    # query_version_data
    registry.register(AtomicService(
        id='query_version_data',
        name='查询版本数据',
        inputs=[{'name': 'version_id', 'type': 'string'}],
        outputs={'data': 'object'},
        # handler 在 v1.5+ 实施真正 DB 查询
    ))
    # compute_chart_metrics
    registry.register(AtomicService(
        id='compute_chart_metrics',
        name='计算图表指标',
        inputs=[
            {'name': 'data', 'type': 'object'},
            {'name': 'chart_type', 'type': 'string'},
        ],
        outputs={'metrics': 'object'},
    ))
    # chart_render
    registry.register(AtomicService(
        id='chart_render',
        name='渲染图表',
        inputs=[
            {'name': 'metrics', 'type': 'object'},
            {'name': 'chart_type', 'type': 'string'},
        ],
        outputs={'config': 'object'},
    ))
