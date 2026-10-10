# -*- coding: utf-8 -*-
"""
초기 수집(보고서용): python -I -X utf8 scripts\\collect.py
 - 공공데이터포털 관세청 API 승인 여부 확인(MOLIT_API_KEY) → data/raw/api_probe.json
 - tradedata.go.kr 월별 품목×국가 수출(최신 월 기준 25개월) → data/raw/monthly_item_country.csv.gz
 - 10일 단위 잠정치(품목·국가, 2025-01 ~ 최신) → data/raw/tentative_items.csv, tentative_countries.csv
"""
import datetime as dt, json, sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import common as C

RAW = C.BASE / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)


def main():
    api = C.probe_api()
    json.dump({"date": dt.date.today().isoformat(), **api}, open(RAW / "api_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[api]", api)
    s = C.TD_Session()
    s.open_menu("/cts/hmpg/openETS0100173Q.do", "ETS_MNK_10500000")
    tmax = C.tentative_maxmonth(s)
    tp = C.fetch_tentative(s, "P", "202501", tmax)
    tn = C.fetch_tentative(s, "N", "202501", tmax)
    tp.to_csv(RAW / "tentative_items.csv", index=False, encoding="utf-8-sig")
    tn.to_csv(RAW / "tentative_countries.csv", index=False, encoding="utf-8-sig")
    print("[tent]", tmax, len(tp), len(tn))
    s.open_menu("/cts/hmpg/openETS0100019Q.do", "ETS_MNK_10200000")
    latest = C.monthly_latest(s, C.ym_add(tmax, -2))
    fr = C.ym_add(latest, -24)
    df = C.fetch_item_country(s, [c for c, *_ in C.ITEMS], fr, latest)
    df.to_csv(RAW / "monthly_item_country.csv.gz", index=False, encoding="utf-8", compression="gzip")
    json.dump({"collected_at": dt.datetime.now().isoformat(timespec="seconds"), "monthly_latest": latest,
               "monthly_from": fr, "tentative_max": tmax, "rows": len(df)},
              open(RAW / "_collect_meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[done]", latest, len(df))


if __name__ == "__main__":
    main()
