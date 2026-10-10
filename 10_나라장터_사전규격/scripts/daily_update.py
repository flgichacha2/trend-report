# -*- coding: utf-8 -*-
"""
일일 갱신 [10] 정부 장바구니(나라장터 사전규격) -> data/snapshots/YYYYMMDD/
  python -I -X utf8 scripts\\daily_update.py [--days 30]      (cwd = 과제 폴더)

- 최근 N일(기본 30일) 사전규격 목록을 나라장터 공개 조회(로그인 불필요)로 받는다. 약 1만~1.3만 건, 요청 15회 안팎, 1~2분.
  (공공데이터포털 사전규격 API는 활용신청 전이라 사용 안 함. 승인되면 common.try_open_api() 가 OK 를 반환)
- '새 사전규격' = 이번 30일 목록 중 직전 완료 스냅샷(ids.txt.gz)과 보고서 원자료(data/raw/months)에 없던 번호.
- 스냅샷 산출물(가벼움): ids.txt.gz(번호 목록), new_items.csv(새 건만), summary.json(30일 분야 비율·새 건 집계), meta.json(완료 표시)
- 같은 날 재실행: 시작 시 meta.json 을 지우고 오늘 폴더를 다시 채움 -> 안전. 실패 시 종료코드 1.
- data/raw, data/processed(보고서 근거)는 읽기만 한다.
"""
import argparse, datetime as dt, glob, gzip, json, os, re, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from common import (G2B_Client, norm, KEEP, RAW, SNAPROOT, CATS, FOCUS, WATCH, cats, org_type, band, try_open_api)

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
TODAY = dt.date.today()
TD = TODAY.strftime("%Y%m%d")


def done_snaps():
    if not SNAPROOT.exists():
        return []
    return sorted(d for d in os.listdir(SNAPROOT)
                  if re.fullmatch(r"\d{8}", d) and (SNAPROOT / d / "meta.json").exists())


def read_ids(d):
    p = SNAPROOT / d / "ids.txt.gz"
    if not p.exists():
        return set()
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def raw_ids(since):
    ids = set()
    for f in glob.glob(str(RAW / "months" / "*.csv.gz")):
        if os.path.basename(f)[:6] >= since:
            ids |= set(pd.read_csv(f, dtype=str, usecols=["id"]).id)
    return ids


def eok(x):
    return round(float(x) / 1e8, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    t0 = time.time()
    snap = SNAPROOT / TD
    snap.mkdir(parents=True, exist_ok=True)
    meta_p = snap / "meta.json"
    if meta_p.exists():
        meta_p.unlink()
    prev = [d for d in done_snaps() if d < TD]
    prev_d = prev[-1] if prev else None

    api_status = try_open_api()
    print("공공데이터포털 사전규격 API:", api_status, flush=True)
    b = TODAY - dt.timedelta(days=a.days - 1)
    C = G2B_Client()
    rows, tot = C.fetch(f"{b:%Y%m%d}", TD)
    if not rows:
        raise RuntimeError("나라장터 사전규격 목록 조회 결과 0건")
    df = pd.DataFrame([norm(r) for r in rows]).drop_duplicates("id")
    if len(df) < tot * 0.95:
        raise RuntimeError(f"수집 {len(df)}건 < 전체 {tot}건의 95%")
    sw_rows, _ = C.fetch(f"{b:%Y%m%d}", TD, sw="Y")
    df["sw"] = df.id.isin({r.get("oderPlanNo") for r in sw_rows}).map({True: "Y", False: ""})
    df = df[~df.org.str.contains("테스트기관")]
    df["amount"] = pd.to_numeric(df.amount, errors="coerce").fillna(0)
    df["cats"] = df.title.map(cats)
    df["otype"] = df.org.map(org_type)

    known = read_ids(prev_d) if prev_d else set()
    known |= raw_ids(f"{b:%Y%m}")
    new = df[~df.id.isin(known)].copy()
    # 직전 스냅샷이 없고 원자료도 없으면 '새 건' 기준이 없으므로 최근 3일분을 새 건으로 본다
    basis = f"직전 스냅샷({prev_d})" if prev_d else ("보고서 원자료" if known else "최근 3일")
    if not known:
        new = df[df.date >= (TODAY - dt.timedelta(days=2)).strftime("%Y%m%d")].copy()

    # 저장
    with gzip.open(snap / "ids.txt.gz", "wt", encoding="utf-8") as f:
        f.write("\n".join(sorted(df.id)))
    out = new.sort_values("amount", ascending=False).copy()
    out["cats"] = out.cats.map(lambda x: "|".join(x))
    out[KEEP + ["cats", "otype"]].to_csv(snap / "new_items.csv", index=False, encoding="utf-8-sig")

    def has(d, n):
        return d.cats.map(lambda x: n in x).astype(bool) if len(d) else pd.Series([], dtype=bool, index=d.index)

    def share(d, n):
        return round(d.cats.map(lambda x: n in x).mean() * 100, 2) if len(d) else 0.0

    def topl(d, k=5):
        return [{"title": t, "org": o, "amount_eok": eok(am), "cats": c, "date": dd}
                for t, o, am, c, dd in d.sort_values("amount", ascending=False)[["title", "org", "amount", "cats", "date"]].head(k).values]
    focus_new = new[new.cats.map(lambda x: any(n in x for n in ["AI(전체)", "생성형AI·LLM", "정보보호·보안", "클라우드", "개인정보"])).astype(bool)] if len(new) else new
    watch = {}
    for w, rx in WATCH.items():
        s = new[new.org.str.contains(rx, regex=True) | new.dept.str.contains(rx, regex=True)]
        watch[w] = {"n": len(s), "top": topl(s, 2)}
    summ = {
        "date": TD, "window_days": a.days, "window_start": f"{b:%Y%m%d}",
        "n_window": len(df), "amt_window_eok": eok(df.amount.sum()), "sw_share_window": round((df.sw == "Y").mean() * 100, 2),
        "share_window": {n: share(df, n) for n, _ in CATS},
        "n_cat_window": {n: int(df.cats.map(lambda x: n in x).sum()) for n, _ in CATS},
        "new_basis": basis, "n_new": len(new), "amt_new_eok": eok(new.amount.sum()),
        "new_by_cat": {n: int(has(new, n).sum()) for n, _ in CATS},
        "new_amt_by_cat": {n: eok(new[has(new, n)].amount.sum()) for n, _ in CATS},
        "new_by_otype": {k: int(v) for k, v in new.otype.value_counts().items()},
        "new_top": topl(new, 5), "new_focus_top": topl(focus_new, 5),
        "new_big100": int((new.amount >= 1e10).sum()),
        "watch_new": watch,
    }
    json.dump(summ, open(snap / "summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    meta = {"date": TD, "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": round(time.time() - t0, 1), "prev_snapshot": prev_d, "source": "g2b.go.kr 사전규격공개 목록(공개)",
            "open_api_status": api_status, "n_window": len(df), "n_new": len(new), "complete": True}
    json.dump(meta, open(meta_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
