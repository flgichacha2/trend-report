# -*- coding: utf-8 -*-
"""
보고서용 분석: data/raw/months/*.csv.gz -> data/processed/
  python -I -X utf8 scripts\\analyze.py [--end 2026-10-10]

산출물
- cat_summary.csv      : 분야별(키워드) 건수·금액, 전년 같은 기간 대비 증감
- cat_monthly.csv      : 분야×월 건수/금액(올해·작년)
- org_type.csv         : 발주기관 유형별(중앙부처/지자체/교육청·학교/공공기관)
- org_type_cat.csv     : 기관유형×관심분야 건수
- band.csv             : 금액대별 분포
- top20_amount.csv     : 금액 큰 사전규격 Top20(최근 6개월)
- top_focus.csv        : AI·보안·클라우드·개인정보 분야 금액 Top15
- top_orgs_focus.csv   : AI·보안 사전규격을 많이 낸 기관 Top15
- watch_region.csv     : 관심지역 기관의 사전규격
- baseline.json        : 텔레그램 요약용 기준값(최근 30일·6개월 분야 비율 등)
- tables.md            : 보고서에 붙일 표(마크다운)
"""
import argparse, datetime as dt, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from common import RAW, PROC, cats, org_type, band, BANDS, FOCUS, CATS, WATCH, sido_of
import re

sys.stdout.reconfigure(encoding="utf-8")


def load_all():
    fs = sorted(glob.glob(str(RAW / "months" / "*.csv.gz")))
    df = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in fs], ignore_index=True)
    df = df.drop_duplicates("id")
    df = df[~df.org.str.contains("테스트기관")]
    df["amount"] = pd.to_numeric(df.amount, errors="coerce").fillna(0)
    df["d"] = pd.to_datetime(df.date, format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["d"])
    df["ym"] = df.d.dt.strftime("%Y-%m")
    df["cats"] = df.title.map(cats)
    df["otype"] = df.org.map(org_type)
    df["band"] = df.amount.map(band)
    return df


def enrich(df):
    return df


def eok(x):
    return round(x / 1e8, 1)


def md(df, cols=None):
    cols = cols or list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df[cols].iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def cat_table(cur, prev):
    rows = []
    for n, _ in CATS:
        c = cur[cur.cats.map(lambda x: n in x)]; p = prev[prev.cats.map(lambda x: n in x)]
        rows.append({"분야": n, "건수": len(c), "비율%": round(len(c) / len(cur) * 100, 2),
                     "금액(억)": eok(c.amount.sum()), "중앙값(만원)": int(c.amount[c.amount > 0].median() / 1e4) if (c.amount > 0).any() else 0,
                     "작년건수": len(p), "작년비율%": round(len(p) / max(len(prev), 1) * 100, 2),
                     "건수증감%": round((len(c) / len(p) - 1) * 100, 1) if len(p) else None,
                     "금액증감%": round((c.amount.sum() / p.amount.sum() - 1) * 100, 1) if p.amount.sum() else None,
                     "SW대상%": round((c.sw == "Y").mean() * 100, 1) if len(c) else 0})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    df = load_all()
    end = pd.Timestamp(a.end) if a.end else df.d.max()
    start = pd.Timestamp(end.year, 4, 1) if end.month >= 4 else end - pd.DateOffset(months=6)
    cur = df[(df.d >= start) & (df.d <= end)].copy()
    ly_s, ly_e = start - pd.DateOffset(years=1), end - pd.DateOffset(years=1)
    prev = df[(df.d >= ly_s) & (df.d <= ly_e)].copy()
    PROC.mkdir(parents=True, exist_ok=True)
    T = []
    T.append(f"기간: {start:%Y-%m-%d} ~ {end:%Y-%m-%d} (사전규격 {len(cur):,}건, 예산 합계 {eok(cur.amount.sum()):,}억원) / "
             f"작년 같은 기간 {ly_s:%Y-%m-%d} ~ {ly_e:%Y-%m-%d} ({len(prev):,}건, {eok(prev.amount.sum()):,}억원)")

    # 1) 전체 월별
    mon = []
    for y, d in (("올해", cur), ("작년", prev)):
        g = d.groupby("ym").agg(건수=("id", "size"), 금액억=("amount", lambda s: eok(s.sum())),
                               SW대상=("sw", lambda s: (s == "Y").sum())).reset_index()
        g["구분"] = y; mon.append(g)
    mon = pd.concat(mon)
    mon.to_csv(PROC / "monthly_total.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 월별 전체\n" + md(mon, ["구분", "ym", "건수", "금액억", "SW대상"]))

    # 2) 분야별
    ct = cat_table(cur, prev).sort_values("금액(억)", ascending=False)
    ct.to_csv(PROC / "cat_summary.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 분야별(최근 6개월 vs 작년 같은 기간)\n" + md(ct))

    # 3) 분야×월
    rows = []
    for n in FOCUS:
        for y, d in (("올해", cur), ("작년", prev)):
            s = d[d.cats.map(lambda x: n in x)]
            for ym, g in s.groupby("ym"):
                tot = (d.ym == ym).sum()
                rows.append({"분야": n, "구분": y, "ym": ym, "건수": len(g), "비율%": round(len(g) / tot * 100, 2),
                             "금액억": eok(g.amount.sum())})
    cm = pd.DataFrame(rows)
    cm.to_csv(PROC / "cat_monthly.csv", index=False, encoding="utf-8-sig")
    piv = cm[cm.구분 == "올해"].pivot_table(index="분야", columns="ym", values="건수", fill_value=0).astype(int)
    T.append("\n### 관심 분야 월별 건수(올해)\n" + md(piv.reset_index()))
    piv2 = cm[cm.구분 == "올해"].pivot_table(index="분야", columns="ym", values="비율%", fill_value=0)
    T.append("\n### 관심 분야 월별 비율%(올해, 그 달 전체 사전규격 대비)\n" + md(piv2.round(2).reset_index()))

    # 4) 기관 유형
    ot = cur.groupby("otype").agg(건수=("id", "size"), 금액억=("amount", lambda s: eok(s.sum()))).reset_index()
    po = prev.groupby("otype").agg(작년건수=("id", "size"), 작년금액억=("amount", lambda s: eok(s.sum()))).reset_index()
    ot = ot.merge(po, on="otype", how="left")
    ot["건수증감%"] = ((ot.건수 / ot.작년건수 - 1) * 100).round(1)
    ot["금액증감%"] = ((ot.금액억 / ot.작년금액억 - 1) * 100).round(1)
    ot = ot.sort_values("금액억", ascending=False)
    ot.to_csv(PROC / "org_type.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 발주기관 유형별\n" + md(ot))
    rows = []
    for t, g in cur.groupby("otype"):
        r = {"기관유형": t, "전체": len(g)}
        for n in ["AI(전체)", "생성형AI·LLM", "정보보호·보안", "클라우드", "개인정보", "데이터", "스마트기기·PC", "노후시설·장비 교체"]:
            r[n] = int(g.cats.map(lambda x: n in x).sum())
        rows.append(r)
    oc = pd.DataFrame(rows).sort_values("전체", ascending=False)
    oc.to_csv(PROC / "org_type_cat.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 기관유형 × 관심분야(건수)\n" + md(oc))

    # 5) 금액대
    order = [b for _, b in BANDS]
    bd = cur.groupby("band").agg(건수=("id", "size"), 금액억=("amount", lambda s: eok(s.sum()))).reindex(order).fillna(0).reset_index()
    bd["건수비율%"] = (bd.건수 / bd.건수.sum() * 100).round(1)
    bd["금액비율%"] = (bd.금액억 / bd.금액억.sum() * 100).round(1)
    pb = prev.groupby("band").size().reindex(order).fillna(0)
    bd["작년건수"] = pb.values.astype(int)
    bd.to_csv(PROC / "band.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 금액대별\n" + md(bd))

    # 6) Top20 금액
    cols = ["date", "biz_type", "title", "org", "otype", "amount", "sw", "id"]
    top = cur.sort_values("amount", ascending=False).head(20).copy()
    top["금액(억)"] = top.amount.map(eok); top["분야"] = top.cats.map(lambda x: ",".join(x))
    top[cols + ["금액(억)", "분야"]].to_csv(PROC / "top20_amount.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 금액 Top20\n" + md(top, ["date", "biz_type", "title", "org", "금액(억)", "분야"]))
    foc = cur[cur.cats.map(lambda x: any(n in x for n in ["AI(전체)", "정보보호·보안", "클라우드", "개인정보"]))]
    tf = foc.sort_values("amount", ascending=False).head(15).copy()
    tf["금액(억)"] = tf.amount.map(eok); tf["분야"] = tf.cats.map(lambda x: ",".join(x))
    tf[cols + ["금액(억)", "분야"]].to_csv(PROC / "top_focus.csv", index=False, encoding="utf-8-sig")
    T.append("\n### AI·보안·클라우드·개인정보 금액 Top15\n" + md(tf, ["date", "biz_type", "title", "org", "금액(억)", "분야"]))
    rows = []
    for n in ["AI(전체)", "정보보호·보안"]:
        s = cur[cur.cats.map(lambda x: n in x)]
        g = s.groupby("org").agg(건수=("id", "size"), 금액억=("amount", lambda v: eok(v.sum()))).sort_values(["건수", "금액억"], ascending=False).head(10).reset_index()
        g.insert(0, "분야", n); rows.append(g)
    to = pd.concat(rows)
    to.to_csv(PROC / "top_orgs_focus.csv", index=False, encoding="utf-8-sig")
    T.append("\n### AI·보안 사전규격 많이 낸 기관\n" + md(to))

    # 7) 관심지역
    rows = []
    for w, rx in WATCH.items():
        s = cur[cur.org.str.contains(rx, regex=True) | cur.dept.str.contains(rx, regex=True)]
        rows.append({"지역": w, "건수": len(s), "금액억": eok(s.amount.sum()),
                     "큰 건(상위3)": " / ".join(f"{t[:28]}({eok(a)}억)" for t, a in s.sort_values("amount", ascending=False)[["title", "amount"]].head(3).values)})
    wr = pd.DataFrame(rows)
    wr.to_csv(PROC / "watch_region.csv", index=False, encoding="utf-8-sig")
    T.append("\n### 관심지역 기관 사전규격\n" + md(wr))

    # 8) 생성형AI 사례 목록
    gen = cur[cur.cats.map(lambda x: "생성형AI·LLM" in x)].sort_values("amount", ascending=False)
    gen[cols].to_csv(PROC / "genai_items.csv", index=False, encoding="utf-8-sig")

    # 9) 기준값(텔레그램용)
    last30 = cur[cur.d > end - pd.Timedelta(days=30)]
    base = {"end": f"{end:%Y-%m-%d}", "start": f"{start:%Y-%m-%d}", "n_6m": len(cur), "amt_6m_eok": eok(cur.amount.sum()),
            "n_prev": len(prev), "amt_prev_eok": eok(prev.amount.sum()), "n_30d": len(last30),
            "share_6m": {n: round(cur.cats.map(lambda x: n in x).mean() * 100, 2) for n, _ in CATS},
            "share_prev": {n: round(prev.cats.map(lambda x: n in x).mean() * 100, 2) for n, _ in CATS},
            "share_30d": {n: round(last30.cats.map(lambda x: n in x).mean() * 100, 2) for n, _ in CATS},
            "sw_share_6m": round((cur.sw == "Y").mean() * 100, 2)}
    json.dump(base, open(PROC / "baseline.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(PROC / "tables.md", "w", encoding="utf-8").write("\n".join(T))
    print("\n".join(T))


if __name__ == "__main__":
    main()
