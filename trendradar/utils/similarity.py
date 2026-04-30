# coding=utf-8
"""
标题相似度工具

提供轻量的模糊匹配能力，用于新闻标题去重。
"""

from difflib import SequenceMatcher
from typing import Iterable, Optional, Tuple


def calculate_similarity(left: str, right: str) -> float:
    """
    计算两个标题的相似度百分比（0-100）。
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 100.0
    return SequenceMatcher(None, left, right).ratio() * 100.0


def find_best_fuzzy_match(
    target: str,
    candidates: Iterable[str],
    threshold: float,
) -> Tuple[Optional[str], float]:
    """
    在候选标题中查找与目标标题最相似的匹配项。
    """
    best_title = None
    best_score = 0.0

    for candidate in candidates:
        score = calculate_similarity(target, candidate)
        if score >= threshold and score > best_score:
            best_title = candidate
            best_score = score

    return best_title, best_score
