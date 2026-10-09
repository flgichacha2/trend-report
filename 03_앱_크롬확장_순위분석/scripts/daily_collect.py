"""매일 1회 실행: 앱스토어(한국/미국) + 구글플레이(한국/미국) 순위를 수집해 SQLite에 누적.

사용법:
    python daily_collect.py            # 오늘 날짜로 수집
    python daily_collect.py --skip-gplay
결과:
    data/raw/YYYY-MM-DD/*.json  (원본)
    data/app_ranks.sqlite       (ranks 테이블, collect_date 기준 누적)
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import date

import requests
try:
    import truststore  # 사내망 SSL 프록시 대응
    truststore.inject_into_ssl()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gplay  # noqa: E402

ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
DB = os.path.join(DATA, "app_ranks.sqlite")
UA = {"User-Agent": "Mozilla/5.0 (trend-research; personal use)"}
SLEEP = 1.5

COUNTRIES = ["kr", "us"]
ITUNES_GENRES = {  # 앱스토어 카테고리 id
    "6007": "생산성", "6015": "금융", "6017": "교육", "6002": "유틸리티",
    "6013": "건강및피트니스", "6000": "비즈니스", "6012": "라이프스타일", "6016": "엔터테인먼트",
    "6008": "사진및비디오", "6005": "소셜네트워킹", "6024": "쇼핑",
}
GPLAY_CATS = ["APPLICATION", "PRODUCTIVITY", "FINANCE", "EDUCATION", "TOOLS",
              "HEALTH_AND_FITNESS", "BUSINESS", "LIFESTYLE", "SHOPPING", "PHOTOGRAPHY"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranks(
  collect_date TEXT, store TEXT, country TEXT, chart TEXT, genre TEXT,
  rank INTEGER, app_id TEXT, name TEXT, developer TEXT,
  release_date TEXT, primary_genre TEXT, score REAL,
  PRIMARY KEY(collect_date, store, country, chart, genre, rank)
);
CREATE INDEX IF NOT EXISTS ix_ranks_app ON ranks(app_id, store, country);
"""


def get_json(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def save_raw(day, name, obj):
    d = os.path.join(DATA, "raw", day)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False)


def collect_apple(day):
    rows = []
    # 1) 애플 마케팅 RSS (top-free / top-paid 100)
    for c in COUNTRIES:
        for chart in ["top-free", "top-paid"]:
            url = f"https://rss.applemarketingtools.com/api/v2/{c}/apps/{chart}/100/apps.json"
            try:
                d = get_json(url)
            except Exception as e:
                print("FAIL", url, e); continue
            save_raw(day, f"apple_{c}_{chart}", d)
            for i, a in enumerate(d["feed"]["results"], 1):
                rows.append((day, "appstore", c, chart, "all", i, a["id"], a["name"], a.get("artistName"),
                             a.get("releaseDate"), None, None))
            time.sleep(SLEEP)
    # 2) iTunes RSS (전체 200 + 카테고리별 200, 출시일/카테고리 포함)
    for c in COUNTRIES:
        for gid in ["all"] + list(ITUNES_GENRES):
            for chart, feed in [("top-free", "topfreeapplications")] + ([("top-grossing", "topgrossingapplications")] if gid == "all" else []):
                g = "" if gid == "all" else f"/genre={gid}"
                url = f"https://itunes.apple.com/{c}/rss/{feed}/limit=200{g}/json"
                try:
                    d = get_json(url)
                except Exception as e:
                    print("FAIL", url, e); continue
                save_raw(day, f"itunes_{c}_{chart}_{gid}", d)
                for i, e in enumerate(d.get("feed", {}).get("entry", []) or [], 1):
                    rows.append((day, "appstore_itunes", c, chart, gid, i,
                                 e["id"]["attributes"]["im:id"], e["im:name"]["label"],
                                 e.get("im:artist", {}).get("label"),
                                 (e.get("im:releaseDate", {}).get("label") or "")[:10],
                                 e.get("category", {}).get("attributes", {}).get("label"), None))
                time.sleep(SLEEP)
    return rows


def collect_gplay(day):
    rows = []
    for c in COUNTRIES:
        lang = "ko" if c == "kr" else "en"
        for cat in GPLAY_CATS:
            charts = ["top_free", "top_paid", "top_grossing"] if cat == "APPLICATION" else ["top_free"]
            for ch in charts:
                apps = []
                for attempt in range(4):  # 구글플레이는 간헐적으로 빈 응답을 주므로 재시도
                    try:
                        apps = gplay.top_chart(ch, cat, c, lang, num=200 if cat == "APPLICATION" else 100)
                    except Exception as e:
                        print("FAIL gplay", c, cat, ch, e)
                    if len(apps) >= 20 or (ch == "top_paid" and apps):
                        break
                    time.sleep(SLEEP * (attempt + 2))
                print(f"gplay {c} {cat} {ch}: {len(apps)}", flush=True)
                if not apps:
                    continue
                save_raw(day, f"gplay_{c}_{ch}_{cat}", apps)
                for a in apps:
                    rows.append((day, "gplay", c, ch.replace("_", "-"), cat, a["rank"], a["appId"], a["title"],
                                 a["developer"], None, None, a["score"]))
                time.sleep(SLEEP)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--skip-gplay", action="store_true")
    ap.add_argument("--skip-apple", action="store_true")
    a = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    rows = []
    if not a.skip_apple:
        rows += collect_apple(a.date)
    if not a.skip_gplay:
        rows += collect_gplay(a.date)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.executemany("INSERT OR REPLACE INTO ranks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM ranks WHERE collect_date=?", (a.date,)).fetchone()[0]
    print(f"[{a.date}] 저장 {len(rows)}행 (DB 내 해당일 {n}행) -> {DB}")


if __name__ == "__main__":
    main()
