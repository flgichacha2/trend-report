# -*- coding: utf-8 -*-
"""관심지역 빌라(연립·다세대) 실거래 분석 — 국토부 연립다세대 매매 API(RTMSDataSvcRHTrade).

  python -I -X utf8 scripts\\villa_analysis.py [--from 2024-10] [--to 2026-10] [--refresh]

- 키: 루트 .env 의 MOLIT_API_KEY (아파트 API와 같은 키, 활용신청은 별도)
- 원본 캐시: data/raw/villa/rh_{시군구}_{YYYYMM}.csv  (최근 2개월은 매번 다시 받음, --refresh 면 전부)
- 결과: data/villa_trades.csv, data/villa_region_stats.csv, data/villa_recent_notable.csv,
        data/villa_summary.json, data/villa_message.txt(텔레그램용, 인사이트 중심)
- 비교 기준: 최근 신고 지연을 피하려고 '올해 3~8월 vs 작년 3~8월'(같은 계절) 거래량·평당가,
  같은 건물·같은 면적끼리 중위가 변화(구성 착시 보정). trades_all.csv 등 기존 파일은 건드리지 않음.
"""
import argparse, datetime as dt, json, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import requests
import fetch_molit_api as M  # .env 로드 + get_key (키는 출력하지 않음)
from common import DATA, RAW, PYEONG

URL = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"
CACHE = RAW / "villa"
CACHE.mkdir(parents=True, exist_ok=True)

REGIONS = [  # key, 이름, 시군구, 읍면동 필터, 리 필터
    ("jeju_edu", "제주 영어교육도시", "50130", ["대정읍"], ["구억리", "보성리", "신평리", "안성리"]),
    ("yeongjong", "영종도", "28155", ["중산동", "운서동", "운남동", "운북동"], None),
    ("yatap", "분당 야탑동", "41135", ["야탑동"], None),
    ("pangyo", "판교", "41135", ["삼평동", "백현동", "판교동", "운중동"], None),
    ("gangnam", "강남구", "11680", None, None),
]
CUR = ("202603", "202608")
PREV = ("202503", "202508")


def months(f, t):
    y, m = map(int, f.split("-")); ty, tm = map(int, t.split("-"))
    while (y, m) <= (ty, tm):
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_month(key, lawd, ym):
    items, page = [], 1
    while True:
        r = requests.get(URL, params={"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ym,
                                      "pageNo": page, "numOfRows": 1000}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} (연립다세대 API 활용신청·승인 확인)")
        root = ET.fromstring(r.content)
        code = root.findtext(".//resultCode")
        if code not in ("00", "000"):
            raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
        items += [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
        if page * 1000 >= int(root.findtext(".//totalCount") or 0):
            return pd.DataFrame(items)
        page += 1
        time.sleep(0.3)


def collect(f, t, refresh):
    key = M.get_key()
    if not key:
        sys.exit("MOLIT_API_KEY가 없습니다(.env).")
    recent = set(list(months(f, t))[-2:])
    frames = []
    for lawd in sorted({r[2] for r in REGIONS}):
        for ym in months(f, t):
            fp = CACHE / f"rh_{lawd}_{ym}.csv"
            if fp.exists() and not refresh and ym not in recent:
                df = pd.read_csv(fp, dtype=str)
            else:
                df = fetch_month(key, lawd, ym)
                df.to_csv(fp, index=False, encoding="utf-8-sig")
                time.sleep(0.4)
            df["lawd"] = lawd
            frames.append(df)
        print("[수집]", lawd, flush=True)
    return pd.concat(frames, ignore_index=True)


def normalize(raw):
    g = lambda c: raw[c] if c in raw else ""
    umd = g("umdNm").astype(str)
    d = pd.DataFrame({
        "lawd": raw["lawd"], "emd": umd.str.split().str[0],
        "ri": umd.apply(lambda s: s.split()[-1] if s.split() and s.split()[-1].endswith("리") else ""),
        "name": g("mhouseNm"), "house_type": g("houseType"), "jibun": g("jibun"),
        "area_m2": pd.to_numeric(g("excluUseAr"), errors="coerce"),
        "ym": g("dealYear").astype(str) + g("dealMonth").astype(str).str.zfill(2),
        "day": pd.to_numeric(g("dealDay"), errors="coerce"),
        "price": pd.to_numeric(g("dealAmount").astype(str).str.replace(",", ""), errors="coerce"),
        "floor": g("floor"), "build_year": pd.to_numeric(g("buildYear"), errors="coerce"),
        "cancel": g("cdealDay").fillna("").astype(str).str.strip(), "deal_type": g("dealingGbn"),
    })
    d = d[d["cancel"].isin(["", "nan", "-"])].copy()
    d["pyeong_price"] = d["price"] / d["area_m2"] * PYEONG
    d["area_bin"] = d["area_m2"].round(0)
    rows = []
    for key, nm, lawd, emd, ri in REGIONS:
        x = d[d["lawd"] == lawd]
        if emd:
            x = x[x["emd"].isin(emd)]
        if ri:
            x = x[x["ri"].isin(ri)]
        rows.append(x.assign(region=key, region_name=nm))
    return pd.concat(rows, ignore_index=True).drop_duplicates()


def inwin(s, w):
    return (s >= w[0]) & (s <= w[1])


def analyze(d):
    stats, notable = [], []
    for key, nm, *_ in REGIONS:
        x = d[d["region"] == key]
        cur, prev = x[inwin(x["ym"], CUR)], x[inwin(x["ym"], PREV)]
        # 같은 건물·같은 면적 중위가 비교
        gk = ["name", "jibun", "area_bin"]
        pc = cur.groupby(gk)["price"].median().to_frame("c").join(prev.groupby(gk)["price"].median().to_frame("p"), how="inner")
        paired = float(((pc["c"] / pc["p"]) - 1).median() * 100) if len(pc) >= 5 else None
        # 최근(7월~) 거래 중 2년 내 최고가·10% 하락
        hist = x.sort_values(["ym", "day"])
        hi = dn = 0
        for _, r in hist[hist["ym"] >= "202607"].iterrows():
            same = hist[(hist["name"] == r["name"]) & (hist["jibun"] == r["jibun"]) & (hist["area_bin"] == r["area_bin"])]
            before = same[(same["ym"] < r["ym"]) | ((same["ym"] == r["ym"]) & (same["day"] < r["day"]))]
            if len(before) == 0:
                continue
            if r["price"] > before["price"].max():
                hi += 1; notable.append({**r.to_dict(), "kind": "2년 내 최고가", "ref": before["price"].max()})
            last12 = before[before["ym"] >= str(int(r["ym"]) - 100)]
            if len(last12) and r["price"] < last12["price"].median() * 0.9:
                dn += 1; notable.append({**r.to_dict(), "kind": "1년 중위 대비 10%↓", "ref": last12["price"].median()})
        stats.append({
            "region": key, "name": nm, "total_24m": len(x),
            "vol_cur": len(cur), "vol_prev": len(prev),
            "vol_chg_pct": (len(cur) / len(prev) - 1) * 100 if len(prev) else None,
            "pp_cur": cur["pyeong_price"].median() if len(cur) else None,
            "pp_prev": prev["pyeong_price"].median() if len(prev) else None,
            "paired_chg_pct": paired, "paired_n": len(pc),
            "since_jul": int((x["ym"] >= "202607").sum()), "new_high": hi, "drop10": dn,
            "median_build_year": x["build_year"].median(),
            "new_build_share": float((cur["build_year"] >= 2021).mean() * 100) if len(cur) else None,
        })
    return pd.DataFrame(stats), pd.DataFrame(notable)


def apt_yoy():
    """아파트 쪽 같은 단지 비교 변화율(보고서 기준) — 빌라와 비교용. 없으면 빈 dict."""
    p = DATA / "summary.json"
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for k, v in (s.items() if isinstance(s, dict) else []):
        if isinstance(v, dict):
            for kk in ("paired_yoy_pct", "paired_median_chg_pct", "paired_chg_pct", "yoy_paired_pct"):
                if isinstance(v.get(kk), (int, float)):
                    out[k] = v[kk]; break
    return out


def fmt_eok(manwon):
    return f"{manwon / 10000:.2f}억".replace(".00억", "억")


def message(st, nt, today):
    by = {r["region"]: r for r in st.to_dict("records")}
    apt = apt_yoy()
    L = [f"📌 [6+] 관심지역 빌라(연립·다세대) ({today:%Y-%m-%d})"]
    # 변화: 거래량·가격 변화가 큰 순
    moves = []
    for r in by.values():
        if r["vol_prev"] >= 10 and r["vol_chg_pct"] is not None:
            moves.append((abs(r["vol_chg_pct"]), f"{r['name']} 거래 {r['vol_chg_pct']:+.0f}%"))
        if r["paired_chg_pct"] is not None:
            moves.append((abs(r["paired_chg_pct"]) * 2, f"{r['name']} 같은 건물 가격 {r['paired_chg_pct']:+.1f}%"))
    moves.sort(reverse=True)
    L.append("🔄 무엇이 바뀌었나 (올해 3~8월 vs 작년 같은 기간)")
    L += ["• " + m for _, m in moves[:3]] or ["• 비교할 거래가 적어 뚜렷한 변화 없음"]
    # 의미
    L.append("💡 무슨 의미")
    hot = [r for r in by.values() if (r["paired_chg_pct"] or 0) >= 5]
    cold = [r for r in by.values() if r["paired_chg_pct"] is not None and r["paired_chg_pct"] <= -3]
    if hot:
        L.append("• " + "·".join(r["name"] for r in hot) + ": 아파트값이 오르자 빌라로 수요가 번지는 '키 맞추기' 신호일 수 있어요")
    if cold:
        thin = any(r["paired_n"] < 10 for r in cold)
        L.append("• " + "·".join(r["name"] for r in cold) + ": 같은 건물끼리 비교해도 값이 내려 약세"
                 + (" (비교 건물이 10곳 미만이라 방향만 참고)" if thin else "") + " — 미분양·공급 과잉 여부를 함께 봐야 해요")
    if not hot and not cold:
        L.append("• 빌라 가격은 대체로 제자리 — 아파트 흐름이 아직 빌라까지 번지지 않았어요")
    # 할 일
    L.append("✅ 내가 할 일")
    je = by.get("jeju_edu")
    if je and je["since_jul"] > 0:
        L.append(f"• 제주 영어교육도시: 7월 이후 {je['since_jul']}건뿐이라 한두 건이 시세를 흔들어요 — 관심 단지는 거래 1건마다 직전가와 비교해 보기")
    yt = by.get("yatap")
    if yt and (yt["paired_chg_pct"] or 0) >= 5:
        L.append("• 야탑: 재건축 기대가 빌라까지 번지는지, 아파트 대비 빌라 가격 격차가 줄어드는지 지켜보기")
    drop_regions = [r["name"] for r in by.values() if r["drop10"] >= 3]
    if drop_regions:
        L.append("• " + "·".join(drop_regions) + ": 10% 넘게 싸게 팔린 거래가 여러 건 — 급매인지 하자·전세 낀 매물인지 등기·전세가율 확인 후 판단")
    else:
        L.append("• 빌라는 전세가율·건물 연식이 가격을 좌우해요 — 관심 매물은 등기부와 전세 시세를 같이 확인")
    # 근거
    L.append("📊 근거 (평당가 중위, 올해 3~8월)")
    for k in ("jeju_edu", "yeongjong", "yatap", "pangyo", "gangnam"):
        r = by.get(k)
        if not r:
            continue
        pp = f"{r['pp_cur']:,.0f}만" if r["pp_cur"] else "-"
        pc = f"{r['paired_chg_pct']:+.1f}%" if r["paired_chg_pct"] is not None else "표본적음"
        L.append(f"• {r['name']}: {r['vol_cur']}건 · 평당 {pp} · 같은건물 {pc} · 7월~ 최고가 {r['new_high']}/하락 {r['drop10']}")
    L.append("※ 최근 2개월은 신고 기한(30일)이 남아 거래가 덜 잡혀요. 매수·매도 권유 아님.")
    txt = "\n".join(L)
    return txt[:1500]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", default="2024-10")
    ap.add_argument("--to", dest="t", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    d = normalize(collect(a.f, a.t, a.refresh))
    d.to_csv(DATA / "villa_trades.csv", index=False, encoding="utf-8-sig")
    st, nt = analyze(d)
    st.to_csv(DATA / "villa_region_stats.csv", index=False, encoding="utf-8-sig")
    nt.to_csv(DATA / "villa_recent_notable.csv", index=False, encoding="utf-8-sig")
    (DATA / "villa_summary.json").write_text(json.dumps(st.to_dict("records"), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    msg = message(st, nt, dt.date.today())
    (DATA / "villa_message.txt").write_text(msg, encoding="utf-8")
    print(st.round(1).to_string())
    print("\n" + msg)


if __name__ == "__main__":
    main()
