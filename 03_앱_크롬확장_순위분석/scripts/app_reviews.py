"""주요 상위·신규 앱의 리뷰 수집(앱스토어 RSS + 구글플레이) → 1~2점 리뷰 불만유형 키워드 분류.

사용법: python app_reviews.py [YYYY-MM-DD]
결과:
    data/app_reviews_raw_YYYY-MM-DD.csv     (전체 리뷰: 앱, 스토어, 별점, 날짜, 본문)
    data/app_low_reviews_classified_YYYY-MM-DD.csv (1~2점 + 불만유형)
    data/app_complaint_summary_YYYY-MM-DD.csv     (앱 x 불만유형 건수)
리뷰 작성자 이름은 저장하지 않음.
"""
import os
import sys
import time
from datetime import date

import pandas as pd
import requests
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gplay  # noqa: E402
from complaint_taxonomy import classify  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
DAY = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
SLEEP = 1.5

# (표시이름, 그룹, iOS id, 구글플레이 id)  — 2026-10-09 한국 상위권/신규 출시 앱 중심
TARGETS = [
    ("ChatGPT", "AI 비서", "6448311069", "com.openai.chatgpt"),
    ("Claude", "AI 비서", "6473753684", "com.anthropic.claude"),
    ("Google Gemini", "AI 비서", "6477489729", "com.google.android.apps.bard"),
    ("PDF ProX(구글플레이 1위)", "문서/PDF", None, "com.trusted.pdfeditor.pdfreader"),
    ("한글 뷰어 편집기(HWP)", "문서/PDF", "6808507107", "com.hwpviewer.hwp"),
    ("TeraBox", "클라우드", "1509453185", "com.dubox.drive"),
    ("하나은행(신 하나원큐)", "금융", "6743190232", "com.hanabank.oqf"),
    ("하나증권V(NEW)", "금융", None, "com.hanasec.pro"),
    ("NetShort(숏폼드라마)", "숏폼드라마", "6504849169", "com.netshort.abroad"),
    ("DramaBox(숏폼드라마)", "숏폼드라마", "6445905219", "com.storymatrix.drama"),
    ("101cam(필름카메라)", "카메라", "6781998623", None),
    ("유니브 AI(강의녹음 요약)", "AI 학습", "6754797367", "com.ai.univai"),
    ("널스메이트(간호사 AI)", "AI 업무", "6783877557", None),
    ("카카오톡", "메신저", "362057947", "com.kakao.talk"),
    ("쿠팡", "쇼핑", "454434967", "com.coupang.mobile"),
    ("네이버플러스 스토어", "쇼핑", "6738063154", "com.navercorp.navershopping"),
    ("당근", "커뮤니티", "1018769995", "com.towneers.www"),
    ("대한민국 모바일 신분증", "공공", "1599450372", "kr.go.mobileid"),
    ("Notion", "생산성", "1232780281", "notion.id"),
    ("네이버 파파고", "번역", None, "com.naver.labs.translator"),
    ("폴센트(최저가 알림)", "쇼핑도구", "1638569789", "com.deaguowl.fallcent"),
    ("쇼포트(AI 쇼핑비서)", "쇼핑도구", "6757226599", None),
    ("스픽(AI 영어회화)", "AI 학습", "1286609883", "com.selabs.speak"),
    ("LockDay(투두)", "생산성", "6812144044", None),
]


def ios_reviews(app_id, country="kr", pages=5):
    out = []
    for p in range(1, pages + 1):
        url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={p}/id={app_id}/sortby=mostrecent/json"
        try:
            d = requests.get(url, timeout=30).json()
        except Exception as e:
            print("FAIL", url, e); break
        ent = d.get("feed", {}).get("entry", [])
        if isinstance(ent, dict):
            ent = [ent]
        ent = [e for e in ent if "im:rating" in e]
        if not ent:
            break
        for e in ent:
            out.append({"score": int(e["im:rating"]["label"]), "title": e.get("title", {}).get("label", ""),
                        "text": e.get("content", {}).get("label", ""), "date": (e.get("updated", {}).get("label") or "")[:10],
                        "version": e.get("im:version", {}).get("label")})
        time.sleep(SLEEP)
    return out


def main():
    rows = []
    for name, grp, ios, gp in TARGETS:
        if ios:
            for r in ios_reviews(ios):
                rows.append({"app": name, "group": grp, "store": "appstore", **r})
        if gp:
            try:
                rs = gplay.reviews(gp, "kr", "ko", sort=2, num=200)
            except Exception as e:
                print("FAIL gplay", gp, e); rs = []
            for r in rs:
                rows.append({"app": name, "group": grp, "store": "gplay", "score": r["score"], "title": "",
                             "text": r["text"] or "", "date": r["date"], "version": r["version"]})
            time.sleep(SLEEP)
        print(name, sum(1 for x in rows if x["app"] == name), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(DATA, f"app_reviews_raw_{DAY}.csv"), index=False, encoding="utf-8-sig")
    low = df[df.score <= 2].copy()
    low["types"] = (low.title.fillna("") + " " + low.text.fillna("")).map(lambda t: "|".join(classify(t)))
    low.to_csv(os.path.join(DATA, f"app_low_reviews_classified_{DAY}.csv"), index=False, encoding="utf-8-sig")
    ex = low.assign(type=low.types.str.split("|")).explode("type")
    summ = ex.pivot_table(index="app", columns="type", values="score", aggfunc="count", fill_value=0)
    tot = df.groupby("app").agg(total=("score", "size"), low=("score", lambda s: (s <= 2).sum()), avg=("score", "mean"))
    summ = tot.join(summ).fillna(0)
    summ.to_csv(os.path.join(DATA, f"app_complaint_summary_{DAY}.csv"), encoding="utf-8-sig")
    print(summ.to_string())


if __name__ == "__main__":
    main()
