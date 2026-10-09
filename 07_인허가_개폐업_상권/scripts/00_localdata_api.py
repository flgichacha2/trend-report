# -*- coding: utf-8 -*-
"""
공공데이터포털 '행정안전부_{업종} 조회서비스' Open API 수집기 (LOCALDATA 이관판, 2026)
- Endpoint : https://apis.data.go.kr/1741000/{slug}/info   (예: general_restaurants, rest_cafes ...)
             https://apis.data.go.kr/1741000/{slug}/history (BASE_DATE 기준 상태 조회)
- 필수     : serviceKey, pageNo, numOfRows(<=100)
- 조건     : cond[LCPMT_YMD::GTE]=YYYYMMDD, cond[LCPMT_YMD::LT], cond[OPN_ATMY_GRP_CD::EQ]=3220000,
             cond[DAT_UPDT_PNT::GTE]=YYYYMMDDHHMMSS (증분 수집), cond[SALS_STTS_CD::EQ], cond[BPLC_NM::LIKE]
- 키       : 환경변수 LOCALDATA_API_KEY (공공데이터포털에서 '활용신청' 후 발급받은 Decoding 키)
- 키가 없으면 안내만 출력하고 종료(파일 다운로드 방식은 01_download_localdata_files.py 사용).

예) python -I scripts/00_localdata_api.py general_restaurants --org 3220000 --from 20250101
"""
import argparse, json, os, sys, time
# 루트 .env 로드 (환경변수가 우선, Encoding 형식 키는 자동으로 Decoding)
from pathlib import Path as _P
from urllib.parse import unquote as _unq
from dotenv import dotenv_values as _dv
for _k, _v in _dv(_P(__file__).resolve().parents[2] / ".env").items():
    if _v and not os.environ.get(_k):
        os.environ[_k] = _unq(_v) if _k.endswith("_KEY") else _v
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "raw", "localdata_api")


def fetch(slug, key, org=None, lic_from=None, lic_to=None, updated_from=None, max_pages=10000):
    url = f"https://apis.data.go.kr/1741000/{slug}/info"
    items, page = [], 1
    while page <= max_pages:
        p = {"serviceKey": key, "pageNo": page, "numOfRows": 100, "returnType": "json"}
        if org: p["cond[OPN_ATMY_GRP_CD::EQ]"] = org
        if lic_from: p["cond[LCPMT_YMD::GTE]"] = lic_from
        if lic_to: p["cond[LCPMT_YMD::LT]"] = lic_to
        if updated_from: p["cond[DAT_UPDT_PNT::GTE]"] = updated_from
        r = requests.get(url, params=p, timeout=60)
        r.raise_for_status()
        body = r.json().get("response", {}).get("body", {})
        it = body.get("items", {}) or {}
        it = it.get("item", []) if isinstance(it, dict) else it
        if isinstance(it, dict):
            it = [it]
        items += it
        total = int(body.get("totalCount", 0) or 0)
        print(f"  page {page}: +{len(it)} / total {total}", flush=True)
        if not it or page * 100 >= total:
            break
        page += 1
        time.sleep(0.2)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--org"); ap.add_argument("--from", dest="lic_from"); ap.add_argument("--to", dest="lic_to")
    ap.add_argument("--updated-from")
    a = ap.parse_args()
    key = os.environ.get("LOCALDATA_API_KEY")
    if not key:
        print("LOCALDATA_API_KEY 환경변수가 없습니다. 공공데이터포털(data.go.kr)에서 "
              "'행정안전부_식품_일반음식점 조회서비스' 등 활용신청 후 키를 설정하세요.\n"
              "키 없이 수집하려면 scripts/01_download_localdata_files.py (파일 다운로드)를 사용하세요.")
        sys.exit(0)
    os.makedirs(OUT, exist_ok=True)
    items = fetch(a.slug, key, a.org, a.lic_from, a.lic_to, a.updated_from)
    fn = os.path.join(OUT, f"{a.slug}_{a.org or 'all'}_{a.lic_from or ''}.json")
    json.dump(items, open(fn, "w", encoding="utf-8"), ensure_ascii=False)
    print("saved", fn, len(items))


if __name__ == "__main__":
    main()
