# -*- coding: utf-8 -*-
"""
일일 자동 갱신: 관심지역 최근 거래를 다시 받아 분석 -> data/snapshots/YYYYMMDD/

  python -I scripts\\daily_update.py [--months 4]

- 아파트: 공공데이터포털 API(fetch_molit_api.py 재사용, 루트 .env 의 MOLIT_API_KEY)로
  4개 시군구(50130, 28155, 41135, 11680) × 최근 N개월(기본 4: 지난 3개월 + 이번 달) = 16회 호출.
- 제주 영어교육도시(연립·다세대): 연립다세대 API는 미승인(403)이라, 기존 방식(fetch_rt_danji.py의
  공개 단지별 조회, 키·로그인 불필요)으로 대정읍 구억·보성·신평·안성리 단지의 올해 거래만 다시 받음.
  실패해도 전체를 멈추지 않고 기존 데이터로 대체(meta.json에 표시).
- 분석: 보고서 근거 데이터 data/trades_all.csv(읽기 전용) 중 최근 N개월만 새 데이터로 바꾼 '임시 결합본'을
  만들어 analyze.py 를 그대로 돌린다. 결합본·차트는 임시 폴더에서 만들고 지운다.
  -> data/trades_all.csv, data/*.csv, charts/ 는 절대 건드리지 않음.
- 스냅샷: trades_window.csv(최근 N개월 거래), summary.json, monthly/newhigh/drop10/period/paired/top_complexes_*.csv,
  meta.json(완료 표시). 같은 날 재실행 시 같은 폴더를 다시 씀(안전).
"""
import argparse, datetime as dt, json, os, shutil, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I 에서도 같은 폴더 모듈 import
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import pandas as pd

import fetch_molit_api as M          # .env 로드(키는 출력하지 않음) + fetch_month/normalize
from common import DATA, SGG, STD_COLS, PYEONG

TODAY = dt.date.today()
SNAPROOT = DATA / "snapshots"
JEJU_LED, JEJU_RI = "5013025000", ("구억리", "보성리", "신평리", "안성리")


def window_months(n):
    y, m = TODAY.year, TODAY.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return sorted(out)


def fetch_api(months):
    key = M.get_key()
    frames, log = [], []
    for lawd in SGG:
        for ym in months:
            for attempt in range(3):
                try:
                    df = M.fetch_month(key, lawd, ym)
                    break
                except Exception as e:  # 키가 메시지에 섞이지 않도록 예외 타입만 기록
                    err = type(e).__name__
                    time.sleep(3)
            else:
                raise RuntimeError(f"API 수집 실패 {lawd} {ym} ({err})")
            frames.append(M.normalize(df, lawd))
            log.append(f"{lawd} {ym} {len(df)}")
            print("[api]", lawd, ym, len(df), flush=True)
            time.sleep(0.5)
    return pd.concat(frames, ignore_index=True), log


def fetch_jeju(years):
    from fetch_rt_danji import session, danji_list, danji_trades
    s = session(); rows = []; seen = set()
    for thing, label in (("A", "아파트"), ("B", "연립다세대")):
        for y in years:
            for dj in danji_list(s, JEJU_LED, y, thing):
                if not dj["ledNm"].endswith(JEJU_RI):
                    continue
                k = (thing, dj["aprpnHsmpCode"], y)
                if k in seen:
                    continue
                seen.add(k)
                for t in danji_trades(s, dj["aprpnHsmpCode"], y, thing):
                    rows.append({"유형": label, "리": dj["ledNm"].split()[-1], "단지": dj["aprpnHsmpNm"], "번지": dj["mnnm"],
                                 "계약일": t["cntrctDe"], "ym": t["cntrctDe"][:6], "전용㎡": float(t["prvuseAr"]),
                                 "거래가(만원)": int(t["thingAmount"].replace(",", "")), "층": t.get("floorCo"),
                                 "해제": t.get("relisDe"), "거래유형": t.get("brkrAt")})
                time.sleep(0.4)
    df = pd.DataFrame(rows, columns=["유형", "리", "단지", "번지", "계약일", "ym", "전용㎡", "거래가(만원)", "층", "해제", "거래유형"]).drop_duplicates()
    df["평당(만원)"] = (df["거래가(만원)"] / df["전용㎡"] * PYEONG).round(0)
    print("[jeju] 연립·다세대/아파트", len(df), "건", flush=True)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    months = window_months(a.months)
    snap = SNAPROOT / TODAY.strftime("%Y%m%d")
    snap.mkdir(parents=True, exist_ok=True)
    meta_path = snap / "meta.json"
    if meta_path.exists():
        meta_path.unlink()
    work = snap / "_work"
    shutil.rmtree(work, ignore_errors=True); (work / "charts").mkdir(parents=True)

    # 1) 아파트(API)
    api, api_log = fetch_api(months)
    base = pd.read_csv(DATA / "trades_all.csv", dtype={"sgg_cd": str, "ym": str, "cancel_date": str, "ri": str})
    keep = base[~(base["sgg_cd"].isin(list(SGG)) & base["ym"].isin(months))]
    comb = pd.concat([keep, api[STD_COLS]], ignore_index=True)
    comb.to_csv(work / "trades_all.csv", index=False, encoding="utf-8-sig")

    # 2) 제주 영어교육도시(연립·다세대)
    jbase = pd.read_csv(DATA / "jeju_edu_town_trades.csv", dtype={"ym": str, "계약일": str, "해제": str})
    years = sorted({m[:4] for m in months})
    jeju_status = "ok"
    try:
        jnew = fetch_jeju(years)
        jnew = jnew[jnew["ym"] >= "202410"]
        jcomb = pd.concat([jbase[~jbase["ym"].str[:4].isin(years)], jnew], ignore_index=True)
    except Exception as e:
        jeju_status = f"갱신 실패({type(e).__name__}) - 기존 데이터 사용"
        print("[jeju]", jeju_status, file=sys.stderr)
        jnew = jbase[jbase["ym"].isin(months)]
        jcomb = jbase
    jcomb.to_csv(work / "jeju_edu_town_trades.csv", index=False, encoding="utf-8-sig")

    # 3) 최근 N개월 거래 원장(회차 비교용)
    jw = jnew[jnew["ym"].isin(months)]
    jw_std = pd.DataFrame({"sgg_cd": "50130B", "sigungu": "제주 서귀포시 대정읍 " + jw["리"], "emd": "대정읍", "ri": jw["리"],
                           "jibun": jw["번지"], "apt": jw["단지"], "area_m2": jw["전용㎡"], "ym": jw["ym"],
                           "day": jw["계약일"].astype(str).str[6:8].astype(int), "price_manwon": jw["거래가(만원)"], "dong": "",
                           "floor": pd.to_numeric(jw["층"], errors="coerce"), "build_year": None, "road": "",
                           "cancel_date": jw["해제"].fillna("").replace("-", ""), "deal_type": jw["거래유형"]})
    win = pd.concat([api[STD_COLS], jw_std[STD_COLS]], ignore_index=True)
    win.to_csv(snap / "trades_window.csv.tmp", index=False, encoding="utf-8-sig")
    os.replace(snap / "trades_window.csv.tmp", snap / "trades_window.csv")

    # 4) analyze.py 재사용(경로만 임시 폴더로)
    import analyze as A
    A.DATA = work; A.CHARTS = work / "charts"
    argv = sys.argv; sys.argv = ["analyze.py", "--asof", TODAY.isoformat(), "--recent", "3"]
    try:
        A.main()
    finally:
        sys.argv = argv
    for f in work.iterdir():
        if f.is_file() and f.name not in ("trades_all.csv", "jeju_edu_town_trades.csv", "analysis_tables.md"):
            os.replace(f, snap / f.name)
    shutil.rmtree(work, ignore_errors=True)

    prev = sorted(p.name for p in SNAPROOT.iterdir()
                  if p.is_dir() and p.name.isdigit() and p.name < snap.name and (p / "meta.json").exists())
    meta = {"date": snap.name, "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": round(time.time() - t0, 1), "window_months": months, "api_calls": api_log,
            "api_rows": len(api), "jeju_status": jeju_status, "jeju_window_rows": len(jw),
            "prev_snapshot": prev[-1] if prev else None, "complete": True}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        for k in ("MOLIT_API_KEY", "DATA_GO_KR_KEY"):  # 혹시라도 키가 섞이면 가림
            v = os.environ.get(k)
            if v:
                msg = msg.replace(v, "***")
                from urllib.parse import quote
                msg = msg.replace(quote(v, safe=""), "***")
        print(msg, file=sys.stderr)
        sys.exit(1)
