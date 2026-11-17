"""滤波处理模块

- algorithms: 二维DAS滤波算法（无Qt依赖）
- filter_pipeline: 不可变滤波管道重放机制
- filter_history: 滤波历史与预设管理

DASFilterDialog 已迁移到 ui.filter_panel
"""
from core.filter.algorithms import ALGORITHM_LABELS, apply_das_filter
from .filter_pipeline import FilterStep, FilterPipeline, clone_steps, replay_filter_pipeline
from .filter_history import make_history_entry, add_recent_history, upsert_named_history

__all__ = [
    'ALGORITHM_LABELS', 'apply_das_filter',
    'FilterStep', 'FilterPipeline', 'clone_steps', 'replay_filter_pipeline',
    'make_history_entry', 'add_recent_history', 'upsert_named_history'
]
