"""매일 자동 갱신(약 3~6분): 앱스토어·구글플레이(한국/미국) 순위 + 크롬 웹스토어 확장 목록을 다시 모아
data/snapshots/YYYYMMDD/ 에 회차별로 저장한다.

기존 수집 코드 재사용
  - daily_collect.collect_apple / collect_gplay  (요청 간 1.5초 sleep)
  - chrome_collect.collect_list                  (요청 간 2.0초 sleep, 리뷰 수집은 생략)
보고서 근거 데이터 보호
  - data/app_ranks.sqlite, data/chrome_extensions_YYYY-MM-DD.csv, data/raw/ 에는 쓰지 않는다.
    (daily_collect.py 는 같은 날짜 행을 INSERT OR REPLACE 하므로 보고서 작성일에 재실행하면 덮어씀
     → 이 스크립트는 스냅샷 폴더로 분리. 원본 JSON(raw)은 용량 때문에 저장 생략)

사용: python -I scripts\\daily_update.py   (작업 디렉터리 = 과제 폴더)
결과: data/snapshots/YYYYMMDD/{app_ranks.csv, chrome_extensions.csv, summary.json}
같은 날 재실행 시 그날 스냅샷을 통째로 교체(idempotent). 실패 시 종료코드 1.
"""
import datetime
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # -I 모드 대응
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd  # noqa: E402

import daily_collect as dc  # noqa: E402  (truststore 주입 포함)
import chrome_collect as cc  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
SNAP_ROOT = os.path.join(DATA, "snapshots")
RANK_COLS = ["collect_date", "store", "country", "chart", "genre", "rank", "app_id", "name", "developer",
             "release_date", "primary_genre", "score"]

# 원본 JSON 을 data/raw/<날짜>/ 에 쓰지 않도록 비활성화(기존 raw 보호 + 용량 절약)
dc.save_raw = lambda *a, **k: None


def write_snapshot(day_dir, files):
    tmp = day_dir + ".tmp"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    for name, obj in files.items():
        p = os.path.join(tmp, name)
        if isinstance(obj, pd.DataFrame):
            obj.to_csv(p, index=False, encoding="utf-8-sig")
        else:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
    if os.path.exists(day_dir):
        shutil.rmtree(day_dir)
    os.rename(tmp, day_dir)


def main():
    t0 = time.time()
    now = datetime.datetime.now()
    day = now.date().isoformat()
    rows = dc.collect_apple(day)
    print("apple rows", len(rows), flush=True)
    rows += dc.collect_gplay(day)
    ranks = pd.DataFrame(rows, columns=RANK_COLS)
    ranks = ranks.drop_duplicates(["store", "country", "chart", "genre", "rank"])
    chrome = cc.collect_list(day)

    cnt = ranks.groupby("store").size().to_dict()
    print("rows by store", cnt, "chrome", len(chrome), flush=True)
    problems = []
    if cnt.get("appstore_itunes", 0) < 1000:
        problems.append(f"앱스토어(iTunes) {cnt.get('appstore_itunes', 0)}행")
    if cnt.get("gplay", 0) < 1000:
        problems.append(f"구글플레이 {cnt.get('gplay', 0)}행")
    if len(chrome) < 300:
        problems.append(f"크롬 확장 {len(chrome)}행")
    if problems:
        print("[FAIL]", "; ".join(problems), flush=True)
        return 1

    summary = {"date": day, "collected_at": now.isoformat(timespec="seconds"),
               "elapsed_sec": round(time.time() - t0, 1), "rows_by_store": cnt,
               "chrome_rows": len(chrome), "chrome_unique": int(chrome.ext_id.nunique())}
    day_dir = os.path.join(SNAP_ROOT, now.strftime("%Y%m%d"))
    os.makedirs(SNAP_ROOT, exist_ok=True)
    write_snapshot(day_dir, {"app_ranks.csv": ranks, "chrome_extensions.csv": chrome, "summary.json": summary})
    print(f"[done] {day_dir} ({summary['elapsed_sec']}s)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa
        import traceback
        traceback.print_exc()
        sys.exit(1)
