# -*- coding: utf-8 -*-
"""
기간(tag)별 purposes_<tag>.csv 를 모아 테마별 기업 수 집계 + 비교표 생성.
사용: python aggregate.py --tags 2026H1reg 2025H1reg 2026post 2025post
출력: data/theme_counts.csv, data/summary_periods.csv, data/cases_all.csv, (표준출력) 마크다운 표
"""
import argparse, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_purposes import THEMES, themes_of  # noqa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True)
    a = ap.parse_args()
    summ, counts, cases = [], {}, []
    for t in a.tags:
        p = os.path.join(DATA, f"purposes_{t}.csv")
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, dtype={"rcept_no": str, "corp_code": str})
        df["added_items"] = df["added_items"].fillna("")
        # 테마 재계산(사전 수정 반영)
        df["themes"] = df["added_items"].map(lambda s: ";".join(themes_of(s)))
        n = len(df)
        pos = df[df.n_added.fillna(0) > 0]
        summ.append(dict(period=t, corps_with_notice=n, agenda_mentions_purpose=int(df.agenda_flag.sum()),
                         big_parsed=int(df.has_big.sum()), purpose_added_corps=len(pos),
                         purpose_added_ratio=round(len(pos) / n * 100, 1) if n else 0))
        c = {}
        for th in THEMES:
            c[th] = int(pos.themes.fillna("").str.split(";").map(lambda L: th in L).sum())
        counts[t] = c
        pos = pos.assign(period=t)
        # DART 접수번호 매핑(같은 기간 DART 소집공고 목록, 회사명 기준 최신본)
        dl = os.path.join(DATA, f"list_{t}.csv")
        if os.path.exists(dl):
            dd = pd.read_csv(dl, dtype=str).sort_values("rcept_no", ascending=False).drop_duplicates("corp_name")
            pos = pos.merge(dd[["corp_name", "rcept_no"]].rename(columns={"rcept_no": "dart_rcept_no"}),
                            on="corp_name", how="left")
        cases.append(pos)
    sm = pd.DataFrame(summ)
    tc = pd.DataFrame(counts)
    tc.index.name = "theme"
    sm.to_csv(os.path.join(DATA, "summary_periods.csv"), index=False, encoding="utf-8-sig")
    tc.to_csv(os.path.join(DATA, "theme_counts.csv"), encoding="utf-8-sig")
    if cases:
        allc = pd.concat(cases, ignore_index=True)
        allc.to_csv(os.path.join(DATA, "cases_all.csv"), index=False, encoding="utf-8-sig")
        # 테마별 사례(해당 테마에 걸린 '추가 항목'만 발췌)
        import re
        from parse_purposes import THEME_RE
        rows = []
        for _, r in allc.iterrows():
            items = [x for x in str(r.added_items).split(" | ") if x and x != "nan"]
            for th, rx in THEME_RE.items():
                hit = [x for x in items if rx.search(x)]
                if hit:
                    rows.append(dict(period=r.period, theme=th, corp_name=r.corp_name, market=r.market,
                                     rcept_dt=r.rcept_dt, n_theme_items=len(hit), n_added_total=len(items),
                                     theme_items=" | ".join(hit)[:400], reason=str(r.reason)[:200],
                                     source_url=r.get("source_url", ""), kind_acptno=r.rcept_no, dart_rcept_no=r.get("dart_rcept_no", "")))
        bt = pd.DataFrame(rows)
        bt.to_csv(os.path.join(DATA, "cases_by_theme.csv"), index=False, encoding="utf-8-sig")
        # 시장별
        mk = allc.groupby(["period", "market"]).size().unstack(fill_value=0)
        mk.to_csv(os.path.join(DATA, "added_by_market.csv"), encoding="utf-8-sig")
        print(mk.to_markdown()); print()
        # 추가 항목 수 분포 (대량 추가 = 테마 편승 의심 신호)
        allc["n_added"] = allc["n_added"].astype(int)
        dist = allc.groupby("period")["n_added"].describe()
        print(dist.to_markdown()); print()
        big = allc[allc.n_added >= 10][["period", "corp_name", "market", "n_added", "themes"]]
        big.to_csv(os.path.join(DATA, "bulk_additions_10plus.csv"), index=False, encoding="utf-8-sig")
        print("10개 이상 대량 추가:", big.groupby("period").size().to_dict())
    print(sm.to_markdown(index=False))
    print()
    # 비율(%) 및 증감
    out = tc.copy()
    for t in tc.columns:
        base = sm.set_index("period").loc[t, "purpose_added_corps"]
        out[f"{t}_%"] = (tc[t] / base * 100).round(1) if base else 0
    print(out.sort_values(tc.columns[0], ascending=False).to_markdown())


if __name__ == "__main__":
    main()


def extra_stats():
    """대량추가·복수 핫테마·동일문구(템플릿) 통계 -> data/extra_*.csv"""
    from parse_purposes import themes_of, norm
    c = pd.read_csv(os.path.join(DATA, "cases_all.csv"), dtype=str)
    c["n_added"] = c.n_added.astype(int)
    hot = ["AI(인공지능)", "로봇", "데이터센터", "방산", "우주항공", "디지털자산·블록체인·STO(스테이블코인)",
           "원전·원자력", "2차전지·배터리", "반도체", "양자", "드론·UAM"]
    c["nhot"] = c.added_items.fillna("").map(lambda s: len([t for t in themes_of(s) if t in hot]))
    g = c.groupby("period").agg(n=("corp_name", "size"), bulk10=("n_added", lambda s: int((s >= 10).sum())),
                                hot1=("nhot", lambda s: int((s >= 1).sum())), hot3=("nhot", lambda s: int((s >= 3).sum())))
    for k in ["bulk10", "hot1", "hot3"]:
        g[k + "%"] = (g[k] / g.n * 100).round(1)
    g.to_csv(os.path.join(DATA, "extra_hot_bulk_stats.csv"), encoding="utf-8-sig")
    c[c.nhot >= 3][["period", "corp_name", "market", "n_added", "nhot", "added_items"]].to_csv(
        os.path.join(DATA, "extra_multi_hot_theme_corps.csv"), index=False, encoding="utf-8-sig")
    rows = []
    for _, r in c.iterrows():
        for it in str(r.added_items).split(" | "):
            if len(norm(it)) > 12:
                rows.append((r.period, r.corp_name, norm(it), it))
    d = pd.DataFrame(rows, columns=["period", "corp", "k", "item"])
    k = d.groupby("k").agg(n_corps=("corp", "nunique"), corps=("corp", lambda s: ",".join(sorted(set(s)))),
                           item=("item", "first")).sort_values("n_corps", ascending=False)
    k[k.n_corps >= 3].to_csv(os.path.join(DATA, "extra_identical_items.csv"), encoding="utf-8-sig")
    print(g.to_markdown())


if __name__ == "__main__" and os.environ.get("EXTRA", "1") == "1":
    extra_stats()
