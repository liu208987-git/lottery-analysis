#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes 日报推送脚本（升级版）
===========================
GPT 建议 7 段结构：
  1. 标题
  2. 昨日复盘（含形态/和值/跨度 + 分策略表现 + 最佳策略 + 一句话结论）
  3. 排列三今日预测（核心观察 + Top10 + 共振分档 + 重点关注/备选）
  4. 福彩3D今日预测（同上）
  5. 今日重点关注（双彩种主/辅看一览）
  6. 数据源状态（健康报告）
  7. 风险提示

用法：
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
#  文件读取 & 工具函数
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


def calc_sum(nums: str) -> int:
    """从号码字符串计算和值（如 '835' → 16）"""
    digits = [int(c) for c in nums if c.isdigit()]
    return sum(digits) if len(digits) == 3 else 0


def calc_span(nums: str) -> int:
    """从号码字符串计算跨度（如 '835' → 5）"""
    digits = [int(c) for c in nums if c.isdigit()]
    return max(digits) - min(digits) if len(digits) == 3 else 0


def calc_pattern(nums: str) -> str:
    """从号码字符串判断形态：豹子/组三/组六"""
    digits = [int(c) for c in nums if c.isdigit()]
    if len(digits) != 3:
        return "未知"
    if digits[0] == digits[1] == digits[2]:
        return "豹子"
    if digits[0] == digits[1] or digits[1] == digits[2] or digits[0] == digits[2]:
        return "组三"
    return "组六"


def parse_bool(val: str) -> bool:
    return str(val).strip().lower() in {"true", "1", "yes", "y", "是", "命中", "✅"}


def hot_numbers(win: dict) -> list[str]:
    """从窗口统计提取热号（近10期出现最多的数字）"""
    freq = win.get("全位数字频率", {})
    if not freq:
        return []
    sorted_nums = sorted(freq.items(), key=lambda x: -x[1])
    return [str(k) for k, v in sorted_nums if v >= max(1, len(sorted_nums) / 3)]


def cold_numbers(win: dict) -> list[str]:
    """从窗口统计提取冷号（近期遗漏较长的数字）"""
    omission = win.get("当前遗漏", {})
    if not omission:
        return []
    avg = win.get("平均遗漏", 3)
    return [str(k) for k, v in sorted(omission.items(), key=lambda x: -x[1]) if v and v >= avg]


# ═══════════════════════════════════════════
#  昨日复盘格式化（升级版）
# ═══════════════════════════════════════════

def pick_latest_review(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """每个彩种取最新一期（三策略各一条）"""
    if not rows:
        return []
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


def format_review_section() -> str:
    """
    读取 review_history.csv → 拼接升级版复盘
    格式：
        【排列三 261XX】
        开奖号码：835
        形态：组六｜和值：16｜跨度：5

        策略表现：
        ✅ conservative：命中走势区间
          - 和值预测区间：14-18，实际 16，命中
          - 跨度预测区间：4-6，实际 5，命中
          - 和值差+跨度差：0，昨日最佳策略

        其他策略：
        - default：和值差+跨度差=2
        - aggressive：和值差+跨度差=3

        复盘结论：昨日排列三走势落在中和值、中跨度、组六形态区间，conservative 策略判断最接近。
    """
    rows = pick_latest_review(read_review_csv())
    if not rows:
        return "【昨日复盘】\n暂无复盘数据"

    # 按 (彩种, 期号) 分组
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        lottery = row.get("彩种", "未知")
        issue = row.get("期号", "未知")
        grouped.setdefault((lottery, issue), []).append(row)

    output_parts = ["━━━━━━━━━━━━━━\n一、昨日复盘\n━━━━━━━━━━━━━━"]

    for (lottery, issue), items in sorted(grouped.items()):
        actual = items[0].get("开奖号码", "未知")
        pattern = calc_pattern(actual)
        total = calc_sum(actual)
        span = calc_span(actual)

        output_parts.append(f"\n【{lottery} {issue}】")
        output_parts.append(f"开奖号码：{actual}")
        output_parts.append(f"形态：{pattern}｜和值：{total}｜跨度：{span}")

        # 分策略表现
        strategy_results = []
        best_strategy = ""
        best_score = 9999

        for item in items:
            st = item.get("策略", "default")
            sum_err = int(item.get("Top1和值误差", 99))
            span_err = int(item.get("Top1跨度误差", 99))
            form_ok = parse_bool(item.get("Top1形态一致", ""))
            score = sum_err + span_err
            direct_hit = parse_bool(item.get("直选命中Top30", ""))
            group_hit = parse_bool(item.get("组选命中Top30", ""))

            strategy_results.append({
                "name": st,
                "sum_err": sum_err,
                "span_err": span_err,
                "score": score,
                "form_ok": form_ok,
                "direct_hit": direct_hit,
                "group_hit": group_hit,
            })
            if score < best_score:
                best_score = score
                best_strategy = st

        # 最佳策略详细展示
        best_entry = next((r for r in strategy_results if r["name"] == best_strategy), None)
        if best_entry:
            output_parts.append(f"\n策略表现：")
            hits = []
            if best_entry["direct_hit"]:
                hits.append("直选命中")
            if best_entry["group_hit"]:
                hits.append("组选命中")
            hit_str = f"（{' + '.join(hits)}）" if hits else ""
            output_parts.append(f"✅ {best_strategy}：命中走势区间{hit_str}")
            output_parts.append(f"  - 和值差={best_entry['sum_err']}，跨度差={best_entry['span_err']}")
            output_parts.append(f"  - 和值差+跨度差={best_score}，昨日最佳策略")

        # 其他策略
        others = [r for r in strategy_results if r["name"] != best_strategy]
        if others:
            output_parts.append(f"\n其他策略：")
            for r in others:
                hits_o = []
                if r["direct_hit"]:
                    hits_o.append("直选")
                if r["group_hit"]:
                    hits_o.append("组选")
                hit_o_str = f"（{' + '.join(hits_o)}命中）" if hits_o else "（未命中）"
                output_parts.append(f"- {r['name']}：和值差+跨度差={r['score']}{hit_o_str}")

        # 一句话复盘结论
        sum_comment = "偏低" if total <= 10 else ("偏高" if total >= 20 else "居中")
        span_comment = "小" if span <= 3 else ("大" if span >= 7 else "中")
        output_parts.append(
            f"\n复盘结论：\n"
            f"昨日{lottery}走势落在{'低' if total <= 9 else '中' if total <= 17 else '高'}和值、"
            f"{span_comment}跨度、{pattern}形态区间，"
            f"{best_strategy} 策略判断最接近。"
        )

    return "\n".join(output_parts)


# ═══════════════════════════════════════════
#  今日预测格式化（升级版）
# ═══════════════════════════════════════════

def extract_top10(data: dict, key: str = "Top10号码") -> list[str]:
    summary = data.get("摘要", {})
    nums = summary.get(key, [])
    if nums:
        return [str(x).zfill(3) for x in nums[:10]]
    recommends = data.get("推荐", [])
    result = []
    for item in (recommends or [])[:10]:
        if isinstance(item, dict):
            n = item.get("号码", "")
            if n:
                result.append(str(n).zfill(3))
    return result[:10]


def load_stats_cache(lottery: str) -> dict:
    """加载统计缓存"""
    path = CACHE_DIR / f"{lottery}_stats_latest.json"
    return read_json(path)


def format_observation(stats: dict, label: str, pred_data: dict = None) -> list[str]:
    """生成核心观察文本（紧凑结构版）"""
    if not stats:
        return ["暂无统计缓存"]

    w10 = stats.get("窗口", {}).get("近10期", {})
    w30 = stats.get("窗口", {}).get("近30期", {})
    p5 = stats.get("窗口", {}).get("近5期", {})

    lines = []

    # 和值区间 + 跨度重点（一行搞定）
    high_sum_w10 = w10.get("高频和值", [])
    high_span_w10 = w10.get("高频跨度", [])
    sum_range = w10.get("高频和值区间", "")
    span_mean = w10.get("跨度均值", "?")

    # 结构倾向
    sum_parts = []
    if sum_range:
        sum_parts.append(f"和值区间：{sum_range}")
    if high_sum_w10:
        sum_parts.append(f"参考 {' '.join(str(s) for s in sorted(high_sum_w10)[:8])}")
    span_parts = []
    if high_span_w10:
        span_parts.append(f"跨度重点：{' '.join(str(s) for s in sorted(high_span_w10))}（均值{span_mean}）")

    if sum_parts:
        lines.append("结构倾向：")
        lines.append("  " + "、".join(sum_parts))
    if span_parts:
        lines.append("  " + span_parts[0])

    # 形态倾向
    lines.append("  形态倾向：组六为主，组三少量防守")

    # 冷热观察
    hot = hot_numbers(w10)
    cold = cold_numbers(w10)
    hot_str = f"热号 {' '.join(hot)}" if hot else ""
    cold_str = f"冷号 {' '.join(cold)}" if cold else ""
    if hot_str and cold_str:
        lines.append(f"  冷热：{hot_str} · {cold_str}")
    elif hot_str:
        lines.append(f"  冷热：{hot_str}")
    elif cold_str:
        lines.append(f"  冷热：{cold_str}")

    # 高分区分位数（从预测JSON读取）
    if pred_data:
        s = pred_data.get("摘要", {})
        p95_score = s.get("P95分数线")
        p95_count = s.get("P95候选数")
        if p95_score is not None:
            lines.append(f"  高分区：Top 5% 候选（≥{p95_score}分，{p95_count}注）")

    return lines


def format_prediction_section(lottery: str, label: str) -> str:
    """
    升级版预测格式化：
      核心观察（和值/跨度/形态/冷热）
      Top10 候选
      三策略共振号码
      重点关注 ⭐
      备选关注
    """
    path = PRED_DIR / f"latest_{lottery}.json"
    data = read_json(path)

    if not data:
        return f"【{label} 今日预测】\n暂无预测文件"

    issue = data.get("预测期号", "未知")
    top10 = extract_top10(data)

    # 核心观察
    stats = load_stats_cache(lottery)
    obs_lines = format_observation(stats, label, pred_data=data)

    # 三策略共振
    consensus_nums: dict[str, int] = {}
    for suffix, sname in [("", "default"), ("_conservative", "稳健"), ("_diversity", "多样性")]:
        sp = PRED_DIR / f"latest_{lottery}{suffix}.json"
        sd = read_json(sp)
        if sd:
            for n in extract_top10(sd)[:10]:
                consensus_nums[n] = consensus_nums.get(n, 0) + 1

    consensus = sorted([(n, c) for n, c in consensus_nums.items() if c >= 2],
                       key=lambda x: (-x[1], x[0]))

    # 共振号分档：三策略全命中 vs 仅两策略
    triple = [n for n, c in consensus if c >= 3]
    double = [n for n, c in consensus if c >= 2 and c < 3]

    parts = [
        f"\n━━━━━━━━━━━━━━\n二、{label} 今日预测\n━━━━━━━━━━━━━━",
        f"预测期号：{issue}",
        "",
        "核心观察：",
    ]
    parts.extend("  " + line for line in obs_lines)
    parts.append("")
    parts.append(f"Top10候选：\n{' '.join(top10) if top10 else '暂无'}")

    if triple:
        parts.append(f"\n三策略共振（三策略交集）：\n{' '.join(triple)}")
    if double:
        parts.append(f"三策略共振（两策略交集）：\n{' '.join(double)}")

    # 重点关注（从推荐列表首部 + 共振取交集）
    # 从 default 推荐列表提取评分前几的号码作为"重点关注"
    recommends = data.get("推荐", [])
    top_scores = {}
    for item in (recommends or [])[:30]:
        if isinstance(item, dict):
            n = str(item.get("号码", "")).zfill(3)
            top_scores[n] = item.get("总分", 0)

    # 重点关注 = 三策略共振 + default 评分前15
    primary_candidates = set(triple)
    # 从评分前15抽和共振的交集，如果没有足够，从共振中补
    top15 = list(top_scores.keys())[:15]
    primary = [n for n in triple if n in top15]
    if not primary and triple:
        primary = triple[:3]

    secondary = [n for n in double if n not in primary]
    # 如果 secondary 不够，从 top10 补充不在共振的
    rest_top10 = [n for n in top10 if n not in primary and n not in secondary]
    secondary.extend(rest_top10[:4 - len(secondary)])

    if primary:
        parts.append(f"\n重点关注：\n{' '.join(primary[:3])}")
        # 给出理由
        reasons = []
        for n in primary[:3]:
            item = next((r for r in (recommends or []) if str(r.get("号码", "")).zfill(3) == n), None)
            if item:
                total = item.get("总分", 0)
                pattern = item.get("形态", "?")
                hv = item.get("和值", "?")
                sp = item.get("跨度", "?")
                reasons.append(f"  {n}：总分{total}，{pattern}，和值{hv}，跨度{sp}")
        if reasons:
            parts.append("理由：")
            parts.extend(reasons)

    if secondary:
        parts.append(f"\n备选关注：\n{' '.join(secondary[:5])}")

    return "\n".join(parts)


# ═══════════════════════════════════════════
#  重点关注总表
# ═══════════════════════════════════════════

def build_summary_section() -> str:
    """生成今日重点关注总表"""
    parts = ["━━━━━━━━━━━━━━\n三、今日重点关注\n━━━━━━━━━━━━━━"]

    for lottery, label in [("pls", "排列三"), ("d3", "福彩3D")]:
        path = PRED_DIR / f"latest_{lottery}.json"
        data = read_json(path)
        if not data:
            continue

        top10 = extract_top10(data)

        # 共振
        consensus_nums: dict[str, int] = {}
        for suffix in ["", "_conservative", "_diversity"]:
            sp = PRED_DIR / f"latest_{lottery}{suffix}.json"
            sd = read_json(sp)
            if sd:
                for n in extract_top10(sd)[:10]:
                    consensus_nums[n] = consensus_nums.get(n, 0) + 1

        triple = [n for n, c in sorted(consensus_nums.items(), key=lambda x: (-x[1], x[0])) if c >= 3]
        double = [n for n, c in sorted(consensus_nums.items(), key=lambda x: (-x[1], x[0])) if c >= 2 and c < 3]

        primary = triple[:3] if triple else (double[:3] if double else top10[:3])
        secondary = [n for n in double if n not in primary][:4]
        if not secondary:
            secondary = [n for n in top10 if n not in primary][:4]

        parts.append(f"\n{label}：")
        parts.append(f"主看 {' '.join(primary)}")
        if secondary:
            parts.append(f"辅看 {' '.join(secondary)}")

    return "\n".join(parts)


# ═══════════════════════════════════════════
#  健康报告格式化（保持不变）
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
#  日报拼接（7段结构）
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
        build_summary_section(),
        "",
        format_health_section(),
        "",
        "⚠️ 彩票具有随机性，以上仅供数据分析与复盘参考，不构成投注建议。",
    ]
    text = "\n".join(parts)
    # 微信单条消息上限约 4096 字符，保守截断
    if len(text) > 4000:
        text = text[:4000] + "\n\n……内容过长已截断"
    return text


# ═══════════════════════════════════════════
#  推送 & 落盘 & 去重（保持不变）
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
    parser.add_argument("--stdout", action="store_true",
                        help="只输出日报正文到stdout（供Hermes deliver=origin推送），日志走stderr")
    args = parser.parse_args()

    text = build_daily_message()

    if args.stdout:
        report_path = PUSH_DIR / "daily_report.md"
        write_file(report_path, text)
        h = msg_hash(text)
        if not args.force and already_sent("daily", h):
            print(f"[跳过] 今日已推送过相同内容", file=sys.stderr)
            sys.exit(0)
        append_log("daily", h, True, "hermes deliver=origin")
        print(text)
        sys.exit(0)

    code = send_or_save(text, kind="daily", force=args.force, do_send=not args.write_only)
    sys.exit(code)


if __name__ == "__main__":
    main()
