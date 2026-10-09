# -*- coding: utf-8 -*-
"""
DART 웹(dart.fss.or.kr) 공개 페이지 기반 수집기 (API 키 불필요)

1) 상세검색(dsab007/detailSearch.ax) 으로 보고서명(예: 주주총회소집공고) + 기간 조회 -> 목록 CSV
2) 공시뷰어(dsaf001/main.do -> report/viewer.do) 에서 '주주총회 목적사항별 기재사항' 노드 HTML 저장(캐시)

사용 예)
  python dart_web_collect.py list   --report 주주총회소집공고 --start 20260201 --end 20260331 --tag 2026Q1
  python dart_web_collect.py fetch  --tag 2026Q1 --workers 2
  (fetch 는 data/list_<tag>.csv 를 읽어 회사별 최신 1건만 받아 data/html/<rcpNo>.html 로 저장)

주의: 조회(GET/POST 검색)만 수행, 로그인/폼 제출 없음. 요청 간 sleep.
사내망 SSL 가로채기(백신 등) 환경 대비 verify=False 사용 (공개 페이지 읽기 전용).
"""
import argparse, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
BASE = "https://dart.fss.or.kr"
H = {"User-Agent": "Mozilla/5.0 (research script; contact: local)"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HTML_DIR = os.path.join(DATA, "html")
os.makedirs(HTML_DIR, exist_ok=True)
SLEEP = 1.2  # DART 는 과다 접속 시 IP 를 일시 차단함(실제 경험: 2~3 병렬 x 0.35s 에서 차단). 1 worker + 1.2s 권장

_local = threading.local()
_fail = {"n": 0}
MAX_CONSEC_FAIL = 8


def sess():
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update(H)
        _local.s = s
    return _local.s


def req(method, url, **kw):
    if _fail["n"] >= MAX_CONSEC_FAIL:
        raise SystemExit("연속 실패 - DART 접속 차단으로 판단, 중단합니다. 수 시간 후 재실행하세요(캐시 이어받기).")
    for i in range(3):
        try:
            r = sess().request(method, url, timeout=90, verify=False, **kw)
            if r.status_code == 200:
                _fail["n"] = 0
                return r
        except Exception as e:  # noqa
            pass
        time.sleep(10 * (i + 1))
    _fail["n"] += 1
    return None


ROW_RE = re.compile(
    r"<tr>\s*<td\s*>\s*(\d+)\s*</td>.*?openCorpInfoNew\('(\d+)'.*?title=\"[^\"]*\"\s*>\s*([^<]+?)\s*</a>"
    r".*?rcpNo=(\d{14})\".*?>(.*?)</a>.*?<td>(\d{4}\.\d{2}\.\d{2})</td>(.*?)</tr>",
    re.S,
)


def search_list(report, start, end):
    rows, page, total_pages = [], 1, 1
    while page <= total_pages:
        data = dict(currentPage=page, maxResults=100, maxLinks=10, sort="date", series="desc",
                    startDate=start, endDate=end, reportName=report)
        r = req("POST", BASE + "/dsab007/detailSearch.ax", data=data)
        if r is None:
            print("list fail page", page); break
        r.encoding = "utf-8"
        m = re.search(r"pageInfo\">\[(\d+)/(\d+)\]\s*\[총\s*([\d,]+)건\]", r.text)
        if m:
            total_pages = int(m.group(2))
        for mm in ROW_RE.finditer(r.text):
            title = re.sub(r"<[^>]+>", "", mm.group(5))
            title = re.sub(r"\s+", " ", title).strip()
            market = re.findall(r'class="tagCom_(\w+)"', mm.group(0))
            rows.append(dict(corp_code=mm.group(2), corp_name=mm.group(3).strip(), rcept_no=mm.group(4),
                             report_nm=title, rcept_dt=mm.group(6).replace(".", ""),
                             market=market[0] if market else ""))
        print(f"  page {page}/{total_pages} rows={len(rows)}", flush=True)
        page += 1
        time.sleep(SLEEP)
    return pd.DataFrame(rows)


NODE_RE = re.compile(
    r"node\d\['text'\] = \"([^\"]*)\";\s*node\d\['id'\] = \"[^\"]*\";\s*node\d\['rcpNo'\] = \"(\d+)\";\s*"
    r"node\d\['dcmNo'\] = \"(\d+)\";\s*node\d\['eleId'\] = \"(\d+)\";\s*node\d\['offset'\] = \"(\d+)\";\s*"
    r"node\d\['length'\] = \"(\d+)\";\s*node\d\['dtd'\] = \"([^\"]*)\";", re.S)


def toc(rcp):
    r = req("GET", BASE + f"/dsaf001/main.do?rcpNo={rcp}")
    time.sleep(SLEEP)
    if r is None:
        return None, []
    r.encoding = "utf-8"
    nodes = [dict(text=m.group(1), rcpNo=m.group(2), dcmNo=m.group(3), eleId=m.group(4), offset=m.group(5),
                  length=m.group(6), dtd=m.group(7)) for m in NODE_RE.finditer(r.text)]
    first = re.search(r'viewDoc\("(\d+)", "(\d+)", "(\d+)", "(\d+)", "(\d+)", "(\w+)"', r.text)
    return first, nodes


def viewer(rcp, dcm, ele, off, ln, dtd):
    r = req("GET", BASE + "/report/viewer.do",
            params=dict(rcpNo=rcp, dcmNo=dcm, eleId=ele, offset=off, length=ln, dtd=dtd))
    time.sleep(SLEEP)
    if r is None:
        return None
    b = r.content
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp949", errors="replace")


def _save(path, rcp, label, html):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!-- rcpNo={rcp} node={label} -->\n" + html)


def _pick(nodes, keys):
    for key in keys:
        for n in nodes:
            if key in n["text"].replace(" ", ""):
                return n
    return None


SMALL_KEYS = ("주주총회소집공고", "소집공고", "주주총회소집결의", "소집결의")
BIG_KEYS = ("목적사항별", "정관", "경영참고사항")


def fetch_one(rcp, big=False):
    """small: 소집공고/소집결의 본문(안건 목록, 수 KB)  big: '목적사항별 기재사항'(정관 신구조문 대비표 포함, 수백 KB)"""
    sp = os.path.join(HTML_DIR, f"{rcp}_s.html")
    bp = os.path.join(HTML_DIR, f"{rcp}_b.html")
    need_s = not (os.path.exists(sp) and os.path.getsize(sp) > 200)
    need_b = big and not (os.path.exists(bp) and os.path.getsize(bp) > 200)
    if not need_s and not need_b:
        return rcp, "cached"
    first, nodes = toc(rcp)
    if need_s:
        # 표지(첫 노드, 텍스트 '주주총회소집공고')가 아닌 본문 노드('주주총회 소집공고')를 우선
        cand = [x for x in nodes if any(k in x["text"].replace(" ", "") for k in SMALL_KEYS)]
        n = cand[1] if len(cand) > 1 else (cand[0] if cand else None)
        if n:
            html = viewer(rcp, n["dcmNo"], n["eleId"], n["offset"], n["length"], n["dtd"])
        elif first:  # 단일 문서(거래소 공시 등)
            g = first.groups(); html = viewer(*g)
        else:
            return rcp, "no_toc"
        if not html:
            return rcp, "fail_s"
        _save(sp, rcp, n["text"] if n else "first", html)
    if need_b:
        n = _pick(nodes, BIG_KEYS)
        if not n:
            return rcp, "no_big"
        html = viewer(rcp, n["dcmNo"], n["eleId"], n["offset"], n["length"], n["dtd"])
        if not html:
            return rcp, "fail_b"
        _save(bp, rcp, n["text"], html)
    return rcp, "ok"


def latest_per_corp(df):
    # 목록은 접수일 내림차순 -> 회사별 첫 행 = 최신(정정 포함) 1건
    df = df.sort_values("rcept_no", ascending=False)
    return df.drop_duplicates("corp_code", keep="first")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "fetch"])
    ap.add_argument("--report", default="주주총회소집공고")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--big", action="store_true", help="정관 대비표가 있는 큰 노드도 받기")
    ap.add_argument("--rcpfile", help="rcpNo 목록 파일(한 줄 1개) - 지정 시 이 목록만 받음")
    a = ap.parse_args()
    lp = os.path.join(DATA, f"list_{a.tag}.csv")
    if a.cmd == "list":
        df = search_list(a.report, a.start, a.end)
        df.to_csv(lp, index=False, encoding="utf-8-sig")
        print("saved", lp, len(df), "unique corp", df.corp_code.nunique())
    else:
        df = latest_per_corp(pd.read_csv(lp, dtype=str))
        rcps = list(df.rcept_no)
        if a.rcpfile:
            rcps = [x.strip() for x in open(a.rcpfile, encoding="utf-8") if x.strip()]
        if a.limit:
            rcps = rcps[: a.limit]
        print("fetch", len(rcps), flush=True)
        done = 0
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(fetch_one, r, a.big) for r in rcps]
            for f in as_completed(futs):
                done += 1
                rcp, st = f.result()
                if st not in ("ok", "cached") or done % 50 == 0:
                    print(done, rcp, st, flush=True)
        print("done")


if __name__ == "__main__":
    main()
