# -*- coding: utf-8 -*-
"""
초기(보고서용) 수집: 나라장터 사전규격 목록을 월 단위로 받아 data/raw/ 에 저장.
  python -I -X utf8 scripts\\collect.py [--from 2026-04 --to 2026-10] [--yoy]

- 기본: 최근 약 6개월(2026-04-01 ~ 오늘) + --yoy 이면 1년 전 같은 기간(2025-04-01 ~ 2025-10-오늘일)
- 월별 파일 data/raw/months/YYYYMM.csv.gz (이미 있으면 건너뜀, 이번 달은 항상 다시 받음) -> 재실행 안전
- SW사업 대상 여부는 같은 조회에 swBizTrgtYn=Y 필터를 걸어 id 집합으로 표시(sw=Y)
- 요청 간 1.5초, 순차 요청
"""
import argparse, datetime as dt, sys, time
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I 실행 대응
import pandas as pd
from common import G2B_Client, norm, RAW, KEEP, try_open_api

sys.stdout.reconfigure(encoding="utf-8")


def month_ranges(f, t, today):
    y, m = map(int, f.split("-")); ty, tm = map(int, t.split("-"))
    while (y, m) <= (ty, tm):
        b = dt.date(y, m, 1)
        e = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        yield b, min(e, today)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="f", default="2026-04")
    ap.add_argument("--to", dest="t", default=None)
    ap.add_argument("--yoy", action="store_true")
    a = ap.parse_args()
    today = dt.date.today()
    a.t = a.t or f"{today:%Y-%m}"
    print("공공데이터포털 API 상태:", try_open_api())
    out = RAW / "months"; out.mkdir(parents=True, exist_ok=True)
    jobs = list(month_ranges(a.f, a.t, today))
    if a.yoy:
        fy, fm = map(int, a.f.split("-")); ty, tm = map(int, a.t.split("-"))
        ly = today.replace(year=today.year - 1)
        jobs = list(month_ranges(f"{fy-1}-{fm:02d}", f"{ty-1}-{tm:02d}", ly)) + jobs
    C = G2B_Client()
    for b, e in jobs:
        p = out / f"{b:%Y%m}.csv.gz"
        complete_month = (e.month != (e + dt.timedelta(days=1)).month) and e < today
        if p.exists() and complete_month:
            print(f"[{b:%Y-%m}] 있음 → 건너뜀"); continue
        rows, tot = C.fetch(f"{b:%Y%m%d}", f"{e:%Y%m%d}")
        df = pd.DataFrame([norm(r) for r in rows]).drop_duplicates("id")
        sw_rows, sw_tot = C.fetch(f"{b:%Y%m%d}", f"{e:%Y%m%d}", sw="Y")
        sw_ids = {r.get("oderPlanNo") for r in sw_rows}
        df["sw"] = df["id"].isin(sw_ids).map({True: "Y", False: ""})
        print(f"[{b:%Y-%m}] {len(df):,}건(총 {tot:,}) SW대상 {df.sw.eq('Y').sum():,}건(필터 총 {sw_tot:,})", flush=True)
        if len(df) < tot * 0.97:
            print(f"  경고: 수집 {len(df)} < totCnt {tot}")
        df[KEEP].to_csv(p, index=False, encoding="utf-8-sig", compression="gzip")
    print("완료")


if __name__ == "__main__":
    main()
