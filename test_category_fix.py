#!/usr/bin/env python
"""测试 Plus/Pro 分类筛选问题"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from account_store import (
    _normalize_account_category,
    ALLOWED_ACCOUNT_CATEGORIES
)


def test_category_normalization():
    print("=== 测试分类规范化 ===")
    test_values = [
        "normal", "普通", "普号",
        "mother", "母号", "team",
        "plus", "Plus", "PLUS",
        "pro", "Pro", "PRO",
        "unknown", ""
    ]
    for val in test_values:
        result = _normalize_account_category(val)
        print(f"  {repr(val)} -> {repr(result)}")


def test_allowed_categories():
    print("\n=== 允许的分类 ===")
    for cat in sorted(ALLOWED_ACCOUNT_CATEGORIES):
        print(f"  {cat}")


def test_filter_match():
    print("\n=== 测试筛选匹配逻辑 ===")
    # 模拟查询场景
    scenarios = [
        ("plus", "plus"),
        ("plus", "normal"),
        ("pro", "pro"),
        ("pro", "normal"),
        ("normal", "normal"),
        ("", "normal"),
    ]

    for filter_cat, record_cat in scenarios:
        print(f"\n  筛选条件: {repr(filter_cat)}")
        print(f"  记录分类: {repr(record_cat)}")

        if filter_cat:
            normalized_filter = _normalize_account_category(filter_cat)
            print(f"  规范化筛选: {repr(normalized_filter)}")
            in_allowed = normalized_filter in ALLOWED_ACCOUNT_CATEGORIES
            print(f"  在允许列表内: {in_allowed}")

            match = normalized_filter == record_cat
            print(f"  是否匹配: {match}")
        else:
            print("  无筛选条件（匹配全部）")


if __name__ == "__main__":
    test_category_normalization()
    test_allowed_categories()
    test_filter_match()
