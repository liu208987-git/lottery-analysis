#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes 日报推送脚本
==================
只读文件 → 拼接日报 → 落盘 → 推送 → 去重

用法:
    python scripts/hermes_push.py --mode daily           # 正常推送
    python scripts/hermes_push.py --mode daily --force   # 强制补发
    python scripts/hermes_push.py --mode daily --write-only  # 只生成不推送
"""

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parent.parent

PRED_DIR = BASE / "output" / "predictions"
REVIEW_HISTORY = BASE / "output" / "reviews" / "review_history.csv"
REPORT_DIR = BASE / "output" / "reports"
CACHE_DIR = BASE / "data" / "cache"
PUSH_DIR = BASE / "output" / "push"

PUSH_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(CN_TZ)


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def yesterday_str() -> str:
    return (now() - timedelta(days=1)).strftime("%Y-%m-%d")


# ═══════════════════════════════════════════
#  文件读取
# ═══════════════════════════════════════════

def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] JSON 读取失败: {path} | {e}")
        return {}


def read_review_csv() -> list[dict[str, str]]:
    if not REVIEW_HISTORY.exists():
        return []
    try:
        with REVIEW_HISTORY.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"[WARN] review_history 读取失败: {e}")
        return []


# ═══════════════════════════════════════════
#  复盘格式化
# ═══════════════════════════════════════════

def pick_latest_review(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """每个彩种取最新一期（三策略各一条）"""
    if not rows:
        return []

    # 按彩种分组，找最大期号
    latest: dict[str, int] = {}
    for row in rows:
        lottery = row.get("彩种", "")
        issue_str = row.get("期号", "")
        digits = "".join(c for c in issue_str if c.isdigit())
        if not digits:
            continue
        num = int(digits)
        if num > latest.get(lottery, -1):
            latest[lottery] = num

    return [r for r in rows
            if "".join(c for c in r.get("期号", "") if c.isdigit()) == str(latest.get(r.get("彩种", ""), ""))]


def parse_bool(val: str) -> bool:
    return str(val).strip().lower() in {"true", "1", "yes", "y", "是", "命中", "✅"}


def format_review_section() -> str:
    """读取 review_history.csv → 拼接昨日复盘"""
    rows = pick_latest_review(read_review_csv())

    if not rows:
        return "【昨日复盘】\n暂无复盘数据"

    # 按 (彩种, 期号) 分组
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        lottery = row.get("彩种", "未知")
        issue = row.get("期号", "未知")
        grouped.setdefault((lottery, issue), []).append(row)

    lines = ["【昨日复盘】"]

    for (lottery, issue), items in sorted(grouped.items()):
        actual = items[0].get("开奖号码", "未知")

        direct_hits: list[str] = []
        group_hits: list[str] = []
        best_strategy = ""
        best_score = 9999

        for item in items:
            st = item.get("策略", "default")
            if parse_bool(item.get("直选命中Top30", "")):
                direct_hits.append(st)
            if parse_bool(item.get("组选命中Top30", "")):
                group_hits.append(st)
            # 最佳接近策略：和值差+跨度差最小
            sum_d = int(item.get("Top1和值误差", 99))
            span_d = int(item.get("Top1跨度误差", 99))
            score = sum_d + span_d
            if score < best_score:
                best_score = score
                best_strategy = st

        hit_detail = ""
        if group_hits:
            hit_detail += f"；组选命中({','.join(group_hits)})"
        if direct_hits:
            hit_detail += f"；直选命中({','.join(direct_hits)})"

        lines.append(
            f"{lottery} {issue}：开奖 {actual}{hit_detail}；"
            f"最佳策略 {best_strategy}(和值差+跨度差={best_score})"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  预测格式化
# ═══════════════════════════════════════════

def extract_top10(data: dict, key: str = "Top10号码") -> list[str]:
    summary = data.get("摘要", {})
    nums = summary.get(key, [])
    if nums:
        return [str(x).zfill(3) for x in nums[:10]]
    # fallback: 从推荐列表提取
    recommends = data.get("推荐", [])
    result = []
    for item in (recommends or [])[:10]:
        if isinstance(item, dict):
            n = item.get("号码", "")
            if n:
                result.append(str(n).zfill(3))
    return result[:10]


def format_prediction_section(lottery: str, label: str) -> str:
    """读取 latest_{lottery}.json → 拼接预测"""
    path = PRED_DIR / f"latest_{lottery}.json"
    data = read_json(path)

    if not data:
        return f"【{label} 今日预测】\n暂无预测文件"

    issue = data.get("预测期号", "未知")
    top10 = extract_top10(data)

    lines = [
        f"【{label} 今日预测】",
        f"预测期号：{issue}",
        f"Top10：{' '.join(top10) if top10 else '暂无'}",
    ]

    # 多策略共振：读取 conservative/diversity 的 Top10 取交集
    consensus_nums: dict[str, int] = {}
    for suffix, sname in [("", "default"), ("_conservative", "稳健"), ("_diversity", "多样性")]:
        sp = PRED_DIR / f"latest_{lottery}{suffix}.json"
        sd = read_json(sp)
        if sd:
            for n in extract_top10(sd)[:10]:
                consensus_nums[n] = consensus_nums.get(n, 0) + 1

    consensus = [n for n, c in sorted(consensus_nums.items(), key=lambda x: (-x[1], x[0])) if c >= 2]
    if consensus:
        lines.append(f"三策略共振：{' '.join(consensus[:10])}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  健康报告格式化
# ═══════════════════════════════════════════

def is_recent(path: Path, hours: int = 12) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) <= hours * 3600


def format_health_section() -> str:
    """优先读 source_health.json，fallback 到 source_status.json"""
    health_path = REPORT_DIR / "source_health.json"

    if is_recent(health_path):
        data = read_json(health_path)
        if data:
            lines = ["【数据源状态】"]
            for lottery, label in [("pls", "排列三"), ("d3", "福彩3D")]:
                d = data.get(lottery, {}).get("data")
                if d and "error" not in d:
                    lines.append(f"  {label}: 最新 {d['issue']}={d['number']} ({d['total_rows']}期)")
                for src_name, s in data.get(lottery, {}).get("sources", {}).items():
                    cd = s.get("cooldown_until")
                    fails = s.get("failures", 0)
                    rnd = s.get("cooldown_round", 0)
                    if cd:
                        rnd_str = f" 第{rnd}轮" if rnd > 1 else ""
                        lines.append(f"  🔒 {src_name} 冷却中{rnd_str} (HTTP{s.get('last_status','?')})")
                    elif fails > 0:
                        lines.append(f"  ⚠️  {src_name} 失败{fails}次")
                    else:
                        lines.append(f"  ✅ {src_name} 正常")
            q = data.get("quarantine", {})
            if q.get("recent_files", 0) > 0:
                lines.append(f"  ⚠️  隔离区最近24h: {q['recent_files']}条")
            return "\n".join(lines)

    # fallback
    status_path = CACHE_DIR / "source_status.json"
    data = read_json(status_path)
    if not data:
        return "【数据源状态】\n暂无记录"

    lines = ["【数据源状态】"]
    for name, item in data.items():
        cd = item.get("cooldown_until", "")
        fails = item.get("consecutive_failures", 0)
        if cd:
            lines.append(f"  🔒 {name} 冷却至 {cd}")
        elif fails > 0:
            lines.append(f"  ⚠️  {name} 失败 {fails} 次")
        else:
            lines.append(f"  ✅ {name} 正常")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  日报拼接
# ═══════════════════════════════════════════

def build_daily_message() -> str:
    parts = [
        f"📊 每日彩票分析日报｜{today_str()}",
        "",
        format_review_section(),
        "",
        format_prediction_section("pls", "排列三"),
        "",
        format_prediction_section("d3", "福彩3D"),
        "",
        format_health_section(),
        "",
        "⚠️ 彩票具有随机性，以上仅供数据分析与复盘参考，不保证命中。",
    ]
    text = "\n".join(parts)
    # 微信单条消息上限约 4096 字符，保守截断
    if len(text) > 3500:
        text = text[:3500] + "\n\n……内容过长已截断"
    return text


# ═══════════════════════════════════════════
#  推送 & 落盘 & 去重
# ═══════════════════════════════════════════

def msg_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def already_sent(kind: str, h: str) -> bool:
    log_path = PUSH_DIR / "send_log.jsonl"
    if not log_path.exists():
        return False
    today = today_str()
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("date") == today and item.get("kind") == kind and item.get("hash") == h and item.get("ok"):
                return True
    except Exception:
        pass
    return False


def append_log(kind: str, h: str, ok: bool, detail: str = ""):
    log_path = PUSH_DIR / "send_log.jsonl"
    item = {
        "time": now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": today_str(),
        "kind": kind,
        "hash": h,
        "ok": ok,
        "detail": detail,
    }
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 写入发送日志失败: {e}")


def write_file(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[ERROR] 写入失败: {path} | {e}")
        return False


def send_webhook(text: str) -> tuple[bool, str]:
    hermes_url = os.getenv("HERMES_WEBHOOK_URL", "")
    wecom_url = os.getenv("WECOM_WEBHOOK_URL", "")

    if not hermes_url and not wecom_url:
        print(text)
        return True, "no webhook, printed only"

    if wecom_url:
        url = wecom_url
        payload = {"msgtype": "markdown", "markdown": {"content": text}}
    else:
        url = hermes_url
        payload = {"text": text}

    last_err = ""
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                try:
                    body = resp.json()
                    if body.get("errcode", 0) != 0:
                        last_err = f"errcode={body['errcode']} {body.get('errmsg','')}"
                    else:
                        return True, "ok"
                except Exception:
                    return True, "ok"
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(min(60, 5 * attempt * attempt) + random.randint(1, 5))

    return False, last_err


def send_or_save(text: str, kind: str, force: bool = False, do_send: bool = True) -> int:
    h = msg_hash(text)
    report_path = PUSH_DIR / f"{kind}_report.md"
    pending_path = PUSH_DIR / f"pending_{kind}_report.md"

    # 始终落盘
    if not write_file(report_path, text):
        append_log(kind, h, False, "write failed")
        return 3

    # 去重
    if not force and already_sent(kind, h):
        print(f"[跳过] 今日已发送相同 {kind} 消息")
        return 0

    if not do_send:
        print(text)
        append_log(kind, h, True, "write only")
        return 0

    ok, detail = send_webhook(text)
    append_log(kind, h, ok, detail)

    if ok:
        if pending_path.exists():
            pending_path.unlink()
        print(f"[完成] {kind} 推送成功")
        return 0

    write_file(pending_path, text)
    print(f"[失败] {kind} 推送失败，已落盘: {pending_path}")
    print(f"  原因: {detail}")
    return 2


# ═══════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Hermes 日报推送")
    parser.add_argument("--mode", choices=["daily"], default="daily")
    parser.add_argument("--write-only", action="store_true", help="只生成不推送")
    parser.add_argument("--force", action="store_true", help="忽略今日去重，强制发送")
    args = parser.parse_args()

    text = build_daily_message()
    code = send_or_save(text, kind="daily", force=args.force, do_send=not args.write_only)
    sys.exit(code)


if __name__ == "__main__":
    main()
