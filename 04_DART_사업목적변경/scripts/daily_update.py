# -*- coding: utf-8 -*-
"""
일일 자동 갱신: 직전 스냅샷 이후 새로 나온 '주주총회소집공고 / 정관변경' 공시에서 사업목적 추가 항목만 뽑는다.
  python -I -X utf8 scripts\\daily_update.py [--days 14] [--budget-min 12]      (cwd = 04 폴더)

- 기간: 직전 완료 스냅샷의 next_from(없으면 그 날짜) ~ 오늘. 첫 회차는 최근 --days(14)일.
  이전 스냅샷들이 이미 확인한 접수번호는 건너뛴다(같은 공시를 두 번 세지 않음).
- 경로: 환경변수 DART_API_KEY(없으면 루트 .env, 환경변수 우선)가 있으면 OpenDART(list.json + document.xml,
  opendart_api_collect.py 재사용). 없거나 키 오류면 KIND 공개 경로(kind_collect.py 재사용).
  파싱·테마 분류는 parse_purposes.py(analyze / themes_of) 그대로.
- 요청: 반드시 순차(1개씩) + 매 요청 전 1.5초 sleep. 403/429/503, 차단 문구, OpenDART status 020(한도 초과),
  재시도 후에도 응답 없음 → '차단'으로 보고 즉시 중단, 종료코드 1 (meta.json 을 쓰지 않음 = 미완료).
- 시간: 원문 조회는 --budget-min(기본 12분) 안에서만. 못 받은 공시는 meta.next_from 으로 다음 회차에 넘김.
- 원문 캐시: KIND = data/kind/(기존 캐시 재사용·추가), OpenDART = data/api_xml/. 스냅샷에는 넣지 않음.
- 스냅샷: data/snapshots/YYYYMMDD/  notices.csv(확인한 공시 목록·상태), new_cases.csv(사업목적 추가 회사),
  summary.json, meta.json(마지막에 기록 = 완료 표시). 기존 분석 파일(data/*.csv 등)은 읽지도 쓰지도 않음.
  같은 날 재실행 시 meta.json 을 먼저 지우고 같은 폴더를 다시 씀(캐시 덕분에 빠름).
"""
import argparse, datetime as dt, glob, json, os, re, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 루트 .env 로드 (환경변수가 우선, Encoding 형식 키는 자동으로 Decoding) - 다른 폴더 스크립트와 같은 방식
from pathlib import Path as _P
from urllib.parse import unquote as _unq
try:
    from dotenv import dotenv_values as _dv
    for _k, _v in _dv(_P(__file__).resolve().parents[2] / ".env").items():
        if _v and not os.environ.get(_k):
            os.environ[_k] = _unq(_v) if _k.endswith("_KEY") else _v
except Exception:
    pass

import pandas as pd  # noqa: E402
import parse_purposes as P  # noqa: E402
import kind_collect as K  # noqa: E402

TODAY = dt.date.today()
SNAPROOT = os.path.join(BASE, "data", "snapshots")
SLEEP = 1.5
REPORTS = ("주주총회소집공고", "정관변경")
HOT = ["AI(인공지능)", "로봇", "데이터센터", "방산", "우주항공", "디지털자산·블록체인·STO(스테이블코인)",
       "원전·원자력", "2차전지·배터리", "반도체", "양자", "드론·UAM"]  # aggregate.extra_stats 와 같은 정의
MARKET = {"Y": "유가증권", "K": "코스닥", "N": "코넥스", "E": "기타"}
BLOCK_TXT = re.compile(r"비정상적인\s*접근|접근이\s*차단|차단되었습니다|Access\s*Denied|too\s*many\s*requests", re.I)


SHOP_NAME = re.compile(r"회사는\s*주식회사|^주식회사$|[이으]?라고?\s*한다|표기한다|표시한다|^영문으로|Co\.,?\s*Ltd|^이라|^[이]?라\s*한다", re.I)


class Blocked(Exception):
    pass


_last = {"t": 0.0, "n": 0}


def polite(fn, *a, **kw):
    """모든 HTTP 요청의 공통 관문: 순차 + 매 요청 전 1.5초 sleep + 차단 감지"""
    for i in range(3):
        time.sleep(SLEEP)
        _last["n"] += 1
        try:
            r = fn(*a, **kw)
        except Exception as e:  # 네트워크 오류는 잠시 쉬고 재시도
            err = type(e).__name__
            time.sleep(5 * (i + 1))
            continue
        if r.status_code in (403, 429, 503):
            raise Blocked(f"HTTP {r.status_code}")
        if r.status_code == 200:
            head = r.content[:3000].decode("utf-8", errors="ignore")
            if BLOCK_TXT.search(head):
                raise Blocked("차단 안내 페이지")
            return r
        err = f"HTTP {r.status_code}"
        time.sleep(5 * (i + 1))
    raise Blocked(f"재시도 3회 실패({err}) - 접속 차단 가능성")


def kind_req(method, url, **kw):  # kind_collect.req 대체 (fetch_one/search_list 가 이걸 쓰게 됨)
    return polite(K.S().request, method, url, timeout=60, verify=False, **kw)


# ---------------------------------------------------------------- 공통
def snaps():
    if not os.path.isdir(SNAPROOT):
        return []
    return sorted(d for d in os.listdir(SNAPROOT)
                  if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(SNAPROOT, d, "meta.json")))


def seen_ids(before):
    """이전 완료 스냅샷들이 '처리 완료'한 접수번호 (pending·error 는 제외 → 다음 회차에 다시 시도)"""
    s = set()
    for d in snaps():
        if d >= before:
            continue
        p = os.path.join(SNAPROOT, d, "notices.csv")
        if os.path.exists(p):
            n = pd.read_csv(p, dtype=str, keep_default_na=False)
            s |= set(n.loc[n["status"].isin(["ok", "cached", "nodoc", "nourl"]), "rcept_no"])
    return s


def clean_items(s):
    """상호 조문 조각 제거. 상호 조각이 2개 이상이고 남은 항목이 2개 이하면 전부 상호 조문으로 보고 비움"""
    items = [x for x in s.split(" | ") if x and x != "nan"]
    bad = [x for x in items if SHOP_NAME.search(x)]
    rest = [x for x in items if x not in bad]
    if len(bad) >= 2 and len(rest) <= 2:
        return ""
    return " | ".join(rest)


def nhot(themes):
    return len([t for t in themes if t in HOT])


# ---------------------------------------------------------------- KIND 경로
def run_kind(frm, to, deadline):
    K.req = kind_req       # 순차·1.5초·차단감지 래퍼로 교체
    K.SLEEP = 0            # 대기는 polite() 가 담당
    frames = []
    for rep in REPORTS:
        df = K.search_list(frm.isoformat(), to.isoformat(), rep)
        if len(df):
            df["report_query"] = rep
            frames.append(df)
        print(f"[kind] '{rep}' {len(df)}건", flush=True)
    if not frames:
        return pd.DataFrame(columns=["rcept_no"])
    lst = pd.concat(frames, ignore_index=True).drop_duplicates("acptno")
    lst = lst.rename(columns={"acptno": "rcept_no"})
    lst["rcept_dt"] = lst["dt"].str[:10].str.replace("-", "")
    recs = []
    for r in lst.sort_values("rcept_no").itertuples():
        st = "pending"
        if time.time() < deadline:
            _, st = K.fetch_one(r.rcept_no)
            if st in ("fail1", "fail2", "fail3"):
                st = "error"
        d = dict(rcept_no=r.rcept_no, rcept_dt=r.rcept_dt, corp_name=r.corp_name, market=r.market,
                 report_nm=r.title, status=st, source="KIND", source_url="")
        sp = os.path.join(K.KDIR, f"{r.rcept_no}_s.html")
        if st in ("ok", "cached") and os.path.exists(sp):
            a = P.analyze(r.rcept_no, K.KDIR)
            m = re.search(r"url=(\S+)", open(sp, encoding="utf-8", errors="replace").read(400))
            d.update(source_url=m.group(1) if m else "", has_aoi_change=a["has_aoi_change"],
                     purpose_change=a["purpose_change"], n_added=a["n_added"], added_items=a["added_items"],
                     reason=a["reason"])
        recs.append(d)
        if len(recs) % 20 == 0:
            print(f"[kind] {len(recs)}/{len(lst)}", flush=True)
    return pd.DataFrame(recs)


# ---------------------------------------------------------------- OpenDART 경로
class KeyError_(Exception):
    pass


def run_api(frm, to, deadline):
    import requests
    import opendart_api_collect as O  # import 시 data/api_xml 생성
    key = os.environ["DART_API_KEY"]

    def get(url, **params):
        return polite(requests.get, url, params=params, timeout=60, verify=False)
    O.get = get; O.SLEEP = 0

    rows = []
    for ty in ("E", "I"):
        page = 1
        while True:
            j = get(O.API + "/list.json", crtfc_key=key, bgn_de=frm.strftime("%Y%m%d"), end_de=to.strftime("%Y%m%d"),
                    pblntf_ty=ty, page_no=page, page_count=100).json()
            stt = j.get("status")
            if stt == "013":  # 조회된 데이터 없음
                break
            if stt == "020":
                raise Blocked("OpenDART 요청 한도 초과(020)")
            if stt in ("010", "011", "012", "901", "100", "101"):
                raise KeyError_(f"OpenDART status {stt}")
            if stt != "000":
                raise RuntimeError(f"OpenDART status {stt}")
            rows += [it for it in j["list"] if any(p in it["report_nm"].replace(" ", "") for p in O.REPORT_PATTERNS)]
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
    lst = pd.DataFrame(rows)
    print(f"[api] 목록 {len(lst)}건", flush=True)
    if lst.empty:
        return pd.DataFrame(columns=["rcept_no"])
    lst = lst.drop_duplicates("rcept_no")
    recs = []
    for r in lst.sort_values("rcept_no").itertuples():
        d = dict(rcept_no=r.rcept_no, rcept_dt=r.rcept_dt, corp_name=r.corp_name,
                 market=MARKET.get(r.corp_cls, r.corp_cls), report_nm=r.report_nm, status="pending", source="OpenDART",
                 source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r.rcept_no}")
        if time.time() < deadline:
            xml = O.document_xml(r.rcept_no)
            d["status"] = "ok" if xml else "nodoc"
            if xml:
                a = O.analyze_xml(xml)
                d.update({k: a[k] for k in ("has_aoi_change", "purpose_change", "n_added", "added_items", "reason")})
        recs.append(d)
    return pd.DataFrame(recs)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="첫 회차 조회 기간(일)")
    ap.add_argument("--budget-min", type=float, default=12.0, help="원문 조회 시간 한도(분)")
    a = ap.parse_args()
    t0 = time.time()
    deadline = t0 + a.budget_min * 60
    tag = TODAY.strftime("%Y%m%d")
    snap = os.path.join(SNAPROOT, tag)
    os.makedirs(snap, exist_ok=True)
    meta_path = os.path.join(snap, "meta.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)  # 재실행 중에는 '미완료' 상태

    prev = [d for d in snaps() if d < tag]
    if prev:
        pm = json.load(open(os.path.join(SNAPROOT, prev[-1], "meta.json"), encoding="utf-8"))
        nf = pm.get("next_from") or f"{prev[-1][:4]}-{prev[-1][4:6]}-{prev[-1][6:]}"
        frm = min(dt.date.fromisoformat(nf), TODAY)
    else:
        frm = TODAY - dt.timedelta(days=a.days)
    seen = seen_ids(tag)

    route, note = "KIND", ""
    if os.environ.get("DART_API_KEY"):
        try:
            df = run_api(frm, TODAY, deadline); route = "OpenDART"
        except KeyError_ as e:
            note = f"{e} → KIND 로 대체"
            print("[api]", note, flush=True)
            df = run_kind(frm, TODAY, deadline)
    else:
        df = run_kind(frm, TODAY, deadline)

    for c, v in (("rcept_dt", ""), ("corp_name", ""), ("market", ""), ("report_nm", ""), ("status", ""),
                 ("source", route), ("source_url", ""), ("has_aoi_change", None), ("purpose_change", False), ("n_added", 0), ("added_items", ""), ("reason", "")):
        if c not in df:
            df[c] = v
    df["n_added"] = df["n_added"].fillna(0).astype(int)
    df["added_items"] = df["added_items"].fillna("")
    df["already_seen"] = df["rcept_no"].isin(seen)
    df.to_csv(os.path.join(snap, "notices.csv.tmp"), index=False, encoding="utf-8-sig")
    os.replace(os.path.join(snap, "notices.csv.tmp"), os.path.join(snap, "notices.csv"))

    # 새 공시만, 회사별 최신 1건(정정본 우선 = 접수번호 큰 것)
    new = df[~df["already_seen"] & df["status"].isin(["ok", "cached"])]
    new = new.sort_values("rcept_no", ascending=False).drop_duplicates("corp_name")
    # 제1조(상호) 문구가 목적 행으로 잘못 잡히는 경우(예: '본 회사는 주식회사 ○○라 한다') 제거
    new = new.copy()
    new["added_items"] = new["added_items"].astype(str).map(clean_items)
    new["n_added"] = new["added_items"].map(lambda s: len([x for x in s.split(" | ") if x]))
    pos = new[new["n_added"] > 0].copy()
    pos["themes"] = pos["added_items"].astype(str).map(lambda s: ";".join(P.themes_of(s)))
    pos["n_hot"] = pos["themes"].astype(str).map(lambda s: nhot([t for t in s.split(";") if t]))
    pos["is_correction"] = pos["report_nm"].astype(str).str.contains("정정", na=False)
    cols = ["corp_name", "market", "added_items", "themes", "n_added", "n_hot", "rcept_dt", "rcept_no",
            "report_nm", "is_correction", "source", "source_url", "reason"]
    pos = pos.sort_values(["n_hot", "n_added", "rcept_no"], ascending=[False, False, False])[cols]
    pos.to_csv(os.path.join(snap, "new_cases.csv.tmp"), index=False, encoding="utf-8-sig")
    os.replace(os.path.join(snap, "new_cases.csv.tmp"), os.path.join(snap, "new_cases.csv"))

    tc = {th: int(pos["themes"].astype(str).str.split(";").map(lambda L: th in L).sum()) for th in P.THEMES}
    pending = df[df["status"].isin(["pending", "error"])]
    summary = {
        "date": TODAY.isoformat(), "route": route, "route_note": note,
        "window": {"from": frm.isoformat(), "to": TODAY.isoformat()},
        "notices_listed": len(df), "notices_new": int((~df["already_seen"]).sum()),
        "notices_parsed_new": len(new), "pending": len(pending),
        "aoi_change_corps": int(new["has_aoi_change"].fillna(False).astype(bool).sum()),
        "purpose_change_corps": int(new["purpose_change"].fillna(False).astype(bool).sum()),
        "purpose_added_corps": len(pos),
        "by_market": pos["market"].value_counts().to_dict(),
        "theme_counts": {k: v for k, v in sorted(tc.items(), key=lambda x: -x[1]) if v},
        "hot3_corps": pos.loc[pos["n_hot"] >= 3, "corp_name"].tolist(),
        "bulk10_corps": pos.loc[pos["n_added"] >= 10, "corp_name"].tolist(),
    }
    json.dump(summary, open(os.path.join(snap, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    next_from = (min(pending["rcept_dt"]) if len(pending) else tag)
    meta = {"date": tag, "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": round(time.time() - t0, 1), "route": route, "requests": _last["n"],
            "window_from": frm.isoformat(), "window_to": TODAY.isoformat(),
            "next_from": f"{next_from[:4]}-{next_from[4:6]}-{next_from[6:]}",
            "prev_snapshot": prev[-1] if prev else None, "complete": True}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({**summary, "meta": meta}, ensure_ascii=False, indent=1))


def _mask(msg):
    v = os.environ.get("DART_API_KEY")
    return msg.replace(v, "***") if v else msg


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        print(f"[중단] 접속 차단 감지: {e}. 스냅샷은 미완료(meta.json 없음). 몇 시간 뒤 재실행하세요.", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print(_mask(traceback.format_exc()), file=sys.stderr)
        sys.exit(1)
