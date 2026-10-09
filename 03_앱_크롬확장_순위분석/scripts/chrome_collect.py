"""크롬 웹스토어 공개 카테고리/컬렉션/검색 페이지에서 확장 목록 수집 + 저평점(1~2점) 리뷰 수집.

페이지 HTML에 내장된 AF_initDataCallback 데이터(ds:N)를 파싱한다(로그인 불필요, 공개 데이터).
리뷰는 웹스토어가 내부적으로 쓰는 공개 RPC(x1DgCd)에 별점 필터를 넣어 조회한다.

사용법:
    python chrome_collect.py                # 목록 수집 + 리뷰 수집
    python chrome_collect.py --no-reviews
결과:
    data/chrome_extensions_YYYY-MM-DD.csv  (확장 목록, 페이지별 순서 포함)
    data/chrome_low_reviews_YYYY-MM-DD.csv (1~2점 리뷰)
    data/app_ranks.sqlite  (chrome_ext 테이블에도 누적)
"""
import argparse
import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timezone

import pandas as pd
import requests
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "app_ranks.sqlite")
BASE = "https://chromewebstore.google.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
SLEEP = 2.0

CATEGORIES = [
    "productivity/communication", "productivity/developer", "productivity/education", "productivity/tools",
    "productivity/workflow", "lifestyle/art", "lifestyle/entertainment", "lifestyle/fun", "lifestyle/games",
    "lifestyle/household", "lifestyle/news", "lifestyle/shopping", "lifestyle/social", "lifestyle/travel",
    "lifestyle/well_being", "make_chrome_yours/accessibility", "make_chrome_yours/functionality",
    "make_chrome_yours/privacy",
]
COLLECTIONS = ["ai_productivity", "ai_content", "2025_favorites", "side_panel", "gmail_extensions",
               "language_learning", "get_started", "dark_mode", "music_extensions"]
SEARCHES = ["AI", "ChatGPT", "요약", "번역", "PDF", "녹음 회의록", "유튜브 요약", "쿠팡", "가격 추적", "자막",
            "스크린샷", "광고 차단", "탭 관리", "메모", "AI agent", "transcript", "Claude", "Gemini"]

ID_RE = re.compile(r"^[a-p]{32}$")
DS_RE = re.compile(r"AF_initDataCallback\(\{key: '(ds:\d+)'.*?data:(.*?), sideChannel: \{\}\}\);</script>", re.S)


def _g(x, i):
    try:
        return x[i]
    except (IndexError, TypeError):
        return None


def parse_items(html):
    items = []
    seen = set()

    def walk(x):
        if isinstance(x, list):
            if x and isinstance(x[0], str) and ID_RE.match(x[0]) and isinstance(_g(x, 2), str) and len(x) > 14:
                if x[0] not in seen:
                    seen.add(x[0])
                    cat = _g(x, 11)
                    ts = _g(_g(x, 17), 0)
                    items.append({
                        "ext_id": x[0], "name": x[2], "rating": _g(x, 3), "rating_count": _g(x, 4),
                        "short_desc": (_g(x, 6) or "")[:200],
                        "category": cat[0] if isinstance(cat, list) else None,
                        "users": _g(x, 14) if isinstance(_g(x, 14), int) else None,
                        "updated": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if isinstance(ts, int) else None,
                    })
                return
            for y in x:
                walk(y)

    for m in DS_RE.finditer(html):
        try:
            walk(json.loads(m.group(2)))
        except Exception:
            pass
    return items


def fetch(url):
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    return r.text


def collect_list(day):
    rows = []
    pages = [("category", c, f"{BASE}/category/extensions/{c}?hl=ko") for c in CATEGORIES]
    pages += [("collection", c, f"{BASE}/collection/{c}?hl=ko") for c in COLLECTIONS]
    pages += [("search", s, f"{BASE}/search/{requests.utils.quote(s)}?hl=ko") for s in SEARCHES]
    for kind, key, url in pages:
        try:
            items = parse_items(fetch(url))
        except Exception as e:
            print("FAIL", url, e); time.sleep(SLEEP); continue
        for i, it in enumerate(items, 1):
            rows.append({"collect_date": day, "source": kind, "source_key": key, "pos": i, **it})
        print(f"{kind}:{key} -> {len(items)}")
        time.sleep(SLEEP)
    return pd.DataFrame(rows)


def low_reviews(ext_id, star, n=50, lang="ko"):
    """lang: 리뷰 언어(ko/en). 웹스토어는 hl과 언어필터에 맞는 리뷰만 반환."""
    inner = [ext_id, [n, None], 2, star, None, [lang]]
    body = {"f.req": json.dumps([[["x1DgCd", json.dumps(inner), None, "generic"]]])}
    r = requests.post(f"{BASE}/_/ChromeWebStoreConsumerFeUi/data/batchexecute?rpcids=x1DgCd&hl={lang}",
                      data=body, headers=UA, timeout=40)
    r.raise_for_status()
    for line in r.text.splitlines():
        if line.startswith('[["wrb.fr"'):
            x = json.loads(line)[0][2]
            if not x:
                return []
            d = json.loads(x)
            out = []
            for rv in (_g(d, 1) or []):
                ts = _g(_g(rv, 4), 0)
                out.append({"ext_id": ext_id, "star": _g(rv, 2), "text": (_g(rv, 3) or "").replace("\n", " ")[:500],
                            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None,
                            "version": _g(rv, 11), "lang": _g(rv, 13)})
            return out
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--no-reviews", action="store_true")
    ap.add_argument("--reviews-only", action="store_true", help="저장된 목록 CSV로 리뷰만 수집")
    ap.add_argument("--review-top", type=int, default=50, help="리뷰 수집 대상 확장 수(사용자수 상위)")
    a = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    list_csv = os.path.join(DATA, f"chrome_extensions_{a.date}.csv")
    if a.reviews_only:
        df = pd.read_csv(list_csv)
    else:
        df = collect_list(a.date)
        df.to_csv(list_csv, index=False, encoding="utf-8-sig")
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM chrome_ext WHERE collect_date=?", (a.date,)) if con.execute(
            "SELECT name FROM sqlite_master WHERE name='chrome_ext'").fetchone() else None
        df.to_sql("chrome_ext", con, if_exists="append", index=False)
        con.commit()
    print("확장 행:", len(df), "고유:", df.ext_id.nunique())
    if a.no_reviews:
        return
    # 리뷰 대상: 사용자 100만 이상 + 평점 4.3 미만 (불만 많은 대형 확장) 우선, 그다음 AI 컬렉션 상위
    u = df.drop_duplicates("ext_id")
    big_low = u[(u.users.fillna(0) >= 300000) & (u.rating.fillna(5) < 4.3)].sort_values("users", ascending=False)
    ai_ids = df[df.source_key.isin(["ai_productivity", "ai_content", "AI", "ChatGPT", "요약", "유튜브 요약", "AI agent"])].ext_id.unique()
    ai = u[u.ext_id.isin(ai_ids)]
    ai = ai.sort_values("users", ascending=False)
    targets = list(dict.fromkeys(list(big_low.ext_id[: a.review_top // 2]) + list(ai.ext_id[: a.review_top // 2])))
    revs = []
    for eid in targets:
        for star in (1, 2):
            for lang in ("ko", "en"):
                try:
                    rs = low_reviews(eid, star, lang=lang)
                except Exception as e:
                    print("FAIL review", eid, e); rs = []
                revs += rs
                time.sleep(SLEEP)
        print("reviews", eid, len(revs), flush=True)
    rv = pd.DataFrame(revs)
    if len(rv):
        rv = rv.merge(u[["ext_id", "name", "users", "rating", "category"]], on="ext_id", how="left")
    rv.to_csv(os.path.join(DATA, f"chrome_low_reviews_{a.date}.csv"), index=False, encoding="utf-8-sig")
    print("저평점 리뷰:", len(rv))


if __name__ == "__main__":
    main()
