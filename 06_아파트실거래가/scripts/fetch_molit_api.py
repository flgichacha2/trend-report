# -*- coding: utf-8 -*-
"""
공공데이터포털 '국토교통부_아파트 매매 실거래가 자료' API 수집기 (서비스키 필요)
  Endpoint: https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
  Params  : serviceKey, LAWD_CD(시군구 5자리), DEAL_YMD(YYYYMM), pageNo, numOfRows

키: 환경변수 MOLIT_API_KEY 또는 DATA_GO_KR_KEY (일반 인증키 'Decoding' 값 권장)
사용: python fetch_molit_api.py --from 2024-10 --to 2026-10 [--sgg 11680 41135 28110 50130]
결과: data/trades_api.csv (fetch_rt_public.py와 동일 스키마; trades_all.csv는 덮어쓰지 않음) -> analyze.py로 집계/차트
"""
import os, sys, time, argparse, datetime as dt
# 루트 .env 로드 (환경변수가 우선, Encoding 형식 키는 자동으로 Decoding)
from pathlib import Path as _P
from urllib.parse import unquote as _unq
from dotenv import dotenv_values as _dv
for _k, _v in _dv(_P(__file__).resolve().parents[2] / ".env").items():
    if _v and not os.environ.get(_k):
        os.environ[_k] = _unq(_v) if _k.endswith("_KEY") else _v
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from common import SGG, RAW, DATA, STD_COLS

URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"


def get_key():
    k = os.environ.get("MOLIT_API_KEY") or os.environ.get("DATA_GO_KR_KEY")
    if not k:
        sys.exit("환경변수 MOLIT_API_KEY(또는 DATA_GO_KR_KEY)가 없습니다. 보고서 '재실행 방법' 참고. "
                 "키 없이 수집하려면 fetch_rt_public.py 를 사용하세요.")
    return k


def months(f, t):
    y, m = map(int, f.split("-")); ty, tm = map(int, t.split("-"))
    while (y, m) <= (ty, tm):
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_month(key, lawd, ymd, rows=1000):
    items, page = [], 1
    while True:
        r = requests.get(URL, params={"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ymd,
                                      "pageNo": page, "numOfRows": rows}, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        code = root.findtext(".//resultCode")
        if code not in ("00", "000"):
            raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
        for it in root.iter("item"):
            items.append({c.tag: (c.text or "").strip() for c in it})
        total = int(root.findtext(".//totalCount") or 0)
        if page * rows >= total:
            break
        page += 1
        time.sleep(0.3)
    return pd.DataFrame(items)


def normalize(df, lawd):
    if df.empty:
        return pd.DataFrame(columns=STD_COLS)
    g = lambda c: df[c] if c in df else ""
    umd = g("umdNm").astype(str)
    emd = umd.str.split().str[0]
    ri = umd.apply(lambda s: s.split()[-1] if s.split() and s.split()[-1].endswith("리") else "")
    out = pd.DataFrame({
        "sgg_cd": lawd, "sigungu": SGG.get(lawd, {}).get("name", lawd) + " " + umd,
        "emd": emd, "ri": ri, "jibun": g("jibun"), "apt": g("aptNm"),
        "area_m2": pd.to_numeric(g("excluUseAr"), errors="coerce"),
        "ym": g("dealYear").astype(str) + g("dealMonth").astype(str).str.zfill(2),
        "day": pd.to_numeric(g("dealDay"), errors="coerce"),
        "price_manwon": pd.to_numeric(g("dealAmount").astype(str).str.replace(",", ""), errors="coerce"),
        "dong": g("aptDong"), "floor": pd.to_numeric(g("floor"), errors="coerce"),
        "build_year": pd.to_numeric(g("buildYear"), errors="coerce"),
        "road": g("roadNm"),
        "cancel_date": g("cdealDay"), "deal_type": g("dealingGbn"),
    })
    return out[STD_COLS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", default="2024-10")
    ap.add_argument("--to", dest="t", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--sgg", nargs="*", default=list(SGG))
    a = ap.parse_args()
    key = get_key()
    frames = []
    for lawd in a.sgg:
        for ymd in months(a.f, a.t):
            df = fetch_month(key, lawd, ymd)
            df.to_csv(RAW / f"api_{lawd}_{ymd}.csv", index=False, encoding="utf-8-sig")
            print(lawd, ymd, len(df))
            frames.append(normalize(df, lawd))
            time.sleep(0.3)
    all_df = pd.concat(frames, ignore_index=True)
    all_df.to_csv(DATA / "trades_api.csv", index=False, encoding="utf-8-sig")
    print("saved", DATA / "trades_api.csv", len(all_df))


if __name__ == "__main__":
    main()
