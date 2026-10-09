# -*- coding: utf-8 -*-
"""telegram_summary.py 공용 보조 모듈 (네트워크 없음, 표준 라이브러리만 사용).

- 스냅샷 찾기: data/snapshots/YYYYMMDD/summary.json 이 있는 폴더만 '완료된 회차'로 본다.
  최신 회차(cur)와 그보다 앞선 날짜의 마지막 회차(prev)를 고른다.
- 인사이트 항목(Item)을 점수순으로 골라 4개 섹션(🔄 💡 ✅ 📊)으로 렌더링하고,
  1,500자를 넘으면 근거(📊) 줄부터 줄여서 맞춘다.
- 같은 입력이면 항상 같은 출력이 나오도록 hash() 대신 zlib.crc32 를 쓴다.
"""
import argparse
import datetime as dt
import sys
import zlib
from pathlib import Path

MAX_LEN = 1500


def setup_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_args(default_root):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--snap-root", default=str(default_root),
                    help="스냅샷 루트 폴더(테스트용). 기본값: data/snapshots")
    return Path(ap.parse_args().snap_root)


def pick_snapshots(root):
    """(cur, prev) 폴더 반환. 없으면 None."""
    root = Path(root)
    ds = sorted(p for p in root.glob("[0-9]" * 8) if p.is_dir() and (p / "summary.json").exists())
    if not ds:
        return None, None
    cur = ds[-1]
    older = [p for p in ds if p.name < cur.name]
    return cur, (older[-1] if older else None)


def day_ordinal(day_str):
    try:
        return dt.date.fromisoformat(day_str[:10]).toordinal()
    except Exception:
        return 0


def rotate_bonus(key, day_str, span=5, unit=0.1):
    """변화가 없는 날 같은 문구만 반복되지 않도록, 날짜에 따라 결정적으로 순서를 돌리는 가산점."""
    return ((zlib.crc32(key.encode("utf-8")) + day_ordinal(day_str)) % span) * unit


class Item:
    """하나의 인사이트(규칙 1개가 만든 결과). 섹션별 문구는 없으면 None."""

    def __init__(self, key, score, change=None, meaning=None, action=None, evidence=None, kind="general",
                 topic=None, mtopic=None):
        self.key, self.score = key, float(score)
        self.change, self.meaning, self.action, self.evidence = change, meaning, action, evidence
        self.kind = kind  # 'stock' 은 행동 칸에 최대 1개만
        self.topic = topic  # 같은 topic 의 행동은 1개만(비슷한 행동 반복 방지)
        self.mtopic = mtopic  # 같은 mtopic 의 의미 문장은 1개만


def _take(items, attr, limit, kind_limits=None, by_topic=None):
    out, seen, kinds, topics = [], set(), {}, set()
    for it in items:
        v = getattr(it, attr)
        if not v or v in seen:
            continue
        t = getattr(it, by_topic) if by_topic else None
        if t:
            if t in topics:
                continue
            topics.add(t)
        if kind_limits and it.kind in kind_limits:
            if kinds.get(it.kind, 0) >= kind_limits[it.kind]:
                continue
            kinds[it.kind] = kinds.get(it.kind, 0) + 1
        seen.add(v)
        out.append(v)
        if len(out) >= limit:
            break
    return out


def render(title, day, items, n_change=3, n_meaning=2, n_action=3, n_evidence=4, max_len=MAX_LEN):
    items = sorted(items, key=lambda x: (-x.score, x.key))
    sec = {
        "change": _take(items, "change", n_change),
        "meaning": _take(items, "meaning", n_meaning, by_topic="mtopic"),
        "action": _take(items, "action", n_action, {"stock": 1}, by_topic="topic"),
        "evidence": _take(items, "evidence", n_evidence),
    }

    def build():
        out = [f"📌 {title} ({day})"]
        for head, k in [("🔄 무엇이 바뀌었나", "change"), ("💡 무슨 의미", "meaning"),
                        ("✅ 내가 할 일", "action"), ("📊 근거", "evidence")]:
            if sec[k]:
                out.append(head)
                out += [f"• {x}" for x in sec[k]]
        return "\n".join(out)

    text = build()
    # 길면 근거 → 행동(3번째) → 변화(3번째) → 의미(2번째) 순으로 줄인다
    for k, keep in [("evidence", 1), ("action", 2), ("change", 2), ("meaning", 1)]:
        while len(text) > max_len and len(sec[k]) > keep:
            sec[k].pop()
            text = build()
    if len(text) > max_len:
        text = text[:max_len - 1] + "…"
    return text


# ---- 숫자 표기 ----
def n(x):
    return f"{int(round(x)):,}"


def signed(x):
    x = int(round(x))
    return f"+{x:,}" if x >= 0 else f"{x:,}"


def spct(x, d=1):
    """변화율(%) 부호 포함 표기. x 는 % 단위."""
    return f"{x:+.{d}f}%"


def spp(x, d=1):
    """%p 부호 포함 표기."""
    return f"{x:+.{d}f}%p"
