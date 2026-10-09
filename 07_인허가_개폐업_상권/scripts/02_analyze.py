# -*- coding: utf-8 -*-
"""
LOCALDATA 업종별 개·폐업 분석 -> data/processed/*.csv, charts/*.png, data/processed/_summary.json
실행: python -I scripts/02_analyze.py
기간 정의 (데이터 기준일 2026-10-07, 월 단위 완결 기준 2026-09-30)
  최근12M = 2025-10-01 ~ 2026-09-30, 직전12M = 2024-10-01 ~ 2025-09-30, 전전12M = 2023-10-01 ~ 2024-09-30
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, NAMES, RAW, BASE
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
PROC = os.path.join(BASE, "data", "processed"); os.makedirs(PROC, exist_ok=True)
CH = os.path.join(BASE, "charts"); os.makedirs(CH, exist_ok=True)
C_OPEN, C_CLOSE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DIV = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])

P = {"전전12M": ("2023-10-01", "2024-10-01"), "직전12M": ("2024-10-01", "2025-10-01"),
     "최근12M": ("2025-10-01", "2026-10-01")}
END = pd.Timestamp("2026-10-01")
START_Q = pd.Timestamp("2023-01-01")
AREAS = ["서울 강남구", "성남 분당구", "인천 영종(옛 중구)", "제주 서귀포시"]


def style(ax):
    ax.set_facecolor(SURF)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)


def win(s, a, b):
    return (s >= pd.Timestamp(a)) & (s < pd.Timestamp(b))


def stock_at(d, t):
    t = pd.Timestamp(t)
    return int(((d.lic < t) & (d.is_alive | (d.is_closed & (d.clo >= t)))).sum())


def period_stats(d):
    r = {}
    for k, (a, b) in P.items():
        o = int(win(d.lic, a, b).sum()); c = int((d.is_closed & win(d.clo, a, b)).sum())
        st = stock_at(d, a)
        # 단기(인허가 후 60일 이내 폐업: '(한시적)' 팝업·행사 부스 등) 제외한 실질 개·폐업
        so = int((win(d.lic, a, b) & d.short).sum()); sc = int((d.is_closed & win(d.clo, a, b) & d.short).sum())
        r[k] = dict(개업=o, 폐업=c, 순증=o - c, 기초재고=st,
                    순증률=round((o - c) / st * 100, 2) if st else np.nan,
                    폐업개업비=round(c / o, 2) if o else np.nan,
                    단기개업=so, 실질개업=o - so, 실질폐업=c - sc,
                    실질폐업개업비=round((c - sc) / (o - so), 2) if o - so else np.nan)
    r["현재영업중"] = int(d.is_alive.sum())
    return r


def flat(key, r):
    row = dict(key)
    for k in P:
        for m, v in r[k].items():
            row[f"{k}_{m}"] = v
    row["현재영업중"] = r["현재영업중"]
    row["개업증감률(최근vs직전)"] = round((r["최근12M"]["개업"] / r["직전12M"]["개업"] - 1) * 100, 1) if r["직전12M"]["개업"] else np.nan
    row["폐업증감률(최근vs직전)"] = round((r["최근12M"]["폐업"] / r["직전12M"]["폐업"] - 1) * 100, 1) if r["직전12M"]["폐업"] else np.nan
    a, b = r["최근12M"]["실질개업"], r["직전12M"]["실질개업"]
    row["실질개업증감률(최근vs직전)"] = round((a / b - 1) * 100, 1) if b else np.nan
    a, b = r["최근12M"]["실질폐업"], r["직전12M"]["실질폐업"]
    row["실질폐업증감률(최근vs직전)"] = round((a / b - 1) * 100, 1) if b else np.nan
    return row


KW = {
    "무인": "무인", "셀프": "셀프", "24시": "24시", "탕후루": "탕후루",
    "요거트아이스크림": "요거트|요아정|요거프레소|요플랜", "두바이": "두바이", "베이글": "베이글",
    "소금빵": "소금빵", "마라(탕)": "마라", "포케": "포케", "샐러드": "샐러드", "하이볼": "하이볼",
    "이자카야": "이자카야", "오마카세": "오마카세", "와인": "와인", "위스키": "위스키",
    "저가커피브랜드": "메가커피|메가MGC|메가엠지씨|컴포즈|빽다방|더벤티|매머드",
    "버블티·밀크티": "공차|버블티|밀크티|팔공티", "젤라또": "젤라또|젤라토",
    "키즈": "키즈", "반려동물(펫·애견)": "펫|애견|강아지|반려|댕댕", "고양이": "고양이|캣",
    "빨래방·코인세탁": "빨래방|코인세탁|코인빨래|워시|론드리|런드리", "필라테스": "필라테스",
    "크로스핏": "크로스핏", "PT·퍼스널": "PT|피티|퍼스널", "스크린": "스크린", "코인노래": "코인",
    "밀키트": "밀키트", "반찬": "반찬", "도시락": "도시락", "디저트": "디저트",
    "편의점": "CU |CU\\(|씨유|GS25|세븐일레븐|이마트24", "스터디": "스터디", "풀빌라·스테이": "풀빌라|스테이|STAY",
    "한시적(팝업·행사)": "한시적", "축제·행사부스": "축제|페스티벌|부스",
    "사행성연상 상호(대박·로또·잭팟 등)": "대박|로또|잭팟|황금|럭키|행운|마카오|카지노|777|라스베가스|슬롯",
}


def main():
    meta = json.load(open(os.path.join(RAW, "_download_meta.json"), encoding="utf-8"))
    slugs = [s for s in NAMES if os.path.exists(os.path.join(RAW, f"{s}.csv.gz"))]
    nat, sido_rows, area_rows, surv, qrows, kwrows, bz_rows, tok_rows = [], [], [], [], [], [], [], []
    sample = {}
    for slug in slugs:
        d = load(slug); nm = NAMES[slug]
        print(nm, len(d), flush=True)
        sample[nm] = dict(원본행수=meta[slug]["rows_total"], 분석행수=len(d),
                          최신인허가일자=meta[slug]["max_license_date"], 수집시각=meta[slug]["downloaded_at"])
        nat.append(flat({"업종": nm}, period_stats(d)))
        for sd, g in d.groupby("시도"):
            if sd == "미상":
                continue
            sido_rows.append(flat({"업종": nm, "시도": sd}, period_stats(g)))
        for ar in AREAS:
            g = d[d["관심지역"] == ar]
            area_rows.append(flat({"업종": nm, "관심지역": ar}, period_stats(g)))
        # 영업기간 (최근12M 폐업)
        a, b = P["최근12M"]
        for scope, g in [("전국", d)] + [(ar, d[d["관심지역"] == ar]) for ar in AREAS]:
            c = g[g.is_closed & win(g.clo, a, b) & g.영업년수.notna() & (g.영업년수 >= 0)]
            if len(c):
                surv.append({"업종": nm, "범위": scope, "폐업건수": len(c),
                             "평균영업년수": round(c.영업년수.mean(), 2), "중앙값영업년수": round(c.영업년수.median(), 2),
                             "1년내폐업비율%": round((c.영업년수 < 1).mean() * 100, 1),
                             "3년내폐업비율%": round((c.영업년수 < 3).mean() * 100, 1),
                             "10년이상비율%": round((c.영업년수 >= 10).mean() * 100, 1)})
        # 분기
        o = d[(d.lic >= START_Q) & (d.lic < END)].groupby(d.lic.dt.to_period("Q")).size()
        c = d[d.is_closed & (d.clo >= START_Q) & (d.clo < END)].groupby(d.clo.dt.to_period("Q")).size()
        q = pd.DataFrame({"개업": o, "폐업": c}).fillna(0).astype(int)
        for k, v in q.iterrows():
            qrows.append({"업종": nm, "분기": str(k), "개업": v["개업"], "폐업": v["폐업"], "순증": v["개업"] - v["폐업"]})
        # 업태 (음식점·세탁 등)
        if d["업태"].str.strip().ne("").any():
            for bz, g in d.groupby("업태"):
                r = period_stats(g)
                if r["최근12M"]["개업"] + r["직전12M"]["개업"] + r["최근12M"]["폐업"] >= 20:
                    bz_rows.append(flat({"업종": nm, "업태": bz or "(미기재)"}, r))
        # 키워드 (분기별 개업/폐업, 업종 합산 위해 저장)
        name = d["사업장명"].fillna("")
        for kw, pat in KW.items():
            m = name.str.contains(pat, regex=True)
            if not m.any():
                continue
            g = d[m]
            o = g[(g.lic >= START_Q) & (g.lic < END)].groupby(g.lic.dt.to_period("Q")).size()
            c = g[g.is_closed & (g.clo >= START_Q) & (g.clo < END)].groupby(g.clo.dt.to_period("Q")).size()
            qq = pd.DataFrame({"개업": o, "폐업": c}).fillna(0).astype(int)
            for k, v in qq.iterrows():
                kwrows.append({"키워드": kw, "업종": nm, "분기": str(k), "개업": v["개업"], "폐업": v["폐업"]})
            for k in P:
                pass
        # 신규 토큰(상호명) 부상/쇠퇴
        if slug in ("general_restaurants", "rest_cafes", "bakeries", "laundries", "fitness_centers", "beauty_salons"):
            def toks(sub):
                cnt = {}
                for s in sub["사업장명"].fillna(""):
                    for t in set(re.findall(r"[가-힣A-Za-z]{2,}", s)):
                        if t.endswith("점") and len(t) >= 3:
                            continue
                        cnt[t] = cnt.get(t, 0) + 1
                return pd.Series(cnt, dtype=float)
            new = toks(d[win(d.lic, *P["최근12M"])]); old = toks(d[win(d.lic, *P["전전12M"])])
            t = pd.DataFrame({"최근12M개업": new, "전전12M개업": old}).fillna(0)
            t = t[(t.sum(axis=1) >= 30)]
            t["배율"] = ((t["최근12M개업"] + 5) / (t["전전12M개업"] + 5)).round(2)
            t = t.sort_values("배율")
            for kind, sub in [("부상", t.tail(30)[::-1]), ("쇠퇴", t.head(30))]:
                for tok, v in sub.iterrows():
                    tok_rows.append({"업종": nm, "구분": kind, "토큰": tok, **v.to_dict()})
        del d

    nat = pd.DataFrame(nat); sido = pd.DataFrame(sido_rows); area = pd.DataFrame(area_rows)
    surv = pd.DataFrame(surv); qdf = pd.DataFrame(qrows); kwdf = pd.DataFrame(kwrows)
    bz = pd.DataFrame(bz_rows); tk = pd.DataFrame(tok_rows)
    for df, fn in [(nat, "national_periods"), (sido, "sido_periods"), (area, "interest_area_periods"),
                   (surv, "closure_duration"), (qdf, "quarterly_open_close"), (kwdf, "keyword_quarterly"),
                   (bz, "biztype_periods"), (tk, "name_token_trends")]:
        df.to_csv(os.path.join(PROC, f"{fn}.csv"), index=False, encoding="utf-8-sig")
    json.dump(sample, open(os.path.join(PROC, "_sample.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- charts ----------
    order = nat.sort_values("최근12M_실질개업")["업종"].tolist()
    n = nat.set_index("업종").loc[order]
    fig, ax = plt.subplots(figsize=(9, 6.5), facecolor=SURF); style(ax); ax.grid(axis="x", color=GRID, lw=.6); ax.grid(axis="y", visible=False)
    y = np.arange(len(n)); h = .38
    ax.barh(y + h / 2, n["최근12M_실질개업"], h - .04, color=C_OPEN, label="개업(인허가)")
    ax.barh(y - h / 2, n["최근12M_실질폐업"], h - .04, color=C_CLOSE, label="폐업")
    ax.set_xscale("log"); ax.set_yticks(y); ax.set_yticklabels(order, color=INK, fontsize=9)
    for i, (o, c) in enumerate(zip(n["최근12M_실질개업"], n["최근12M_실질폐업"])):
        ax.text(max(o, c) * 1.12, i, f"순증 {o - c:+,}", va="center", fontsize=8, color=INK2)
    ax.set_title("전국 업종별 실질 개업 vs 폐업 (2025.10~2026.09, 60일내 단기영업 제외, 로그축)", loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_xlim(right=ax.get_xlim()[1] * 4)
    fig.text(0.01, 0.005, "출처: 행정안전부 지방행정 인허가데이터(LOCALDATA) 파일다운로드, 2026-10-09 수집", fontsize=7, color=INK2)
    fig.tight_layout(); fig.savefig(os.path.join(CH, "c1_national_open_close_12m.png"), dpi=150); plt.close(fig)

    ups = nat.sort_values("최근12M_개업", ascending=False)["업종"].tolist()
    fig, axes = plt.subplots(4, 4, figsize=(14, 10), facecolor=SURF, sharex=True)
    for ax, u in zip(axes.flat, ups):
        style(ax); g = qdf[qdf.업종 == u]
        x = np.arange(len(g))
        ax.plot(x, g["개업"], color=C_OPEN, lw=2, marker="o", ms=3)
        ax.plot(x, g["폐업"], color=C_CLOSE, lw=2, marker="o", ms=3)
        ax.set_title(u, loc="left", fontsize=10, color=INK)
        ax.set_xticks(x[::4]); ax.set_xticklabels([s.replace("Q1", "") for s in g["분기"].iloc[::4]], fontsize=7)
        ax.set_ylim(bottom=0)
    for ax in list(axes.flat)[len(ups):]:
        ax.axis("off")
    axes.flat[0].legend(["개업", "폐업"], frameon=False, fontsize=8)
    fig.suptitle("업종별 분기 개업·폐업 건수 (2023Q1~2026Q3, 전국)", x=0.01, ha="left", color=INK, fontsize=13)
    fig.tight_layout(); fig.savefig(os.path.join(CH, "c2_quarterly_by_industry.png"), dpi=140); plt.close(fig)

    piv = sido.pivot(index="업종", columns="시도", values="최근12M_순증률").loc[ups]
    sido_order = sido[sido.업종 == "일반음식점"].sort_values("현재영업중", ascending=False)["시도"].tolist()
    piv = piv[[s for s in sido_order if s in piv.columns]]
    lim = np.nanpercentile(np.abs(piv.values), 95)
    fig, ax = plt.subplots(figsize=(13, 7), facecolor=SURF)
    im = ax.imshow(piv.values, cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels(piv.columns, fontsize=9)
    ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(piv.index, fontsize=9)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=7, color=INK)
    ax.set_title("시도×업종 순증률(%) = (개업-폐업)/기초재고, 2025.10~2026.09", loc="left", color=INK)
    fig.colorbar(im, ax=ax, shrink=.6)
    fig.tight_layout(); fig.savefig(os.path.join(CH, "c3_sido_net_rate_heatmap.png"), dpi=140); plt.close(fig)

    pa = area.pivot(index="업종", columns="관심지역", values="최근12M_순증률").loc[ups][AREAS]
    pn = area.pivot(index="업종", columns="관심지역", values="최근12M_순증").loc[ups][AREAS]
    natr = nat.set_index("업종").loc[ups, "최근12M_순증률"]
    pa.insert(0, "전국", natr); pn.insert(0, "전국", nat.set_index("업종").loc[ups, "최근12M_순증"])
    fig, ax = plt.subplots(figsize=(9, 7), facecolor=SURF)
    im = ax.imshow(pa.values, cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    ax.set_xticks(range(pa.shape[1])); ax.set_xticklabels(pa.columns, fontsize=9)
    ax.set_yticks(range(pa.shape[0])); ax.set_yticklabels(pa.index, fontsize=9)
    for i in range(pa.shape[0]):
        for j in range(pa.shape[1]):
            v = pa.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:+.1f}%\n({int(pn.values[i, j]):+d})", ha="center", va="center", fontsize=7, color=INK)
    ax.set_title("관심지역 업종 순증률(%)·순증(건), 2025.10~2026.09", loc="left", color=INK)
    fig.tight_layout(); fig.savefig(os.path.join(CH, "c4_interest_area_heatmap.png"), dpi=140); plt.close(fig)

    if len(kwdf):
        kq = kwdf.groupby(["키워드", "분기"])[["개업", "폐업"]].sum().reset_index()
        sel = ["탕후루", "요거트아이스크림", "두바이", "베이글", "소금빵", "저가커피브랜드", "무인", "한시적(팝업·행사)",
               "빨래방·코인세탁", "하이볼", "필라테스", "반려동물(펫·애견)"]
        sel = [s for s in sel if s in kq.키워드.unique()]
        qs = sorted(qdf["분기"].unique())
        fig, axes = plt.subplots(3, 4, figsize=(14, 8.5), facecolor=SURF, sharex=True)
        for ax, k in zip(axes.flat, sel):
            style(ax); g = kq[kq.키워드 == k].set_index("분기").reindex(qs).fillna(0)
            x = np.arange(len(qs))
            ax.plot(x, g["개업"], color=C_OPEN, lw=2, marker="o", ms=3)
            ax.plot(x, g["폐업"], color=C_CLOSE, lw=2, marker="o", ms=3)
            ax.set_title(f"'{k}' 상호", loc="left", fontsize=10, color=INK)
            ax.set_xticks(x[::4]); ax.set_xticklabels([s[:4] for s in qs[::4]], fontsize=7); ax.set_ylim(bottom=0)
        axes.flat[0].legend(["개업", "폐업"], frameon=False, fontsize=8)
        fig.suptitle("상호명 키워드별 분기 개업·폐업 (분석 14개 업종 합산, 2023Q1~2026Q3)", x=0.01, ha="left", color=INK, fontsize=13)
        fig.tight_layout(); fig.savefig(os.path.join(CH, "c5_keyword_quarterly.png"), dpi=140); plt.close(fig)
    print("done")


if __name__ == "__main__":
    main()
