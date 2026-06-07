# -*- coding: utf-8 -*-
"""
异步导入服务

为数据导入提供异步执行能力，支持：
- 后台线程执行导入
- 任务状态查询
- 进度回调
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ImportTaskStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass
class ImportTask:
    id: str
    status: ImportTaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_sheets: int = 0
    processed_sheets: int = 0
    current_sheet: Optional[str] = None
    total_rows: int = 0
    processed_rows: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress_callback: Optional[Callable] = None


class AsyncImportService:
    """
    异步导入服务

    提供异步导入能力，使用单线程后台执行。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, ImportTask] = {}
                    cls._instance._task_lock = threading.Lock()
        return cls._instance

    def start_import(
        self,
        import_func: Callable,
        import_args: tuple = (),
        import_kwargs: dict = None,
        progress_callback: Callable = None
    ) -> str:
        """
        启动异步导入任务

        Args:
            import_func: 导入函数（通常是 ImportExportService.import_cascade）
            import_args: 导入函数的位置参数
            import_kwargs: 导入函数的关键字参数
            progress_callback: 进度回调函数

        Returns:
            str: 任务ID
        """
        task_id = str(uuid.uuid4())[:8]
        task = ImportTask(
            id=task_id,
            status=ImportTaskStatus.PENDING,
            created_at=datetime.now(),
            progress_callback=progress_callback
        )

        with self._task_lock:
            self._tasks[task_id] = task

        kwargs = import_kwargs or {}

        def run_import():
            with self._task_lock:
                task = self._tasks.get(task_id)
                if not task:
                    return
                task.status = ImportTaskStatus.RUNNING
                task.started_at = datetime.now()

            try:
                def internal_progress(sheet_name, sheet_idx, total_sheets, row_idx, total_rows):
                    with self._task_lock:
                        t = self._tasks.get(task_id)
                        if t:
                            t.current_sheet = sheet_name
                            t.processed_sheets = sheet_idx
                            t.total_sheets = total_sheets
                            t.processed_rows = row_idx
                            t.total_rows = total_rows

                    if progress_callback:
                        try:
                            progress_callback(task_id, sheet_name, sheet_idx, total_sheets, row_idx, total_rows)
                        except Exception as e:
                            logger.warning(f"[AsyncImport] Progress callback error: {e}")

                kwargs['progress_callback'] = internal_progress

                result = import_func(*import_args, **kwargs)

                with self._task_lock:
                    t = self._tasks.get(task_id)
                    if t:
                        t.status = ImportTaskStatus.COMPLETED
                        t.completed_at = datetime.now()
                        t.result = result

            except Exception as e:
                import traceback
                logger.error(f"[AsyncImport] Task {task_id} failed: {e}\n{traceback.format_exc()}")
                with self._task_lock:
                    t = self._tasks.get(task_id)
                    if t:
                        t.status = ImportTaskStatus.FAILED
                        t.completed_at = datetime.now()
                        t.error = str(e)

        thread = threading.Thread(target=run_import, name=f"import-{task_id}")
        thread.daemon = True
        thread.start()

        logger.info(f"[AsyncImport] Started task {task_id}")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            Optional[Dict]: 任务状态信息，如果任务不存在则返回 None
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            return {
                'id': task.id,
                'status': task.status.value,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'progress': {
                    'total_sheets': task.total_sheets,
                    'processed_sheets': task.processed_sheets,
                    'current_sheet': task.current_sheet,
                    'total_rows': task.total_rows,
                    'processed_rows': task.processed_rows,
                },
                'result': task.result,
                'error': task.error
            }

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务（仅对 PENDING 状态有效）

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.status == ImportTaskStatus.PENDING:
                task.status = ImportTaskStatus.CANCELLED
                task.completed_at = datetime.now()
                logger.info(f"[AsyncImport] Cancelled task {task_id}")
                return True

            return False

    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """
        清理已完成的任务

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        cutoff = datetime.now()
        to_remove = []

        with self._task_lock:
            for task_id, task in self._tasks.items():
                if task.status in (ImportTaskStatus.COMPLETED, ImportTaskStatus.FAILED, ImportTaskStatus.CANCELLED):
                    if task.completed_at:
                        age_hours = (cutoff - task.completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

        if to_remove:
            logger.info(f"[AsyncImport] Cleaned up {len(to_remove)} completed tasks")


async_import_service = AsyncImportService()
