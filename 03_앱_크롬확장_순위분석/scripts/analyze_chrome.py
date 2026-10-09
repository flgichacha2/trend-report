"""크롬 확장 수집 데이터 분석: 카테고리 통계, 최근 1년 내 등록 확장, AI 확장 비중, 저평점 리뷰 불만 분류.
'first_seen'(=데이터의 [17] 타임스탬프)은 실측상 최초 등록일로 보임(Google 번역 2009, Grammarly 2012 등) → '등록일(추정)'로 사용.
사용법: python analyze_chrome.py [YYYY-MM-DD]
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from complaint_taxonomy import classify  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
DAY = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
pd.set_option("display.width", 250, "display.max_colwidth", 60, "display.max_rows", 300)

d = pd.read_csv(os.path.join(DATA, f"chrome_extensions_{DAY}.csv")).rename(columns={"updated": "registered_est"})
u = d.drop_duplicates("ext_id").copy()
AI_RE = r"(?<![A-Za-z])AI(?![a-z])|GPT|Claude|Gemini|DeepSeek|Copilot|Perplexity|Grok|인공지능|LLM|Agent|에이전트"
u["is_ai"] = u.name.str.contains(AI_RE, regex=True) | u.short_desc.fillna("").str.contains(AI_RE, regex=True)
cut = (date.fromisoformat(DAY) - timedelta(days=365)).isoformat()
u["new_1y"] = u.registered_est >= cut

cat = u.groupby("category").agg(n=("ext_id", "size"), users_median=("users", "median"), rating_mean=("rating", "mean"),
                                 ai_share=("is_ai", "mean"), new_1y=("new_1y", "sum")).sort_values("n", ascending=False)
cat.to_csv(os.path.join(DATA, f"chrome_category_stats_{DAY}.csv"), encoding="utf-8-sig")
print("=== 카테고리 통계 ===\n", cat.round(3).to_string())

yr = u.registered_est.str[:4].value_counts().sort_index()
ai_yr = u[u.is_ai].registered_est.str[:4].value_counts().sort_index()
print("=== 등록연도별 (전체/AI) ===\n", pd.DataFrame({"all": yr, "ai": ai_yr}).fillna(0).astype(int).to_string())

new = u[u.new_1y].sort_values("users", ascending=False)
new[["name", "users", "rating", "rating_count", "category", "registered_est", "source", "source_key", "ext_id"]] \
    .to_csv(os.path.join(DATA, f"chrome_new_1y_{DAY}.csv"), index=False, encoding="utf-8-sig")
print("=== 최근 1년 등록 확장 수:", len(new), "/ AI:", int(new.is_ai.sum()))

big_low = u[(u.users >= 1_000_000) & (u.rating < 4.0)].sort_values("users", ascending=False)
big_low[["name", "users", "rating", "rating_count", "category", "ext_id"]].to_csv(
    os.path.join(DATA, f"chrome_big_lowrated_{DAY}.csv"), index=False, encoding="utf-8-sig")
print("=== 사용자 100만+ & 평점 4.0 미만:", len(big_low))
print(big_low[["name", "users", "rating", "rating_count"]].to_string(index=False))

rp = os.path.join(DATA, f"chrome_low_reviews_{DAY}.csv")
if os.path.exists(rp):
    r = pd.read_csv(rp)
    r["types"] = r.text.fillna("").map(lambda t: "|".join(classify(t)))
    r.to_csv(os.path.join(DATA, f"chrome_low_reviews_classified_{DAY}.csv"), index=False, encoding="utf-8-sig")
    ex = r.assign(type=r.types.str.split("|")).explode("type")
    overall = ex.type.value_counts()
    print("=== 크롬 저평점 리뷰 불만유형 (n=%d) ===\n" % len(r), overall.to_string())
    per = ex.pivot_table(index="name", columns="type", values="star", aggfunc="count", fill_value=0)
    per.insert(0, "n_low", r.groupby("name").size())
    per = per.sort_values("n_low", ascending=False)
    per.to_csv(os.path.join(DATA, f"chrome_complaint_summary_{DAY}.csv"), encoding="utf-8-sig")
    print(per.head(40).to_string())
