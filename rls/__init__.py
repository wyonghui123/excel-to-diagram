"""
rls - M11 声明式 RLS 加载器

基于实际代码（server.py 18 拦截器）：
- 复用 PermissionInterceptor / DataPermissionInterceptor / FieldPolicyInterceptor
- 本模块仅做 YAML 集中配置 + 缓存 + 公开 API
- 业务代码 0 改动（拦截器层接入）

公开 API：
- get_row_filters(entity, role) -> List[dict]
- get_field_masks(entity, role) -> List[dict]
- get_allowed_actions(entity, role) -> List[str]
- get_loader(rules_dir) -> RLSLoader
- check_action(user_role, entity, action) -> bool
- get_active_row_filter(user_role, entity) -> Optional[str]
- apply_field_masks(user_role, entity, data) -> masked_data
- start_hot_reload(rules_dir, interval=1.0) -> HotReloadWatcher  # [DECORATIVE] v1.3.0
- check_and_reload(rules_dir) -> bool  # [DECORATIVE] v1.3.0

回滚方案：删除 rls_rules/*.yaml 即可（1 秒生效）
"""
import logging
from .loader import (
    RLSLoader,
    get_loader,
    get_row_filters,
    get_field_masks,
    get_allowed_actions,
    clear_cache,
)
from .enforce import (
    check_action,
    get_active_row_filter,
    apply_field_masks,
    apply_field_masks_to_list,
)
from .hot_reload import (
    HotReloadWatcher,
    check_and_reload,
    start_hot_reload,
    stop_hot_reload,
    reset_check_and_reload_state,
)
from .dsl import (
    parse_condition,
    get_row_filter_parsed,
    is_field_reference,
)

logger = logging.getLogger(__name__)

__all__ = [
    # loader
    'RLSLoader',
    'get_loader',
    'get_row_filters',
    'get_field_masks',
    'get_allowed_actions',
    'clear_cache',
    # enforce
    'check_action',
    'get_active_row_filter',
    'apply_field_masks',
    'apply_field_masks_to_list',
    # hot_reload [DECORATIVE] v1.3.0
    'HotReloadWatcher',
    'check_and_reload',
    'start_hot_reload',
    'stop_hot_reload',
    'reset_check_and_reload_state',
    # dsl [DECORATIVE] v1.4.0
    'parse_condition',
    'get_row_filter_parsed',
    'is_field_reference',
]

__version__ = '1.4.0'
