#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
期号标准化工具
=============
排列三和福彩3D 期号格式不同但业务序号相同：
  PLS: 26126 → year=2026, seq=126
  D3:  2026126 → year=2026, seq=126

用法:
  from scripts.issue_utils import parse_issue, same_draw_day
"""

from datetime import date, timedelta


def is_pls_format(issue: str) -> bool:
    """5位格式: YYDDD (如 26126)"""
    return bool(issue and issue.strip().isdigit() and len(issue.strip()) == 5)


def is_d3_format(issue: str) -> bool:
    """7位格式: YYYYDDD (如 2026126)"""
    return bool(issue and issue.strip().isdigit() and len(issue.strip()) == 7)


def parse_issue(issue: str) -> dict:
    """
    解析期号 → {year, seq, seq3}

    >>> parse_issue('26126')
    {'year': 2026, 'seq': 126, 'seq3': '126'}
    >>> parse_issue('2026126')
    {'year': 2026, 'seq': 126, 'seq3': '126'}
    """
    s = str(issue).strip()
    if is_d3_format(s):
        year = int(s[:4])
        seq = int(s[4:])
    elif is_pls_format(s):
        year = 2000 + int(s[:2])
        seq = int(s[2:])
    else:
        raise ValueError(f"无法识别的期号格式: {issue!r} (需5位或7位纯数字)")
    if seq < 1 or seq > 366:
        raise ValueError(f"期号序号超出范围: {seq} (1-366)")
    return {"year": year, "seq": seq, "seq3": f"{seq:03d}"}


def same_draw_day(pls_issue: str, d3_issue: str) -> bool:
    """同一天开奖 → 比较 year + seq"""
    p = parse_issue(pls_issue)
    d = parse_issue(d3_issue)
    return p["year"] == d["year"] and p["seq"] == d["seq"]


def to_pls_format(issue: str) -> str:
    """任意格式 → PLS 5位"""
    p = parse_issue(issue)
    return f"{p['year'] % 100:02d}{p['seq']:03d}"


def to_d3_format(issue: str) -> str:
    """任意格式 → D3 7位"""
    p = parse_issue(issue)
    return f"{p['year']}{p['seq']:03d}"


def extract_date_from_issue(issue: str) -> str:
    """期号 → YYYY-MM-DD"""
    p = parse_issue(issue)
    d = date(p["year"], 1, 1) + timedelta(days=p["seq"] - 1)
    return d.strftime("%Y-%m-%d")


def validate_issue(issue: str, lottery: str) -> dict:
    """
    校验期号合法性

    Returns: {'valid': bool, 'reason': str, 'normalized': str|None}
    """
    s = str(issue).strip()
    expected_len = 5 if lottery == 'pls' else 7
    if len(s) != expected_len:
        return {"valid": False, "reason": f"长度应为{expected_len}位", "normalized": None}
    if not s.isdigit():
        return {"valid": False, "reason": "含非数字字符", "normalized": None}
    try:
        parsed = parse_issue(s)
    except ValueError as e:
        return {"valid": False, "reason": str(e), "normalized": None}
    return {"valid": True, "reason": "", "normalized": s}


if __name__ == "__main__":
    # 基本测试
    assert parse_issue("26126") == {"year": 2026, "seq": 126, "seq3": "126"}
    assert parse_issue("2026126") == {"year": 2026, "seq": 126, "seq3": "126"}
    assert same_draw_day("26126", "2026126") is True
    assert same_draw_day("26125", "2026126") is False
    assert to_pls_format("2026126") == "26126"
    assert to_d3_format("26126") == "2026126"

    # 边界测试：年初 001 期
    assert parse_issue("26001") == {"year": 2026, "seq": 1, "seq3": "001"}
    assert parse_issue("2026001") == {"year": 2026, "seq": 1, "seq3": "001"}
    assert same_draw_day("26001", "2026001") is True
    assert same_draw_day("26001", "2026002") is False
    assert to_pls_format("2026001") == "26001"
    assert to_d3_format("26001") == "2026001"
    assert extract_date_from_issue("2026001") == "2026-01-01"

    # 边界测试：年末 365/366 期
    assert parse_issue("26365") == {"year": 2026, "seq": 365, "seq3": "365"}
    assert parse_issue("2026365") == {"year": 2026, "seq": 365, "seq3": "365"}
    assert extract_date_from_issue("2026365") == "2026-12-31"

    # 边界测试：validate_issue
    assert validate_issue("26126", "pls")["valid"] is True
    assert validate_issue("2026126", "d3")["valid"] is True
    assert validate_issue("26126", "d3")["valid"] is False  # 5位给d3
    assert validate_issue("2026126", "pls")["valid"] is False  # 7位给pls
    assert validate_issue("abc", "pls")["valid"] is False

    # 边界测试：跨年比较
    assert same_draw_day("25365", "2026001") is False  # 2025末 ≠ 2026初
    assert parse_issue("25001")["year"] == 2025
    assert parse_issue("2025001")["year"] == 2025

    print("✅ 全部 19 项自测通过")
