"""수집된 순위 분석: 한국 Top30, 최근 출시앱(6/12개월), 한·미 비교, 카테고리별 상위.
결과: data/analysis_*.csv, 콘솔 요약
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "app_ranks.sqlite")
day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
pd.set_option("display.width", 250, "display.max_colwidth", 40, "display.max_rows", 300)

con = sqlite3.connect(DB)
df = pd.read_sql("SELECT * FROM ranks WHERE collect_date=?", con, params=(day,))

# 출시일/카테고리 메타: iTunes RSS 행에서 app_id별로 취합(마케팅 RSS의 releaseDate도 사용)
meta = (df[df.store.str.startswith("appstore")]
        .sort_values("primary_genre", na_position="last")
        .groupby("app_id").agg(release_date=("release_date", "first"), primary_genre=("primary_genre", "first")))

d6 = (date.fromisoformat(day) - timedelta(days=183)).isoformat()
d12 = (date.fromisoformat(day) - timedelta(days=365)).isoformat()


def top(store, country, chart, genre, n=30):
    x = df[(df.store == store) & (df.country == country) & (df.chart == chart) & (df.genre == genre)].sort_values("rank").head(n)
    if store.startswith("appstore"):
        x = x.drop(columns=["release_date", "primary_genre"]).join(meta, on="app_id")
    return x


# 1) 한국 Top30
kr_ios = top("appstore", "kr", "top-free", "all")
kr_gp = top("gplay", "kr", "top-free", "APPLICATION")
kr_ios[["rank", "name", "developer", "primary_genre", "release_date", "app_id"]].to_csv(os.path.join(DATA, "analysis_kr_ios_top30.csv"), index=False, encoding="utf-8-sig")
kr_gp[["rank", "name", "developer", "score", "app_id"]].to_csv(os.path.join(DATA, "analysis_kr_gplay_top30.csv"), index=False, encoding="utf-8-sig")
print("=== KR iOS Top30 ===");
print(kr_ios[["rank", "name", "primary_genre", "release_date"]].to_string(index=False))
print("=== KR GPlay Top30 ===");
print(kr_gp[["rank", "name", "score", "app_id"]].to_string(index=False))

# 2) 최근 출시(12개월 내) 앱이 상위 100에 있는 경우 (전체 + 카테고리)
ios = df[df.store.str.startswith("appstore")].drop(columns=["release_date", "primary_genre"]).join(meta, on="app_id")
recent = ios[(ios.release_date >= d12) & (ios["rank"] <= 100)].copy()
recent["within6m"] = recent.release_date >= d6
recent = recent.sort_values(["country", "genre", "chart", "rank"])
recent[["store", "country", "chart", "genre", "rank", "name", "developer", "primary_genre", "release_date", "within6m", "app_id"]] \
    .to_csv(os.path.join(DATA, "analysis_recent_release_apps.csv"), index=False, encoding="utf-8-sig")
print("=== 최근 12개월 출시 & Top100 (KR/US) ===")
print(recent.drop_duplicates(["country", "app_id"])[["country", "genre", "chart", "rank", "name", "primary_genre", "release_date"]].to_string(index=False))

# 3) 한·미 비교: 미국 Top100(무료, 전체+카테고리)에 있으나 한국 동일 차트 Top100에 없는 앱
rows = []
for (store, chart, genre), g in df.groupby(["store", "chart", "genre"]):
    us = g[g.country == "us"]; kr = g[g.country == "kr"]
    if us.empty or kr.empty:
        continue
    only_us = us[~us.app_id.isin(kr.app_id) & (us["rank"] <= 50)]
    for _, r in only_us.iterrows():
        rows.append({"store": store, "chart": chart, "genre": genre, "us_rank": r["rank"], "name": r["name"],
                     "developer": r.developer, "app_id": r.app_id,
                     "in_kr_any_chart": r.app_id in set(df[df.country == "kr"].app_id)})
us_only = pd.DataFrame(rows).sort_values(["store", "genre", "us_rank"])
us_only.to_csv(os.path.join(DATA, "analysis_us_only_top50.csv"), index=False, encoding="utf-8-sig")
print("=== 미국 Top50에만 있는 앱 수(카테고리별, 한국 어떤 차트에도 없음) ===")
x = us_only[~us_only.in_kr_any_chart]
print(x.groupby(["store", "genre"]).size().to_string())

# 4) 카테고리별 KR Top10
cat_rows = []
for (store, genre), g in df[(df.country == "kr") & (df.chart == "top-free")].groupby(["store", "genre"]):
    for _, r in g.sort_values("rank").head(10).iterrows():
        cat_rows.append({"store": store, "genre": genre, "rank": r["rank"], "name": r["name"], "app_id": r.app_id})
pd.DataFrame(cat_rows).to_csv(os.path.join(DATA, "analysis_kr_category_top10.csv"), index=False, encoding="utf-8-sig")
print("=== KR 카테고리 Top10 ===")
cr = pd.DataFrame(cat_rows)
for (s, gname), g in cr.groupby(["store", "genre"]):
    print(s, gname, " | ".join(g.name.str[:18]))

# 5) AI 관련 앱 키워드 집계
kw = r"(?<![A-Za-z])AI(?![a-z])|GPT|Claude|Gemini|Perplexity|Copilot|Genspark|Grok|뤼튼|wrtn|에이닷|Manus|Chatbot|인공지능"
ai = df[df.name.str.contains(kw, case=True, regex=True) & (df["rank"] <= 100)]
ai_s = ai.groupby(["country", "store", "app_id"]).agg(name=("name", "first"), best_rank=("rank", "min"), n_charts=("genre", "count")).reset_index().sort_values(["country", "best_rank"])
ai_s_old = ai.groupby(["country", "name"]).agg(best_rank=("rank", "min"), charts=("chart", "nunique"), n=("genre", "count")).reset_index().sort_values(["country", "best_rank"])
ai_s.to_csv(os.path.join(DATA, "analysis_ai_apps.csv"), index=False, encoding="utf-8-sig")
print("=== AI 키워드 앱 ===")
print(ai_s.to_string(index=False))
