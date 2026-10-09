"""SQLite에 누적된 일별 순위로 '신규 진입 / 2주 이상 유지 / 이탈' 리포트 생성.

사용법:
    python diff_report.py                 # 최신 수집일 기준
    python diff_report.py --top 100 --hold-days 14
결과: data/diff_report_YYYY-MM-DD.md (+ 같은 이름 .csv)

정의
- 신규 진입: 최신일 TopN에 있으나 직전 lookback(기본 30일) 동안 같은 차트 TopN에 한 번도 없던 앱
- 2주 유지: 최초 등장일로부터 hold-days(14일) 이상 지났고, 그 이후 수집일의 80% 이상에서 TopN 안에 있던 앱
  (광고성 반짝 순위를 거르기 위한 기준)
- 이탈: 직전 수집일엔 있었는데 최신일엔 없는 앱
"""
import argparse
import os
import sqlite3
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "app_ranks.sqlite")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--hold-days", type=int, default=14)
    ap.add_argument("--lookback", type=int, default=30)
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    df = pd.read_sql("SELECT * FROM ranks WHERE rank<=?", con, params=(a.top,))
    if df.empty:
        print("데이터 없음"); return
    dates = sorted(df.collect_date.unique())
    latest = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    since = (date.fromisoformat(latest) - timedelta(days=a.lookback)).isoformat()
    key = ["store", "country", "chart", "genre"]
    out_rows = []
    lines = [f"# 순위 변화 리포트 ({latest})", "",
             f"- 누적 수집일 수: {len(dates)} ({dates[0]} ~ {latest})",
             f"- 기준: Top{a.top}, 신규=최근 {a.lookback}일 내 첫 등장, 유지=첫 등장 후 {a.hold_days}일 이상 & 80% 이상 잔류", ""]
    if len(dates) == 1:
        lines.append("> 수집일이 1일뿐이라 비교 불가. 매일 실행하면 다음 날부터 신규/이탈, 14일 후부터 '2주 유지'가 계산됩니다.")
    for k, g in df.groupby(key):
        cur = g[g.collect_date == latest]
        hist = g[(g.collect_date < latest) & (g.collect_date >= since)]
        if hist.empty:
            continue
        new = cur[~cur.app_id.isin(hist.app_id)]
        dropped = g[(g.collect_date == prev) & (~g.app_id.isin(cur.app_id))] if prev else g.iloc[0:0]
        # 유지 판정
        first = g.groupby("app_id").collect_date.min()
        g_dates = sorted(g.collect_date.unique())
        held = []
        for app_id, fd in first.items():
            if (date.fromisoformat(latest) - date.fromisoformat(fd)).days < a.hold_days or fd <= dates[0]:
                continue  # 첫 수집일부터 있던 앱은 '기존 강자'로 보고 제외
            span = [d for d in g_dates if d >= fd]
            present = g[(g.app_id == app_id)].collect_date.nunique()
            if present / len(span) >= 0.8 and app_id in set(cur.app_id):
                held.append(app_id)
        label = " / ".join(k)
        lines.append(f"## {label}")
        lines.append(f"- 신규 진입 {len(new)}개: " + ", ".join(f"{r['name']}({r['rank']}위)" for _, r in new.sort_values('rank').iterrows()))
        lines.append(f"- 이탈 {len(dropped)}개: " + ", ".join(dropped["name"].head(15)))
        hn = cur[cur.app_id.isin(held)].sort_values("rank")
        lines.append(f"- {a.hold_days}일 이상 유지한 신규 앱 {len(hn)}개: " + ", ".join(f"{r['name']}({r['rank']}위)" for _, r in hn.iterrows()))
        lines.append("")
        for _, r in new.iterrows():
            out_rows.append({**dict(zip(key, k)), "type": "new", "app_id": r.app_id, "name": r["name"], "rank": r["rank"]})
        for _, r in hn.iterrows():
            out_rows.append({**dict(zip(key, k)), "type": "held", "app_id": r.app_id, "name": r["name"], "rank": r["rank"]})
    path = os.path.join(DATA, f"diff_report_{latest}.md")
    with open(path, "w", encoding="utf8") as f:
        f.write("\n".join(lines))
    pd.DataFrame(out_rows).to_csv(path.replace(".md", ".csv"), index=False, encoding="utf-8-sig")
    print("->", path)


if __name__ == "__main__":
    main()
