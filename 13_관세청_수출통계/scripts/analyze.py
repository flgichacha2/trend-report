# -*- coding: utf-8 -*-
"""
분석(보고서용): python -I -X utf8 scripts\\analyze.py  → data/processed/*.csv + 화면에 표(마크다운) 출력
입력: data/raw (collect.py 결과). 금액 단위: 백만 달러(원자료 천 달러 ÷ 1000)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import common as C

RAW = C.BASE / "data" / "raw"
PRO = C.BASE / "data" / "processed"
PRO.mkdir(parents=True, exist_ok=True)


def f(v, d=1):
    return "-" if v is None or pd.isna(v) else f"{v:+.{d}f}%"


def mn(v):
    return f"{v / 1000:,.1f}"


def main():
    meta = json.load(open(RAW / "_collect_meta.json", encoding="utf-8"))
    df = pd.read_csv(RAW / "monthly_item_country.csv.gz", dtype={"ym": str, "hs": str})
    res = C.analyze_monthly(df, meta["monthly_latest"])
    it = pd.DataFrame(res["items"])
    it.drop(columns=["trend12"]).to_csv(PRO / "items_summary.csv", index=False, encoding="utf-8-sig")
    res["cells"].to_csv(PRO / "item_country_cells.csv", index=False, encoding="utf-8-sig")
    up, down, split, new = C.pick_tops(res)
    for n, d in (("top_up", up), ("top_down", down), ("split_stronger", split), ("new_markets", new)):
        d.to_csv(PRO / f"{n}.csv", index=False, encoding="utf-8-sig")
    M = res["latest"]
    print(f"## 품목 요약 (최신 {M}, 3개월={res['q3_months']})")
    print("| 품목(HS) | 최근월 | 전월비 | 전년비 | 3개월 전년비 | 연초~ 누적 전년비 |")
    print("|---|---:|---:|---:|---:|---:|")
    for r in res["items"]:
        print(f"| {r['name']}({r['hs']}) | {mn(r['m'])} | {f(r['mom'])} | {f(r['yoy'])} | {f(r['q3_yoy'])} | {f(r['ytd_yoy'])} |")
    for title, d in (("급증 Top", up), ("급감 Top", down), ("쪼개 볼수록 강해짐", split), ("새로 열린 시장", new)):
        print(f"\n## {title}")
        print("| 품목 | 국가 | 3개월 합 | 작년 같은 3개월 | 증감액 | 증가율 | 품목 전체 증가율 | 품목 내 비중 |")
        print("|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in d.iterrows():
            print(f"| {r['name']} | {r['cnty']} | {mn(r['q3'])} | {mn(r['q3_ly'])} | {mn(r['q3_diff'])} | {f(r['q3_yoy'])} | {f(r['item_q3_yoy'])} | {r['share_q3']}% |")
    # 관심 국가 × 품목 매트릭스(3개월 전년비)
    c = res["cells"]
    mat = c[c["cnty"].isin(C.FOCUS_CNTY)].pivot_table(index="name", columns="cnty", values="q3_yoy")
    mat = mat.reindex(columns=[x for x in C.FOCUS_CNTY if x in mat.columns])
    mat.to_csv(PRO / "focus_matrix_q3_yoy.csv", encoding="utf-8-sig")
    print("\n## 관심국가 3개월 전년비(%)")
    print(mat.round(0).to_string())
    # 품목별 상위 5개국
    print("\n## 품목별 상위 5개 수출국(3개월 합)")
    for hs in [x for x, *_ in C.ITEMS]:
        d = c[c["hs"] == hs].sort_values("q3", ascending=False).head(5)
        print(C.ITEM_NAME[hs], " / ".join(f"{r['cnty']} {mn(r['q3'])}({f(r['q3_yoy'], 0)})" for _, r in d.iterrows()))
    mv = C.per_item_movers(res)
    json.dump(mv, open(PRO / "per_item_movers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n## 품목별 증가/감소 국가(3개월 증감액, 백만달러)")
    for hs, v in mv.items():
        print(C.ITEM_NAME[hs], "| 증가:", ", ".join(f"{r['cnty']} {r['q3_diff']/1000:+.1f}({f(r['q3_yoy'],0)})" for r in v["up"]),
              "| 감소:", ", ".join(f"{r['cnty']} {r['q3_diff']/1000:+.1f}({f(r['q3_yoy'],0)})" for r in v["down"]))
    # 10일 잠정치
    tp =pd.read_csv(RAW / "tentative_items.csv", dtype={"ym": str})
    tn = pd.read_csv(RAW / "tentative_countries.csv", dtype={"ym": str})
    t = C.analyze_tentative(tp, tn)
    json.dump(t, open(PRO / "tentative_latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in t.items():
        print(f"\n## 10일 잠정치 {k}: {v['ym']} {v['period']} vs {v['ly_ym']} {v['ly_period']}")
        for r in v["rows"]:
            print(f"  {r['name']}: {mn(r['cur'])} (작년 {mn(r['ly'])}, {f(r['yoy'])})")
    # 월별 잠정 총수출 추이(말일 기준)
    end = tp[(tp["name"] == "전체") & ~tp["period"].isin(["01~10", "01~20"])]
    print("\n## 월별 총수출(잠정, 백만달러):", ", ".join(f"{r.ym}:{mn(r.usd_k)}" for r in end.itertuples()))
    semi = tp[(tp["name"] == "반도체") & ~tp["period"].isin(["01~10", "01~20"])]
    print("## 반도체(잠정):", ", ".join(f"{r.ym}:{mn(r.usd_k)}" for r in semi.itertuples()))
    print("\n## 12개월 추이(백만달러)")
    for r in res["items"]:
        print(r["name"], r["trend12"][-12:])


if __name__ == "__main__":
    main()
