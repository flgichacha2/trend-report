"""Google Play 차트/리뷰 수집 (google-play-scraper(node) v9.1.1의 batchexecute 요청을 Python으로 이식).
설치된 google-play-scraper-py 는 Windows에서 npm 호출 문제로 동작하지 않아 직접 구현.
"""
import json
import os
import time
from datetime import datetime, timezone

import requests
try:
    import truststore  # 사내망 SSL 프록시 대응(윈도우 인증서 저장소 사용)
    truststore.inject_into_ssl()
except Exception:
    pass

BASE = "https://play.google.com"
HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}
COLLECTIONS = {"top_free": "topselling_free", "top_paid": "topselling_paid", "top_grossing": "topgrossing"}


def _path(obj, path):
    try:
        for p in path:
            obj = obj[p]
        return obj
    except (IndexError, KeyError, TypeError):
        return None


def _parse_batch(text):
    for line in text.splitlines():
        if line.startswith('[["wrb.fr"'):
            inp = json.loads(line)
            return json.loads(inp[0][2]) if inp[0][2] else None
    return None


def top_chart(collection="top_free", category="APPLICATION", country="kr", lang="ko", num=100):
    tpl = open(os.path.join(HERE, "gplay_list_body.tpl"), encoding="utf8").read()
    body = tpl.replace("{num}", str(num)).replace("{collection}", COLLECTIONS[collection]).replace("{category}", category)
    url = (f"{BASE}/_/PlayStoreUi/data/batchexecute?rpcids=vyAe2&source-path=%2Fstore%2Fapps"
           f"&f.sid=-4178618388443751758&bl=boq_playuiserver_20220612.08_p0&authuser=0&soc-app=121"
           f"&soc-platform=1&soc-device=1&_reqid=82003&rt=c&hl={lang}&gl={country}")
    r = requests.post(url, data=body.encode(), headers=UA, timeout=30)
    r.raise_for_status()
    obj = _parse_batch(r.text)
    apps = _path(obj, [0, 1, 0, 28, 0]) or []
    out = []
    for i, a in enumerate(apps, 1):
        out.append({
            "rank": i,
            "title": _path(a, [0, 3]),
            "appId": _path(a, [0, 0, 0]),
            "developer": _path(a, [0, 14]),
            "score": _path(a, [0, 4, 1]),
            "price": (_path(a, [0, 8, 1, 0, 0]) or 0) / 1e6,
            "summary": _path(a, [0, 13, 1]),
        })
    return out


def reviews(app_id, country="kr", lang="ko", sort=2, num=150):
    """sort: 1=도움순, 2=최신순, 3=평점순"""
    body = (f"f.req=%5B%5B%5B%22UsvDTd%22%2C%22%5Bnull%2Cnull%2C%5B2%2C{sort}%2C%5B{num}%2Cnull%2Cnull%5D%2Cnull%2C%5B%5D%5D"
            f"%2C%5B%5C%22{app_id}%5C%22%2C7%5D%5D%22%2Cnull%2C%22generic%22%5D%5D%5D")
    url = (f"{BASE}/_/PlayStoreUi/data/batchexecute?rpcids=UsvDTd&f.sid=-697906427155521722"
           f"&bl=boq_playuiserver_20190903.08_p0&hl={lang}&gl={country}&authuser&soc-app=121"
           f"&soc-platform=1&soc-device=1&_reqid=1065213")
    r = requests.post(url, data=body.encode(), headers=UA, timeout=30)
    r.raise_for_status()
    obj = _parse_batch(r.text)
    out = []
    for rv in ((obj or [None])[0] or []):
        ts = _path(rv, [5, 0])
        out.append({
            "id": _path(rv, [0]),
            "score": _path(rv, [2]),
            "text": _path(rv, [4]),
            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else None,
            "version": _path(rv, [10]),
            "thumbsUp": _path(rv, [6]),
        })
    return out


if __name__ == "__main__":
    for x in top_chart(num=10):
        print(x["rank"], x["title"], x["appId"], x["score"])
    time.sleep(1)
    rv = reviews("com.kakao.talk", num=5)
    print([ (r["score"], (r["text"] or "")[:30]) for r in rv])
