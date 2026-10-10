# -*- coding: utf-8 -*-
"""
일일 자동 갱신 [13] 수출 성적표:  python -I -X utf8 scripts\\daily_update.py [--force]   (cwd = 과제 폴더)

1) 공공데이터포털 관세청 API 승인 여부 1회 확인(MOLIT_API_KEY, 키 값은 남기지 않음) → meta.api
2) tradedata.go.kr(키 없음)
   - 10일 단위 잠정치(품목·국가, 최근 14개월) : 요청 3회, 몇 초
   - 월별 품목×국가 확정치의 최신 공개 월 확인 : 요청 1~3회
3) '새 데이터'(잠정치 최신 구간 또는 월별 최신 월이 직전 스냅샷과 다름)가 있을 때만 분석을 다시 한다.
   없으면 직전 스냅샷의 summary.json 을 그대로 복사하고 meta.data_updated=false, kept_from=직전 날짜 로 표시.
   월별 확정치가 새 달이면 품목 15개 × 25개월을 받는다(약 1~2분). 받은 원자료는
   data/snapshots/monthly_cache/YYYYMM.csv.gz (데이터 월 기준 캐시, 약 0.5MB) 에만 둔다(스냅샷에는 넣지 않음).
   같은 월 캐시가 있거나 data/raw(collect.py 결과, 읽기 전용)가 같은 월이면 다시 받지 않는다.
4) 결과: data/snapshots/YYYYMMDD/ (summary.json, tentative.csv, meta.json=완료 표시). 같은 날 재실행 시 같은 폴더를 다시 씀.
   data/raw, data/processed 는 건드리지 않음. 실패 시 종료코드 1.
"""
import argparse, datetime as dt, json, os, shutil, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import pandas as pd
import common as C

TODAY = dt.date.today()
SNAPROOT = C.BASE / "data" / "snapshots"
CACHE = SNAPROOT / "monthly_cache"
RAW = C.BASE / "data" / "raw"


def prev_snapshot(cur):
    if not SNAPROOT.exists():
        return None
    ds = sorted(d.name for d in SNAPROOT.iterdir()
                if d.name.isdigit() and len(d.name) == 8 and d.name < cur and (d / "meta.json").exists())
    return ds[-1] if ds else None


def load_monthly(sess, latest):
    """latest 월 기준 25개월 품목×국가. 캐시 → raw → 새로 받기 순"""
    p = CACHE / f"{latest}.csv.gz"
    if p.exists():
        return pd.read_csv(p, dtype={"ym": str, "hs": str}), "cache"
    rm = RAW / "_collect_meta.json"
    if rm.exists() and json.load(open(rm, encoding="utf-8")).get("monthly_latest") == latest:
        df = pd.read_csv(RAW / "monthly_item_country.csv.gz", dtype={"ym": str, "hs": str})
        src = "raw"
    else:
        sess.open_menu("/cts/hmpg/openETS0100019Q.do", "ETS_MNK_10200000")
        df = C.fetch_item_country(sess, [c for c, *_ in C.ITEMS], C.ym_add(latest, -24), latest)
        src = "fetched"
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / f"{latest}.csv.gz.tmp"
    df.to_csv(tmp, index=False, encoding="utf-8", compression="gzip")
    os.replace(tmp, p)
    for old in sorted(CACHE.glob("*.csv.gz"))[:-3]:  # 최근 3개 월만 보관
        old.unlink()
    return df, src


def build_summary(df, latest, tp, tn):
    res = C.analyze_monthly(df, latest)
    up, down, split, new = C.pick_tops(res)
    rec = lambda d: d.drop(columns=[c for c in ("gap",) if c in d]).to_dict("records")
    return {"monthly_latest": latest, "q3_months": res["q3_months"], "items": res["items"],
            "movers": C.per_item_movers(res), "top_up": rec(up), "top_down": rec(down),
            "split": rec(split), "new_markets": rec(new), "tentative": C.analyze_tentative(tp, tn)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="새 데이터가 없어도 다시 분석")
    a = ap.parse_args()
    t0 = time.time()
    day = TODAY.strftime("%Y%m%d")
    snap = SNAPROOT / day
    snap.mkdir(parents=True, exist_ok=True)
    meta_path = snap / "meta.json"
    if meta_path.exists():
        meta_path.unlink()
    prev = prev_snapshot(day)
    pmeta = json.load(open(SNAPROOT / prev / "meta.json", encoding="utf-8")) if prev else {}

    api = C.probe_api()
    sess = C.TD_Session()
    sess.open_menu("/cts/hmpg/openETS0100173Q.do", "ETS_MNK_10500000")
    tmax = C.tentative_maxmonth(sess)
    fr = C.ym_add(tmax, -13)
    tp = C.fetch_tentative(sess, "P", fr, tmax)
    tn = C.fetch_tentative(sess, "N", fr, tmax)
    if not len(tp) or not len(tn):
        raise RuntimeError("10일 잠정치 응답이 비어 있음")
    last = tp[tp["ym"] == tp["ym"].max()]["period"].tolist()
    tkey = f"{tp['ym'].max()}:{sorted(last, key=lambda s: int(s.split('~')[1]))[-1]}"
    sess.open_menu("/cts/hmpg/openETS0100019Q.do", "ETS_MNK_10200000")
    latest = C.monthly_latest(sess, pmeta.get("monthly_latest") or C.ym_add(tmax, -2))
    if not latest:
        raise RuntimeError("월별 확정치 최신 월을 찾지 못함")

    new_tent = tkey != pmeta.get("tentative_key")
    new_month = latest != pmeta.get("monthly_latest")
    updated = bool(a.force or not prev or new_tent or new_month or not (SNAPROOT / prev / "summary.json").exists())
    src = "kept"
    if updated:
        df, src = load_monthly(sess, latest)
        summary = build_summary(df, latest, tp, tn)
        pd.concat([tp, tn]).to_csv(snap / "tentative.csv.tmp", index=False, encoding="utf-8-sig")
        os.replace(snap / "tentative.csv.tmp", snap / "tentative.csv")
    else:
        summary = json.load(open(SNAPROOT / prev / "summary.json", encoding="utf-8"))
        if (SNAPROOT / prev / "tentative.csv").exists():
            shutil.copy(SNAPROOT / prev / "tentative.csv", snap / "tentative.csv")
    summary.update({"date": TODAY.isoformat(), "data_updated": updated, "kept_from": None if updated else prev,
                    "new_tentative": bool(prev) and new_tent, "new_monthly": bool(prev) and new_month,
                    "tentative_key": tkey})
    with open(snap / "summary.json.tmp", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=float)
    os.replace(snap / "summary.json.tmp", snap / "summary.json")
    meta = {"date": day, "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": round(time.time() - t0, 1), "data_updated": updated,
            "kept_from": None if updated else prev, "monthly_latest": latest, "monthly_source": src,
            "tentative_key": tkey, "new_tentative": new_tent, "new_monthly": new_month,
            "api": api, "prev_snapshot": prev, "complete": True}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        for k in ("MOLIT_API_KEY", "DATA_GO_KR_KEY"):
            v = os.environ.get(k)
            if v:
                from urllib.parse import quote
                msg = msg.replace(v, "***").replace(quote(v, safe=""), "***")
        print(msg, file=sys.stderr)
        sys.exit(1)
