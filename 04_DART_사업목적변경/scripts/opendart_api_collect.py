# -*- coding: utf-8 -*-
"""
OpenDART API 버전 수집기 (환경변수 DART_API_KEY 필요)

1) list.json (공시검색): 기간 내 '주주총회소집공고'(pblntf_ty=E 기타공시) / '주주총회소집결의'(I 거래소공시) /
   '정관변경' 등 보고서명 필터 -> 접수번호 목록
2) document.xml (공시서류원본파일, ZIP) 다운로드 -> 내부 XML 에서 '정관의 변경' 섹션의 변경전/변경후/변경목적 표 파싱
3) parse_purposes.py 의 동일 로직(사업목적 행 탐지, 추가 항목 diff, 테마 분류) 재사용

키 발급: https://opendart.fss.or.kr -> 인증키 신청/관리 -> 인증키 신청 (개인 이메일 인증, 무료, 일 20,000건 한도)
사용:
  set DART_API_KEY=발급키            (PowerShell: $env:DART_API_KEY="발급키")
  python opendart_api_collect.py --start 20260101 --end 20260331 --tag api_2026H1reg
  python opendart_api_collect.py --start 20250101 --end 20250331 --tag api_2025H1reg
출력: data/api_<tag>_list.csv, data/api_<tag>_purposes.csv, data/api_<tag>_added_items.csv
"""
import argparse, io, os, re, sys, time, zipfile
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_purposes as P  # noqa: E402

API = "https://opendart.fss.or.kr/api"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
XML_DIR = os.path.join(DATA, "api_xml")
os.makedirs(XML_DIR, exist_ok=True)
SLEEP = 0.15
REPORT_PATTERNS = ("주주총회소집공고", "주주총회소집결의", "정관변경")


def key():
    k = os.environ.get("DART_API_KEY")
    if not k:
        sys.exit("환경변수 DART_API_KEY 가 없습니다. opendart.fss.or.kr 에서 인증키 발급 후 설정하세요.")
    return k


def get(url, **params):
    for i in range(4):
        try:
            r = requests.get(url, params=params, timeout=60, verify=False)
            if r.status_code == 200:
                return r
        except Exception:
            pass
        time.sleep(2 + 3 * i)
    raise RuntimeError(url)


def list_filings(start, end, pblntf_ty):
    """list.json 은 조회기간 최대 3개월(회사 미지정 시) -> 월 단위로 끊어서 조회"""
    rows = []
    dates = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="MS").tolist()
    if not dates or dates[0] > pd.to_datetime(start):
        dates = [pd.to_datetime(start)] + dates
    bounds = dates + [pd.to_datetime(end) + pd.Timedelta(days=1)]
    for s, e in zip(bounds[:-1], bounds[1:]):
        bgn, endd = s.strftime("%Y%m%d"), (e - pd.Timedelta(days=1)).strftime("%Y%m%d")
        page = 1
        while True:
            j = get(API + "/list.json", crtfc_key=key(), bgn_de=bgn, end_de=endd, pblntf_ty=pblntf_ty,
                    page_no=page, page_count=100).json()
            if j.get("status") != "000":
                print("list status", j.get("status"), j.get("message")); break
            for it in j["list"]:
                if any(p in it["report_nm"].replace(" ", "") for p in REPORT_PATTERNS):
                    rows.append(it)
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
            time.sleep(SLEEP)
    return pd.DataFrame(rows)


def document_xml(rcp):
    path = os.path.join(XML_DIR, f"{rcp}.xml")
    if os.path.exists(path):
        return open(path, encoding="utf-8", errors="replace").read()
    r = get(API + "/document.xml", crtfc_key=key(), rcept_no=rcp)
    time.sleep(SLEEP)
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        return None
    texts = []
    for n in z.namelist():
        b = z.read(n)
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                texts.append(b.decode(enc)); break
            except UnicodeDecodeError:
                continue
    xml = "\n".join(texts)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return xml


def analyze_xml(xml):
    """DART XML(dart4.xsd)은 TABLE/TR/TD/TE/TU 태그 사용 -> HTML 파서로 동일 처리하도록 태그 치환"""
    h = re.sub(r"<(/?)(TE|TU|TH)(\s|>)", r"<\1td\3", xml)
    h = re.sub(r"<TITLE[^>]*>([^<]*)</TITLE>", r"<P class='section-3'>\1</P>", h)
    sec = P.section_html(h)
    if not sec:
        m = re.search(r"정관", h)
        if not m:
            return dict(has_aoi_change=False, purpose_change=False, n_added=0, added_items="", themes="", reason="")
        sec = h[m.start(): m.start() + 300000]
    rows, sec_txt = P.parse_changes(sec)
    prows = P.purpose_rows(rows)
    items = P.added_items(prows)
    return dict(has_aoi_change=True, purpose_change=bool(prows), n_added=len(items), added_items=" | ".join(items),
                themes=";".join(P.themes_of(" ".join(items))),
                reason=" / ".join(sorted({r[:150] for _, _, r in prows if r}))[:600])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    df = pd.concat([list_filings(a.start, a.end, "E"), list_filings(a.start, a.end, "I")], ignore_index=True)
    df.to_csv(os.path.join(DATA, f"api_{a.tag}_list.csv"), index=False, encoding="utf-8-sig")
    # 소집공고 우선, 회사별 최신 1건
    df["prio"] = df.report_nm.str.contains("소집공고").map({True: 0, False: 1})
    df = df.sort_values(["prio", "rcept_no"], ascending=[True, False]).drop_duplicates("corp_code")
    recs = []
    for i, r in enumerate(df.itertuples(), 1):
        xml = document_xml(r.rcept_no)
        d = analyze_xml(xml) if xml else {}
        d.update(corp_name=r.corp_name, corp_code=r.corp_code, stock_code=r.stock_code, corp_cls=r.corp_cls,
                 rcept_no=r.rcept_no, rcept_dt=r.rcept_dt, report_nm=r.report_nm)
        recs.append(d)
        if i % 100 == 0:
            print(i, len(df), flush=True)
    out = pd.DataFrame(recs)
    out.to_csv(os.path.join(DATA, f"api_{a.tag}_purposes.csv"), index=False, encoding="utf-8-sig")
    rows = []
    for _, r in out[out.get("n_added", 0) > 0].iterrows():
        for it in r.added_items.split(" | "):
            rows.append(dict(corp_name=r.corp_name, rcept_no=r.rcept_no, item=it, themes=";".join(P.themes_of(it))))
    pd.DataFrame(rows).to_csv(os.path.join(DATA, f"api_{a.tag}_added_items.csv"), index=False, encoding="utf-8-sig")
    print("done", len(out))


if __name__ == "__main__":
    main()
