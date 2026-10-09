# -*- coding: utf-8 -*-
"""
KIND(kind.krx.co.kr) 공개 공시검색으로 '주주총회소집공고'(기본값, --report 로 소집결의 등 변경 가능) 목록+본문 수집.
 - DART 웹이 과다접속으로 일시 차단될 때의 대체 경로. 소집결의 본문에는 '주주총회 안건 세부내역'(안건명/비고)이 있어
   '사업목적 추가/변경' 안건 여부를 1차 판별할 수 있음(상세 신구조문 대비표는 DART 소집공고에만 있음).
사용:
  python kind_collect.py list  --start 2026-01-01 --end 2026-03-31 --tag 2026H1reg
  python kind_collect.py fetch --tag 2026H1reg --workers 2
출력: data/kind_list_<tag>.csv, data/kind/<acptno>.html
"""
import argparse, os, re, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_purposes as P  # noqa
import requests
import urllib3

urllib3.disable_warnings()
BASE = "https://kind.krx.co.kr"
H = {"User-Agent": "Mozilla/5.0", "Referer": BASE + "/disclosure/details.do?method=searchDetailsMain"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KDIR = os.path.join(DATA, "kind")
os.makedirs(KDIR, exist_ok=True)
SLEEP = 0.5
_l = threading.local()


def S():
    if not hasattr(_l, "s"):
        _l.s = requests.Session(); _l.s.headers.update(H)
    return _l.s


def req(method, url, **kw):
    for i in range(5):
        try:
            r = S().request(method, url, timeout=60, verify=False, **kw)
            if r.status_code == 200:
                return r
        except Exception:
            pass
        time.sleep(5 * (i + 1))
    return None


ROW = re.compile(r"<tr[^>]*>\s*<td class=\"first txc\">(\d+)</td>\s*<td class=\"txc\">([\d\- :]+)</td>\s*<td>(.*?)</td>\s*"
                 r"<td><a href=\"#viewer\" onclick=\"openDisclsViewer\('(\d+)',''\)\" title='([^']*)'>(.*?)</a></td>\s*<td>([^<]*)</td>", re.S)


def search_list(start, end, report):
    rows, page = [], 1
    while True:
        d = dict(method="searchDetailsSub", forward="details_sub", currentPageSize="100", pageIndex=str(page),
                 orderMode="1", orderStat="D", fromDate=start, toDate=end, reportNm=report, reportNmTemp=report,
                 searchCodeType="", repIsuSrtCd="", allRepIsuSrtCd="", searchCorpName="")
        r = req("POST", BASE + "/disclosure/details.do", data=d)
        if r is None:
            print("fail page", page); break
        r.encoding = "utf-8"
        got = 0
        soup = BeautifulSoup(r.text, "html.parser")
        for tr in soup.select("table.list tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            a_ = tds[3].find("a", onclick=re.compile("openDisclsViewer"))
            if not a_:
                continue
            acpt = re.search(r"openDisclsViewer\('(\d+)'", a_["onclick"]).group(1)
            comp = tds[2].find("a")
            mk = tds[2].find("img")
            rows.append(dict(acptno=acpt, dt=tds[1].get_text(strip=True),
                             corp_name=comp.get_text(strip=True) if comp else tds[2].get_text(strip=True),
                             market=mk.get("alt", "") if mk else "", title=a_.get_text(strip=True),
                             submitter=tds[4].get_text(strip=True)))
            got += 1
        print(f"page {page} got {got} total {len(rows)}", flush=True)
        if got < 100:
            break
        page += 1
        time.sleep(SLEEP)
    return pd.DataFrame(rows)


def fetch_one(acpt):
    p = os.path.join(KDIR, f"{acpt}_s.html")
    if os.path.exists(p) and os.path.getsize(p) > 300:
        return acpt, "cached"
    r = req("GET", BASE + "/common/disclsviewer.do", params=dict(method="search", acptno=acpt, docno="", viewerhost="", viewerport=""))
    time.sleep(SLEEP)
    if r is None:
        return acpt, "fail1"
    r.encoding = "utf-8"
    opts = re.findall(r"<option value='(\d+)\|([YN])'", r.text)
    if not opts:
        return acpt, "nodoc"
    # 정정공시는 원본(N)과 정정본(Y)이 함께 있음 -> 최신본(Y) 우선
    doc = next((d for d, y in opts if y == "Y"), opts[-1][0])
    r2 = req("GET", BASE + "/common/disclsviewer.do", params=dict(method="searchContents", docNo=doc))
    time.sleep(SLEEP)
    if r2 is None:
        return acpt, "fail2"
    r2.encoding = "utf-8"
    u = [x for x in re.findall(r"'(https?://[^']+\.htm)'", r2.text) if not x.endswith("_toc.htm")]
    if not u:
        return acpt, "nourl"
    r3 = req("GET", u[0].replace("http://", "https://"))
    time.sleep(SLEEP)
    if r3 is None:
        return acpt, "fail3"
    b = r3.content
    try:
        h = b.decode("utf-8")
    except UnicodeDecodeError:
        h = b.decode("cp949", errors="replace")
    # 용량 절약: 안건부(앞 40,000자)와 '□ 정관의 변경' 섹션만 저장
    head = h[:40000]
    sec = P.section_html(h) or ""
    meta = f"<!-- acptno={acpt} url={u[0]} len={len(h)} -->\n"
    with open(os.path.join(KDIR, f"{acpt}_b.html"), "w", encoding="utf-8") as f:
        f.write(meta + sec)
    with open(p, "w", encoding="utf-8") as f:
        f.write(meta + head)
    return acpt, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "fetch"])
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--tag", required=True)
    ap.add_argument("--report", default="주주총회소집공고")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--refetch-corrections", action="store_true", help="[정정] 공시 캐시 삭제 후 재수집")
    a = ap.parse_args()
    lp = os.path.join(DATA, f"kind_list_{a.tag}.csv")
    if a.cmd == "list":
        df = search_list(a.start, a.end, a.report)
        df.to_csv(lp, index=False, encoding="utf-8-sig")
        print("saved", lp, len(df), "corps", df.corp_name.nunique())
    else:
        df = pd.read_csv(lp, dtype=str).sort_values("acptno", ascending=False).drop_duplicates("corp_name")
        if a.refetch_corrections:
            for x in df[df.title.str.contains("정정", na=False)].acptno:
                for suf in ("_s.html", "_b.html"):
                    fp = os.path.join(KDIR, f"{x}{suf}")
                    if os.path.exists(fp):
                        os.remove(fp)
        acs = list(df.acptno)
        print("fetch", len(acs), flush=True)
        n = 0
        with ThreadPoolExecutor(a.workers) as ex:
            for f in as_completed([ex.submit(fetch_one, x) for x in acs]):
                n += 1
                acpt, st = f.result()
                if st not in ("ok", "cached") or n % 100 == 0:
                    print(n, acpt, st, flush=True)
        print("done")


if __name__ == "__main__":
    main()
