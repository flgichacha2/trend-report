# -*- coding: utf-8 -*-
"""
국토부 실거래가 공개시스템(rt.molit.go.kr) '자료제공' 화면의 공개 CSV 다운로드를 이용해
API 키 없이 아파트 매매 실거래 자료를 월 단위로 수집한다.

- 일일 다운로드 최대 100건(IP 기준으로 보임) -> data/raw 캐시 재사용, 최근 2개월만 재다운로드
- 시군구 선택 시 1회 최대 1년 범위 제한 -> 월 단위로 나누어 요청(서버 부담 최소화, 1.5초 간격)
- CSV는 CP949, 상단 안내문 15줄 + 헤더
사용:  python fetch_rt_public.py --from 2024-10 --to 2026-10 [--sgg 11680 41135 ...]
"""
import argparse, io, time, datetime as dt
import requests
import pandas as pd
from common import SGG, RAW, DATA, STD_COLS

HOST = "https://rt.molit.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (research script; public data)"}


def month_range(f, t):
    y, m = map(int, f.split("-")); ty, tm = map(int, t.split("-"))
    while (y, m) <= (ty, tm):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def last_day(y, m):
    n = dt.date(y + (m == 12), m % 12 + 1, 1)
    return (n - dt.timedelta(days=1)).day


def form(sido, sgg, d1, d2):
    return {"srhThingNo": "A", "srhDelngSecd": "1", "srhAddrGbn": "1", "srhLfstsSecd": "1",
            "srhFromDt": d1, "srhToDt": d2, "srhNewRonSecd": "", "srhSidoCd": sido, "srhSggCd": sgg,
            "srhEmdCd": "", "srhHsmpCd": "", "srhArea": "", "srhFromAmount": "", "srhToAmount": "",
            "mobileAt": "", "sidoNm": "", "sggNm": "", "emdNm": "", "loadNm": "", "areaNm": "", "hsmpNm": ""}


def parse_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("cp949", errors="replace")
    lines = text.splitlines()
    hi = next(i for i, l in enumerate(lines) if l.startswith('"NO"'))
    df = pd.read_csv(io.StringIO("\n".join(lines[hi:])), dtype=str)
    return df


def normalize(df: pd.DataFrame, sgg_cd: str) -> pd.DataFrame:
    s = df["시군구"].str.split()
    # 예) "서울특별시 강남구 세곡동" / "경기도 성남분당구 야탑동" / "제주특별자치도 서귀포시 대정읍 구억리"
    out = pd.DataFrame({
        "sgg_cd": sgg_cd,
        "sigungu": df["시군구"],
        "emd": s.apply(lambda x: next((t for t in x[1:] if t.endswith(("동", "읍", "면", "가")) and not t.endswith("구")), x[-1])),
        "ri": s.apply(lambda x: x[-1] if x[-1].endswith("리") else ""),
        "jibun": df["번지"],
        "apt": df["단지명"],
        "area_m2": pd.to_numeric(df["전용면적(㎡)"], errors="coerce"),
        "ym": df["계약년월"],
        "day": pd.to_numeric(df["계약일"], errors="coerce"),
        "price_manwon": pd.to_numeric(df["거래금액(만원)"].str.replace(",", ""), errors="coerce"),
        "dong": df["동"],
        "floor": pd.to_numeric(df["층"], errors="coerce"),
        "build_year": pd.to_numeric(df["건축년도"], errors="coerce"),
        "road": df["도로명"],
        "cancel_date": df["해제사유발생일"].replace("-", ""),
        "deal_type": df["거래유형"],
    })
    return out[STD_COLS]


def fetch(sgg_list, f, t, cache_only=False):
    ses = requests.Session(); ses.headers.update(UA)
    ses.get(f"{HOST}/pt/xls/xls.do?mobileAt=", timeout=30)
    today = dt.date.today()
    frames, missing = [], []
    for sgg in sgg_list:
        sido = SGG[sgg]["sido"]
        for y, m in month_range(f, t):
            d1 = f"{y}-{m:02d}-01"
            d2 = min(dt.date(y, m, last_day(y, m)), today).isoformat()
            cache = RAW / f"rt_{sgg}_{y}{m:02d}.csv"
            recent = (y, m) >= ((today - dt.timedelta(days=62)).year, (today - dt.timedelta(days=62)).month)
            if cache.exists() and (cache_only or not recent):
                df = pd.read_csv(cache, dtype=str)
            elif cache_only:
                print(sgg, y, m, "캐시 없음"); missing.append(f"{sgg}-{y}{m:02d}"); continue
            else:
                data = form(sido, sgg, d1, d2)
                chk = ses.post(f"{HOST}/pt/xls/ptXlsDownDataCheck.do", data=data, timeout=60).json()
                if chk.get("error"):  # 예: 일일 다운로드 횟수 100건 초과
                    print(sgg, y, m, "오류:", chk["error"])
                    if cache.exists():
                        frames.append(normalize(pd.read_csv(cache, dtype=str), sgg))
                    else:
                        missing.append(f"{sgg}-{y}{m:02d}")
                    continue
                if chk.get("cnt", 0) == 0:
                    print(sgg, y, m, "0건"); time.sleep(1); continue
                r = ses.post(f"{HOST}/pt/xls/ptXlsCSVDown.do", data=data, timeout=120)
                r.raise_for_status()
                df = parse_csv(r.content)
                df.to_csv(cache, index=False, encoding="utf-8-sig")
                time.sleep(1.5)
            print(sgg, y, m, len(df), "건")
            frames.append(normalize(df, sgg))
    all_df = pd.concat(frames, ignore_index=True)
    out = DATA / "trades_all.csv"
    all_df.to_csv(out, index=False, encoding="utf-8-sig")
    print("saved", out, len(all_df))
    (DATA / "missing_months.txt").write_text("\n".join(missing), encoding="utf-8")
    if missing:
        print("누락(다음날 재실행 또는 fetch_rt_danji.py로 보완):", missing)
    return all_df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", default="2024-10")
    ap.add_argument("--to", dest="t", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--sgg", nargs="*", default=list(SGG))
    ap.add_argument("--cache-only", action="store_true", help="다운로드 없이 data/raw 캐시로만 trades_all.csv 재구성")
    a = ap.parse_args()
    fetch(a.sgg, a.f, a.t, a.cache_only)
