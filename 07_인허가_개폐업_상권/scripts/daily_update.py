# -*- coding: utf-8 -*-
"""
일일 자동 갱신: 관심지역(서울 강남구 · 성남 분당구 · 인천 영종 · 제주 서귀포시) 가게 개·폐업
  python -I scripts\\daily_update.py [--days 30] [--force-files]

1) Open API(00_localdata_api.py 의 fetch 재사용, 루트 .env 의 LOCALDATA_API_KEY)
   - 업종 × 4개 지자체 코드로 cond[DAT_UPDT_PNT::GTE]=오늘-45일 '증분' 조회 → 최근 30일 개업/폐업 집계
   - 승인 확인: general_restaurants, bakeries, rest_cafes. 그 외 업종은 시도 후 403 등 실패하면 건너뜀.
2) 파일 다운로드(01_download_localdata_files.py 의 download/reduce 재사용)는 API가 안 되는 업종에 한해
   '주 1회'만: 마지막 파일 기준일이 7일 이상 지났을 때만 받는다. 받은 전국 파일은 임시 폴더에서
   관심지역 행만 추려 data/snapshots/files/YYYYMMDD/ 에 저장하고 원본은 지운다.
   그 사이에는 가장 최근 파일(기존 data/raw/localdata_file 은 읽기 전용)로 집계.
3) 스냅샷: data/snapshots/YYYYMMDD/ (api_events.csv, summary.json, meta.json=완료 표시)
   data/raw, data/processed, charts 는 건드리지 않음. 같은 날 재실행 시 같은 폴더를 다시 씀.
"""
import argparse, datetime as dt, glob, gzip, importlib.util, json, os, shutil, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import pandas as pd


def load_mod(fname, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


API = load_mod("00_localdata_api.py", "localdata_api")      # .env 로드 + fetch()
import common as C

TODAY = dt.date.today()
SNAPROOT = os.path.join(BASE, "data", "snapshots")
BASE_FILES = os.path.join(BASE, "data", "raw", "localdata_file")
ORGS = {"3220000": "서울 강남구", "3780000": "성남 분당구", "3491000": "인천 영종(옛 중구)", "6520000": "제주 서귀포시"}
API_SLUGS = list(C.NAMES)  # 14개 업종 모두 시도, 실패하면 건너뜀


def ymd(d):
    return d.strftime("%Y-%m-%d")


def run_api(days):
    upd_from = (TODAY - dt.timedelta(days=days + 15)).strftime("%Y%m%d") + "000000"
    key = os.environ.get("LOCALDATA_API_KEY")
    if not key:
        raise RuntimeError("LOCALDATA_API_KEY 없음")
    rows, status = [], {}
    for slug in API_SLUGS:
        status[slug] = "ok"
        for org, area in ORGS.items():
            items = None
            for attempt in range(2):
                try:
                    items = API.fetch(slug, key, org=org, updated_from=upd_from)
                    break
                except Exception as e:
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    err = f"{type(e).__name__}{'(' + str(code) + ')' if code else ''}"
                    if code in (401, 403):
                        break
                    time.sleep(3)
            if items is None:
                status[slug] = f"건너뜀: {err}"
                print(f"[api] {slug} {org} 실패 {err} -> 이 업종 건너뜀", flush=True)
                break
            for it in items:
                addr = it.get("ROAD_NM_ADDR") or it.get("LOTNO_ADDR") or ""
                if org == "3780000" and "분당구" not in addr:
                    continue
                rows.append({"slug": slug, "업종": C.NAMES[slug], "area": area, "mng_no": it.get("MNG_NO"),
                             "name": it.get("BPLC_NM"), "업태": it.get("SNTTN_BZSTAT_NM") or it.get("BZSTAT_SE_NM") or "",
                             "lic": (it.get("LCPMT_YMD") or "")[:10], "clo": (it.get("CLSBIZ_YMD") or "")[:10],
                             "status": it.get("SALS_STTS_NM") or "", "updated": it.get("DAT_UPDT_PNT") or "",
                             "addr": addr})
            print(f"[api] {slug} {org} {len(items)}건", flush=True)
            time.sleep(0.5)
    df = pd.DataFrame(rows, columns=["slug", "업종", "area", "mng_no", "name", "업태", "lic", "clo", "status", "updated", "addr"])
    return df.drop_duplicates(["slug", "mng_no"], keep="last"), status


def events(df, ref, days, lic="lic", clo="clo", closed=None):
    """ref 기준 최근 days일 개업/폐업 행"""
    a = ymd(ref - dt.timedelta(days=days - 1))
    b = ymd(ref)
    o = df[(df[lic] >= a) & (df[lic] <= b)]
    cmask = (df[clo] >= a) & (df[clo] <= b)
    if closed is not None:
        cmask &= closed
    return o, df[cmask]


POPUP = r"한시적|팝업|(?i:pop-?up)"


def agg(df, ref, days, closed=None):
    """개업/폐업 수. '실질' = 팝업·한시적 이름 개업 제외 / 인허가 후 60일 이내 폐업(단기 영업) 제외 (보고서와 같은 기준)"""
    out = {}
    df = df.copy()
    df["popup"] = df["name"].fillna("").str.contains(POPUP)
    df["short"] = (pd.to_datetime(df["clo"], errors="coerce") - pd.to_datetime(df["lic"], errors="coerce")).dt.days.le(60)
    for area in ORGS.values():
        x = df[df["area"] == area]
        o30, c30 = events(x, ref, days, closed=closed(x) if closed else None)
        o7, c7 = events(x, ref, 7, closed=closed(x) if closed else None)
        ro, rc = o30[~o30["popup"]], c30[~(c30["short"] | c30["popup"])]
        out[area] = {"open": len(o30), "close": len(c30), "open7": len(o7), "close7": len(c7),
                     "open_real": len(ro), "close_real": len(rc),
                     "open7_real": int((~o7["popup"]).sum()), "close7_real": int((~(c7["short"] | c7["popup"])).sum()),
                     "open_by_type": ro.groupby(["업종", "업태"]).size().sort_values(ascending=False).head(6).to_dict(),
                     "close_by_type": rc.groupby(["업종", "업태"]).size().sort_values(ascending=False).head(6).to_dict(),
                     "popup_open": int(o30["popup"].sum()), "short_close": int((c30["short"] | c30["popup"]).sum())}
        for k in ("open_by_type", "close_by_type"):
            out[area][k] = [[a, b, int(v)] for (a, b), v in out[area][k].items()]
    return out


def last_file_date():
    dates = []
    mp = os.path.join(BASE_FILES, "_download_meta.json")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8"))
        dates += [v.get("downloaded_at", "")[:10] for v in m.values() if v.get("downloaded_at")]
    base_d = min(dates) if dates else None
    snap_ds = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SNAPROOT, "files", "????????"))
                     if os.path.exists(os.path.join(p, "meta.json")))
    snap_d = f"{snap_ds[-1][:4]}-{snap_ds[-1][4:6]}-{snap_ds[-1][6:]}" if snap_ds else None
    return base_d, snap_ds[-1] if snap_ds else None, max([d for d in (base_d, snap_d) if d] or [""])


def file_slug_frames(slugs, force):
    """API 미승인 업종: 최신 파일(주 1회 갱신) 기준 관심지역 행 반환 {slug: (df, asof)}"""
    base_d, snap_dir, last = last_file_date()
    need = force or not last or (TODAY - dt.date.fromisoformat(last)).days >= 7
    out, info = {}, {"last_file_date": last, "downloaded": False}
    if need and slugs:
        D = load_mod("01_download_localdata_files.py", "localdata_files")
        fdir = os.path.join(SNAPROOT, "files", TODAY.strftime("%Y%m%d"))
        work = os.path.join(fdir, "_work"); os.makedirs(work, exist_ok=True)
        D.OUT = work
        shutil.copy(os.path.join(BASE_FILES, "_orgcodes.csv"), work)
        fmeta = {}
        for slug in slugs:
            try:
                path, n = D.download(slug)
                st = D.reduce(slug, path); os.remove(path)
                C.RAW = work
                d = C.load(slug)
                d = d[d["관심지역"] != ""]
                d.drop(columns=[c for c in ("lic", "clo", "is_closed", "is_alive", "영업년수", "short") if c in d]).to_csv(
                    os.path.join(fdir, f"{slug}_areas.csv.gz"), index=False, encoding="utf-8", compression="gzip")
                os.remove(os.path.join(work, f"{slug}.csv.gz"))
                fmeta[slug] = {"downloaded_at": st["downloaded_at"], "rows_total": st["rows_total"], "area_rows": len(d)}
                print(f"[file] {slug} 관심지역 {len(d):,}행", flush=True)
            except Exception as e:
                fmeta[slug] = {"error": type(e).__name__}
                print(f"[file] {slug} 실패 {type(e).__name__}", flush=True)
            time.sleep(5)
        shutil.rmtree(work, ignore_errors=True)
        json.dump({"date": TODAY.isoformat(), "slugs": fmeta}, open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        info["downloaded"] = True
        base_d, snap_dir, last = last_file_date()
        info["last_file_date"] = last
    for slug in slugs:
        d, asof = None, None
        if snap_dir:
            p = os.path.join(SNAPROOT, "files", snap_dir, f"{slug}_areas.csv.gz")
            if os.path.exists(p):
                d = pd.read_csv(p, dtype=str, keep_default_na=False)
                asof = f"{snap_dir[:4]}-{snap_dir[4:6]}-{snap_dir[6:]}"
        if d is None and os.path.exists(os.path.join(BASE_FILES, f"{slug}.csv.gz")):
            C.RAW = BASE_FILES  # 기존 파일은 읽기만
            d = C.load(slug); d = d[d["관심지역"] != ""]
            asof = base_d
        if d is not None:
            out[slug] = (d, asof)
    return out, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--force-files", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    snap = os.path.join(SNAPROOT, TODAY.strftime("%Y%m%d"))
    os.makedirs(snap, exist_ok=True)
    meta_path = os.path.join(snap, "meta.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)

    df, status = run_api(a.days)
    ok = [s for s, v in status.items() if v == "ok"]
    if not ok:
        raise RuntimeError("API로 받은 업종이 하나도 없음")
    df.to_csv(os.path.join(snap, "api_events.csv.tmp"), index=False, encoding="utf-8-sig")
    os.replace(os.path.join(snap, "api_events.csv.tmp"), os.path.join(snap, "api_events.csv"))
    api_sum = agg(df, TODAY, a.days, closed=lambda x: x["status"].eq("폐업"))

    # API 미승인 업종: 파일 기준(주 1회)
    fslugs = [s for s in API_SLUGS if s not in ok]
    frames, finfo = file_slug_frames(fslugs, a.force_files)
    file_sum = {}
    for slug, (d, asof) in frames.items():
        ref = dt.date.fromisoformat(asof) if asof else TODAY
        x = pd.DataFrame({"업종": C.NAMES[slug], "area": d["관심지역"], "name": d["사업장명"], "업태": d.get("업태", ""),
                          "lic": d["인허가일자"].str[:10], "clo": d["폐업일자"].str[:10], "status": d["영업상태명"]})
        file_sum[slug] = {"asof": asof, "areas": agg(x, ref, a.days, closed=lambda y: y["status"].eq("폐업"))}

    summary = {"date": TODAY.isoformat(), "days": a.days, "api_status": status, "api": api_sum,
               "files": file_sum, "file_info": finfo}
    json.dump(summary, open(os.path.join(snap, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prev = sorted(d for d in os.listdir(SNAPROOT)
                  if d.isdigit() and d < os.path.basename(snap) and os.path.exists(os.path.join(SNAPROOT, d, "meta.json")))
    meta = {"date": os.path.basename(snap), "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": round(time.time() - t0, 1), "api_rows": len(df), "api_ok": ok,
            "file_slugs": list(frames), "prev_snapshot": prev[-1] if prev else None, "complete": True}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        v = os.environ.get("LOCALDATA_API_KEY")
        if v:
            from urllib.parse import quote
            msg = msg.replace(v, "***").replace(quote(v, safe=""), "***")
        print(msg, file=sys.stderr)
        sys.exit(1)
