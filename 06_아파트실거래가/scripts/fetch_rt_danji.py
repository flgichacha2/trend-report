# -*- coding: utf-8 -*-
"""
보완 수집기: 공개시스템 CSV 일일 다운로드 한도(100건) 초과로 빠진 월(data/missing_months.txt)을
지도조회 화면의 단지별 조회(ptDanjiList.do -> ptDtl.do)로 채운다. (다운로드 횟수 차감 없음)
- 읍면동 코드: /data/emd.do,  단지목록: /pt/gis/ptDanjiList.do,  단지 거래: /pt/gis/ptDtl.do (연 단위)
- 건축년도/도로명/동 정보 일부는 제공되지 않음(NaN)
사용: python fetch_rt_danji.py            (missing_months.txt 기준)
      python fetch_rt_danji.py --sgg 28155 --months 202608 202609 202610
"""
import argparse, time
import requests
import pandas as pd
from common import SGG, DATA, RAW, STD_COLS

HOST = "https://rt.molit.go.kr"


def session():
    s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0 (research script; public data)"})
    s.get(f"{HOST}/pt/gis/gis.do?srhThingSecd=A&mobileAt=", timeout=30)
    return s


def danji_list(s, led, year, thing="A"):
    out, page = [], 1
    while True:
        r = s.post(f"{HOST}/pt/gis/ptDanjiList.do", data={"srhThingSecd": thing, "srhYear": year, "srhLadSecd": "1",
                   "srhLedCd": led, "srhRoadCd": "", "srhBldgNm": "", "pageIndex": page, "mobileAt": ""}, timeout=60).json()
        lst = r.get("danjiList") or []
        out += lst
        if not lst or len(out) >= int(r.get("totCnt", 0)):
            return out
        page += 1; time.sleep(0.5)


def danji_trades(s, code, year, thing="A"):
    r = s.post(f"{HOST}/pt/gis/ptDtl.do", data={"srhThingSecd": thing, "srhDelngSecd": "1", "dtlLi": "", "dtlYear": year,
               "dtlMon": "", "dtlArea": "", "dtlAmount": "", "dtlLfstsMtht": "", "srhAprpnHsmpCode": code,
               "dtlGbn1": "", "dtlGbn2": ""}, timeout=60).json()
    return r.get("danjiList") or []


def run(sgg, months):
    s = session()
    emds = s.post(f"{HOST}/data/emd.do", data={"signguCode": sgg}, timeout=30).json()
    years = sorted({m[:4] for m in months})
    rows = []
    for e in emds:
        led = sgg + e["emdCode"]
        for y in years:
            for dj in danji_list(s, led, y):
                for t in danji_trades(s, dj["aprpnHsmpCode"], y):
                    ym = t["cntrctDe"][:6]
                    if ym not in months:
                        continue
                    rows.append({"sgg_cd": sgg, "sigungu": f'{SGG[sgg]["name"]} {e["emdNm"]}', "emd": e["emdNm"], "ri": "",
                                 "jibun": dj.get("mnnm", ""), "apt": dj["aprpnHsmpNm"], "area_m2": float(t["prvuseAr"]),
                                 "ym": ym, "day": int(t["cntrctDd"]), "price_manwon": int(t["thingAmount"].replace(",", "")),
                                 "dong": t.get("dongName", ""), "floor": pd.to_numeric(t.get("floorCo"), errors="coerce"),
                                 "build_year": None, "road": dj.get("roadNm", ""),
                                 "cancel_date": "" if t.get("relisDe") in ("-", None) else t["relisDe"],
                                 "deal_type": t.get("brkrAt", "")})
                time.sleep(0.4)
        print(e["emdNm"], "누적", len(rows))
    return pd.DataFrame(rows, columns=STD_COLS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sgg"); ap.add_argument("--months", nargs="*")
    a = ap.parse_args()
    if a.sgg:
        todo = {a.sgg: set(a.months)}
    else:
        todo = {}
        for line in (DATA / "missing_months.txt").read_text(encoding="utf-8").split():
            g, m = line.split("-"); todo.setdefault(g, set()).add(m)
    if not todo:
        print("누락 월 없음"); raise SystemExit
    allt = pd.read_csv(DATA / "trades_all.csv", dtype=str)
    for g, ms in todo.items():
        df = run(g, ms)
        df.to_csv(RAW / f"danji_{g}_{min(ms)}_{max(ms)}.csv", index=False, encoding="utf-8-sig")
        allt = allt[~((allt["sgg_cd"] == g) & allt["ym"].isin(ms))]
        allt = pd.concat([allt, df.astype(str).replace({"nan": "", "None": ""})], ignore_index=True)
        print(g, sorted(ms), len(df), "건 보완")
    allt.to_csv(DATA / "trades_all.csv", index=False, encoding="utf-8-sig")
