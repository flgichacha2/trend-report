# -*- coding: utf-8 -*-
"""
data/trades_all.csv(표준 스키마)를 관심지역별로 집계하고 표(CSV/MD)와 차트(PNG)를 만든다.
  - 해제(취소) 신고된 거래 제외
  - 월별 거래량, 평균/중위 거래가, 평균/중위 ㎡당·평당 가격(만원)
  - 대표 단지(최근 12개월 거래 많은 순) 최근 거래
  - 최근 3개월 '기간내 최고가 경신'(데이터 시작월 이후 동일 단지·동일 전용면적 기준)과
    '직전 12개월 동일 단지·면적 중위가 대비 10% 이상 낮은 거래(비교 3건 이상)'
사용: python analyze.py [--asof 2026-10-09] [--recent 3]
"""
import argparse, json, datetime as dt
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from common import DATA, CHARTS, REGIONS, PYEONG

for f in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False


def load():
    d = pd.read_csv(DATA / "trades_all.csv", dtype={"sgg_cd": str, "ym": str, "cancel_date": str, "ri": str})
    jt = DATA / "jeju_edu_town_trades.csv"   # 제주 영어교육도시 연립·다세대(보완 수집분)
    if jt.exists():
        j = pd.read_csv(jt, dtype={"ym": str, "계약일": str, "해제": str})
        d = pd.concat([d, pd.DataFrame({
            "sgg_cd": "50130B", "sigungu": "제주 서귀포시 대정읍 " + j["리"], "emd": "대정읍", "ri": j["리"],
            "apt": j["단지"], "area_m2": j["전용㎡"], "ym": j["ym"], "day": j["계약일"].str[6:8].astype(int),
            "price_manwon": j["거래가(만원)"], "floor": pd.to_numeric(j["층"], errors="coerce"), "build_year": None,
            "cancel_date": j["해제"].fillna("").replace("-", ""), "deal_type": j["거래유형"]})], ignore_index=True)
    d["cancel_date"] = d["cancel_date"].fillna("").str.strip()
    d["ri"] = d["ri"].fillna("")
    d["cancelled"] = d["cancel_date"].ne("") & d["cancel_date"].ne("-")
    d["date"] = pd.to_datetime(d["ym"] + d["day"].astype(int).astype(str).str.zfill(2), format="%Y%m%d")
    d["ppm2"] = d["price_manwon"] / d["area_m2"]          # 만원/㎡
    d["pppy"] = d["ppm2"] * PYEONG                        # 만원/3.3㎡(평)
    d["area_b"] = d["area_m2"].astype(int)
    return d


def subset(d, r):
    x = d[d["sgg_cd"] == r["sgg"]]
    if r["emd"]:
        x = x[x["emd"].isin(r["emd"])]
    if r["ri"]:
        x = x[x["ri"].isin(r["ri"])]
    return x


def monthly(x):
    g = x.groupby("ym")
    m = pd.DataFrame({
        "거래량": g.size(),
        "평균가(만원)": g["price_manwon"].mean().round(0),
        "중위가(만원)": g["price_manwon"].median().round(0),
        "평균㎡당(만원)": g["ppm2"].mean().round(1),
        "중위㎡당(만원)": g["ppm2"].median().round(1),
        "평균평당(만원)": g["pppy"].mean().round(0),
        "중위평당(만원)": g["pppy"].median().round(0),
        "직거래비중(%)": ((x["deal_type"] == "직거래").groupby(x["ym"]).mean() * 100).round(1),
    })
    return m


def records(x, asof, recent_months):
    """최근 N개월 거래 중 기간내 신고가 / 하락 거래"""
    x = x.sort_values("date")
    cut = (pd.Timestamp(asof) - pd.DateOffset(months=recent_months)).replace(day=1)
    hi, lo = [], []
    for (apt, ab), g in x.groupby(["apt", "area_b"]):
        prev_max = None
        for _, row in g.iterrows():
            if prev_max is not None and row["date"] >= cut:
                if row["price_manwon"] > prev_max:
                    hi.append({**_row(row), "직전최고가": prev_max, "상승률(%)": round((row["price_manwon"] / prev_max - 1) * 100, 1)})
                else:
                    # 하락 거래: 같은 단지·면적의 직전 12개월 거래(3건 이상) 중위값 대비 10% 이상 낮은 거래
                    p12 = g[(g["date"] < row["date"]) & (g["date"] >= row["date"] - pd.DateOffset(months=12))]["price_manwon"]
                    if len(p12) >= 3 and row["price_manwon"] <= p12.median() * 0.9:
                        lo.append({**_row(row), "직전12개월중위": int(p12.median()), "기간최고가": prev_max,
                                   "중위대비(%)": round((row["price_manwon"] / p12.median() - 1) * 100, 1)})
            prev_max = row["price_manwon"] if prev_max is None else max(prev_max, row["price_manwon"])
    return pd.DataFrame(hi), pd.DataFrame(lo)


def _row(r):
    return {"계약일": r["date"].date().isoformat(), "읍면동": r["emd"] + (" " + r["ri"] if r["ri"] else ""),
            "단지": r["apt"], "전용㎡": r["area_m2"], "층": int(r["floor"]) if pd.notna(r["floor"]) else None,
            "거래가(만원)": int(r["price_manwon"]), "평당(만원)": round(r["pppy"]), "거래유형": r["deal_type"]}


def top_complexes(x, asof, n=6):
    last12 = x[x["date"] >= pd.Timestamp(asof) - pd.DateOffset(months=12)]
    top = last12.groupby("apt").size().sort_values(ascending=False).head(n).index
    rows = []
    for apt in top:
        g = x[x["apt"] == apt].sort_values("date")
        l = g.iloc[-1]
        g12 = g[g["date"] >= pd.Timestamp(asof) - pd.DateOffset(months=12)]
        main_area = g12["area_b"].mode().iloc[0]
        ga = g[g["area_b"] == main_area]
        rows.append({"단지": apt, "읍면동": l["emd"] + (" " + l["ri"] if l["ri"] else ""), "건축년도": int(g["build_year"].max()) if g["build_year"].notna().any() else None,
                     "12개월거래": len(g12), "주력면적(㎡)": int(main_area),
                     "주력면적 최근거래": f'{ga.iloc[-1]["date"].date()} {int(ga.iloc[-1]["price_manwon"]):,}만원({ga.iloc[-1]["floor"]:.0f}층)',
                     "주력면적 기간최고": f'{int(ga["price_manwon"].max()):,}만원',
                     "주력면적 12개월중위": f'{int(ga[ga["date"] >= pd.Timestamp(asof) - pd.DateOffset(months=12)]["price_manwon"].median()):,}만원',
                     "최근거래": f'{l["date"].date()} {l["area_m2"]}㎡ {int(l["price_manwon"]):,}만원'})
    return pd.DataFrame(rows)


def period_compare(x, asof):
    """완결월 기준 최근 3개월 vs 직전 3개월 vs 전년 동기 3개월"""
    a = pd.Timestamp(asof)
    end = (a - pd.DateOffset(months=1)).replace(day=1)  # 신고기한(30일) 고려해 직전월은 잠정
    def win(e, k=3):
        s = e - pd.DateOffset(months=k - 1)
        w = x[(x["date"] >= s) & (x["date"] < e + pd.DateOffset(months=1))]
        return {"기간": f"{s:%Y-%m}~{e:%Y-%m}", "거래량": len(w),
                "중위평당(만원)": round(w["pppy"].median()) if len(w) else None,
                "중위가(만원)": round(w["price_manwon"].median()) if len(w) else None}
    e1 = end - pd.DateOffset(months=1)  # 최근 '확정에 가까운' 월(asof 기준 2개월 전)
    return pd.DataFrame([win(e1), win(e1 - pd.DateOffset(months=3)), win(e1 - pd.DateOffset(months=12))],
                        index=["최근3개월", "직전3개월", "전년동기"])


def paired_change(x, asof):
    """동일 단지·동일 전용면적(정수㎡) 쌍의 중위가 변화율의 중앙값 (구성 효과 제거용)"""
    a = pd.Timestamp(asof)
    e = (a - pd.DateOffset(months=2)).replace(day=1)  # 최근 '확정 근접' 월
    def w(end):
        s0 = end - pd.DateOffset(months=2)
        z = x[(x["date"] >= s0) & (x["date"] < end + pd.DateOffset(months=1))]
        return z.groupby(["apt", "area_b"])["price_manwon"].median()
    cur = w(e); out = {}
    for lab, k in (("직전3개월대비", 3), ("전년동기대비", 12)):
        prev = w(e - pd.DateOffset(months=k))
        j = pd.concat([cur, prev], axis=1, keys=["c", "p"]).dropna()
        out[lab] = {"비교쌍": len(j), "중앙변화율(%)": round(((j["c"] / j["p"]).median() - 1) * 100, 1) if len(j) else None}
    return pd.DataFrame(out).T


def chart(m, title, path, partial):
    fig, ax1 = plt.subplots(figsize=(10, 4.2))
    idx = list(m.index)
    colors = ["#9db4d6" if i not in partial else "#d9d9d9" for i in idx]
    ax1.bar(range(len(idx)), m["거래량"], color=colors)
    ax1.set_ylabel("거래량(건)")
    ax1.set_xticks(range(len(idx)))
    ax1.set_xticklabels([f"{i[2:4]}.{i[4:]}" for i in idx], rotation=60, fontsize=8)
    ax2 = ax1.twinx()
    ax2.plot(range(len(idx)), m["중위평당(만원)"], color="#c0392b", marker="o", ms=3, label="중위 평당가")
    ax2.set_ylabel("중위 평당가(만원/3.3㎡)")
    ax1.set_title(f"{title} - 월별 거래량(막대) / 중위 평당가(선)  *회색=신고 진행중")
    ax1.spines["top"].set_visible(False); ax2.spines["top"].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def compare_chart(allm, path, partial):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    ticks = sorted(set().union(*[set(m.index) for m in allm.values()]) - set(partial))
    for name, m in allm.items():
        m = m.reindex(ticks).rolling(3, min_periods=1).mean()  # 3개월 이동평균
        base = m["중위평당(만원)"].iloc[:3].mean()
        axes[0].plot(range(len(m)), m["중위평당(만원)"] / base * 100, label=name, marker=".", lw=1.5)
        axes[1].plot(range(len(m)), m["거래량"] / m["거래량"].iloc[:3].mean() * 100, label=name, marker=".", lw=1.5)
    for ax, t in zip(axes, ["중위 평당가 지수(3개월 이동평균, 첫 3개월=100)", "거래량 지수(3개월 이동평균, 첫 3개월=100)"]):
        ax.set_title(t); ax.axhline(100, color="#999", lw=.8)
        ax.set_xticks(range(0, len(ticks), 2)); ax.set_xticklabels([f"{ticks[i][2:4]}.{ticks[i][4:]}" for i in range(0, len(ticks), 2)], rotation=60, fontsize=8)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    axes[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=dt.date.today().isoformat())
    ap.add_argument("--recent", type=int, default=3)
    a = ap.parse_args()
    d = load()
    print("전체", len(d), "해제", int(d["cancelled"].sum()))
    asof = pd.Timestamp(a.asof)
    partial = {f"{asof:%Y%m}", f"{asof - pd.DateOffset(months=1):%Y%m}"}
    summary, allm, md = {}, {}, []
    for r in REGIONS:
        x_all = subset(d, r)
        x = x_all[~x_all["cancelled"]]
        m = monthly(x)
        m["해제건수"] = x_all[x_all["cancelled"]].groupby("ym").size().reindex(m.index).fillna(0).astype(int)
        m.to_csv(DATA / f"monthly_{r['key']}.csv", encoding="utf-8-sig")
        hi, lo = records(x, a.asof, a.recent)
        hi.to_csv(DATA / f"newhigh_{r['key']}.csv", index=False, encoding="utf-8-sig")
        lo.to_csv(DATA / f"drop10_{r['key']}.csv", index=False, encoding="utf-8-sig")
        tc = top_complexes(x, a.asof)
        tc.to_csv(DATA / f"top_complexes_{r['key']}.csv", index=False, encoding="utf-8-sig")
        pc = period_compare(x, a.asof)
        pc.to_csv(DATA / f"period_{r['key']}.csv", encoding="utf-8-sig")
        pr = paired_change(x, a.asof)
        pr.to_csv(DATA / f"paired_{r['key']}.csv", encoding="utf-8-sig")
        chart(m, r["name"], CHARTS / f"{r['key']}.png", partial)
        if not r["name"].startswith("(참고)"):
            allm[r["name"].split("(")[0]] = m
        recent = x[x["date"] >= (asof - pd.DateOffset(months=a.recent)).replace(day=1)]
        summary[r["key"]] = {"name": r["name"], "total": len(x), "cancelled": int(x_all["cancelled"].sum()),
                             "newhigh_recent": len(hi), "drop10_recent": len(lo), "recent_trades": len(recent),
                             "period": pc.to_dict(orient="index"), "paired": pr.to_dict(orient="index")}
        md += [f"\n## {r['name']}\n", "### 월별\n", m.to_markdown(), "\n### 기간비교\n", pc.to_markdown(),
               "\n### 동일 단지·면적 쌍 비교(최근 3개월 중위가 변화율의 중앙값)\n", pr.to_markdown(),
               "\n### 대표 단지\n", tc.to_markdown(index=False),
               f"\n### 최근 {a.recent}개월 기간내 신고가 (상위 15, 상승률순)\n",
               hi.sort_values("상승률(%)", ascending=False).head(15).to_markdown(index=False) if len(hi) else "없음",
               f"\n### 최근 {a.recent}개월 직전12개월 중위 대비 -10% 이하 거래 (상위 15)\n",
               lo.sort_values("중위대비(%)").head(15).to_markdown(index=False) if len(lo) else "없음"]
    compare_chart(allm, CHARTS / "compare_index.png", partial)
    (DATA / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (DATA / "analysis_tables.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
