# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class TaskResult:
    success: bool
    data: Any = None
    error: str = None
    tokens_used: int = None
    cost: float = None
    model_used: str = None
    duration_ms: int = None


@dataclass
class TaskExecutionContext:
    task_id: int
    execution_id: int
    trigger_type: str
    tenant_id: Optional[int] = None
    user_id: Optional[int] = None
    ai_session_id: Optional[str] = None
    agent_id: Optional[str] = None
    params: Dict = field(default_factory=dict)


class TaskHandler(ABC):
    
    def __init__(self, data_source=None):
        self.data_source = data_source
    
    @abstractmethod
    def execute(self, params: Dict, context: TaskExecutionContext) -> TaskResult:
        pass
    
    def on_success(self, result: TaskResult, context: TaskExecutionContext):
        pass
    
    def on_failure(self, error: Exception, context: TaskExecutionContext):
        pass
    
    def on_complete(self, result: TaskResult, context: TaskExecutionContext):
        pass