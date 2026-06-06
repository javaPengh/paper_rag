"""评测集相关模型与解析入口。

该包向外暴露 golden dataset 的结构化模型和加载函数，供后续 eval CLI、
指标计算和报告输出复用同一套数据入口。
"""

from paper_rag.evaluation.dataset import (
    EvalCase,
    EvalDataset,
    EvalDocument,
    EvalEvidence,
    load_eval_dataset,
)

__all__ = [
    "EvalCase",
    "EvalDataset",
    "EvalDocument",
    "EvalEvidence",
    "load_eval_dataset",
]
