# -*- coding: utf-8 -*-
"""
수집된 DART 주주총회소집공고 HTML 에서 '정관 변경 - 사업목적 추가' 항목을 추출하고 테마 키워드로 분류.

입력: data/list_<tag>.csv, data/html/<rcpNo>_s.html(안건), data/html/<rcpNo>_b.html(목적사항별 기재사항)
출력: data/purposes_<tag>.csv  (회사별 1행: 사업목적 변경 여부, 추가 항목, 테마)
      data/added_items_<tag>.csv (추가 항목 1개 1행)
사용: python parse_purposes.py --tag 2026H1reg
"""
import argparse, os, re, json
import pandas as pd
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HTML_DIR = os.path.join(DATA, "html")

# 테마 사전 (정규식, 대소문자 무시). 순서 = 보고서 표 순서
THEMES = {
    "AI(인공지능)": r"인공\s*지능|(?<![A-Za-z])A\.?I(?![A-Za-z])|에이아이|머신\s*러닝|딥\s*러닝|생성형|LLM|거대\s*언어",
    "로봇": r"로봇|로보틱스|휴머노이드|액추에이터",
    "데이터센터": r"데이터\s*센터|(?<![A-Za-z])IDC(?![A-Za-z])|DATA\s*CENTER|AIDC",
    "클라우드·SW·빅데이터": r"클라우드|소프트웨어|빅\s*데이터|데이터\s*(?:처리|분석|가공|거래|서비스|베이스)|플랫폼|SaaS",
    "반도체": r"반도체|웨이퍼|팹리스|HBM",
    "원전·원자력": r"원자력|원전|원자로|(?<![A-Za-z])SMR(?![A-Za-z])|핵연료|핵융합",
    "방산": r"방위\s*산업|방산|군수|군용|군납|국방|탄약|총포|유도\s*무기|미사일|무기\s*체계|(?<![사유ㆍ·/\s])무기(?!\s*(?:화학|물|재료|질|소재|안료))",
    "우주항공": r"우주|위성|발사체|로켓|항공(?!\s*유|\s*화물|\s*운송|권)",
    "드론·UAM": r"드론|무인\s*(?:비행|항공)|UAM|도심\s*항공",
    "디지털자산·블록체인·STO(스테이블코인)": r"스테이블\s*코인|가상\s*자산|디지털\s*자산|암호\s*화?\s*(?:폐|자산)|블록\s*체인|토큰\s*증권|증권형\s*토큰|(?<![A-Za-z])STO(?![A-Za-z])|NFT|가상\s*화폐|코인|분산\s*원장|토큰\s*발행",
    "전자지급·결제(PG·선불)": r"전자\s*지급|선불\s*(?:전자)?\s*지급|직불\s*전자|지급\s*결제|결제\s*대행|전자\s*금융",
    "바이오·헬스케어": r"바이오(?!\s*(?:연료|디젤|중유|선박유|항공유|플라스틱|가스|매스))|의약품|의료\s*기기|신약|세포|유전자|(?<!안전)(?<!안전 )(?<!에너지)(?<!에너지 )진단|헬스\s*케어|건강\s*기능\s*식품|의료|병원|줄기|mRNA|펩타이드|(?<![A-Za-z])(?:CDMO|CRO)(?![A-Za-z])|정형\s*외과|재활|요양|방사성\s*의약",
    "반려동물(펫)": r"반려\s*동물|애완|(?<![A-Za-z가-힣])펫(?!트)",
    "2차전지·배터리": r"[2이]\s*차\s*전지|배터리|양극재|음극재|전해질|전해액|리튬|분리막|에너지\s*저장|ESS",
    "신재생·에너지·전력": r"태양광|태양\s*에너지|풍력|수소|신\s*재생|재생\s*에너지|연료\s*전지|발전\s*(?:사업|업|소)|전력|송배전|변압기|전기\s*(?:차\s*)?충전|집단\s*에너지|바이오\s*(?:연료|디젤|중유)",
    "희토류·핵심광물·소재": r"희토류|영구\s*자석|핵심\s*광물|광물|광산|니켈|코발트|흑연|초전도",
    "모빌리티·전기차·자율주행": r"전기\s*자동차|전기차|자율\s*주행|모빌리티|자동차\s*부품|전장\s*부품|라이다",
    "양자": r"양자",
    "조선·해양": r"선박|조선|해양|해운|해저",
    "부동산·임대·건설": r"부동산|건설|건축|주택|분양|시설물\s*(?:임대|관리)",
    "엔터·콘텐츠·게임": r"엔터테인먼트|콘텐츠|컨텐츠|게임|공연|음반|영화|방송|웹툰|매니지먼트|아티스트",
    "화장품·뷰티": r"화장품|뷰티|미용",
    "식품·농업·외식": r"식품|농업|축산|수산(?!\s*물\s*가공\s*기계)|음료|외식|음식점|베이커리|카페",
    "투자·금융": r"투자\s*업|신기술\s*사업\s*(?:금융|투자)|창업\s*투자|대부|자산\s*운용|금융\s*(?:투자|상품)|투자\s*조합",
    "탄소·환경": r"탄소|배출권|폐기물|재활용|환경",
    "교육": r"교육|학원",
}
THEME_RE = {k: re.compile(v, re.I) for k, v in THEMES.items()}

PURPOSE_HINT = re.compile(r"사업\s*목적|목적\s*사업|사업목적|신규\s*사업|신사업|사업\s*다각화|사업\s*영역|목적\s*추가|사업\s*추가|추가\s*사업")
ARTICLE_PURPOSE = re.compile(r"제\s*[2-3]\s*조\s*[\]\)】]?\s*[\(\[【]?\s*(?:목\s*적|사업\s*목적)|[\(\[【]\s*목\s*적\s*[\)\]】]|^\s*목\s*적\s*$|제\s*2\s*조")
ITEM_SPLIT = re.compile(r"(?:^|\n|\s)(\d{1,3}(?:\s*[~\-]\s*\d{1,3})?\s*[\.\)]|\(\d{1,3}\)|[①-⑳㉑-㉟])\s*")
PAREN_NOISE = re.compile(r"[\(\[<][^()\[\]<>]*(?:동일|생략|같음|현행|기존|좌동)[^()\[\]<>]*[\)\]>]")
NOISE = re.compile(r"동\s*일|기존과|상기\s*(?:와|각호와?)?\s*관련|관련한\s*사업\s*일체|사업\s*일체|현행과\s*같음|좌\s*동|생\s*략|이하\s*생략|중\s*략|신\s*설|삭\s*제|^\s*[-~]\s*$|각\s*호에?\s*(?:관련|부대)|부대\s*(?:사업|되는)|관련\s*된?\s*부대|부수되는|각\s*호의?\s*사업", re.I)


def norm(s):
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"[·ㆍ\.,，、/\-\(\)\[\]<>『』「」\"'※*]", "", s)
    return s


def split_items(text):
    """'1. xxx 2. yyy' 형태 -> 항목 리스트"""
    if not text:
        return []
    t = PAREN_NOISE.sub(" ", text.replace("\r", "\n"))
    parts = ITEM_SPLIT.split("\n" + t)
    items = []
    # split 결과: [prefix, num, body, num, body ...]
    for i in range(1, len(parts) - 1, 2):
        body = re.sub(r"\s+", " ", parts[i + 1]).strip(" ;,.")
        if body:
            items.append(body)
    if not items:
        items = [x.strip() for x in re.split(r"\n+", t) if x.strip()]
    return items


def cell_text(td):
    return td.get_text("\n", strip=True)


def section_html(html, title_key="정관"):
    """'□ 정관의 변경' 섹션 HTML 조각만 잘라내기"""
    m = re.search(r"<P[^>]*class=['\"]section-3['\"][^>]*>[^<]*□[^<]*정관[^<]*</P>", html, re.I)
    if not m:
        m = re.search(r"□\s*정관", html)
        if not m:
            return None
    start = m.start()
    nxt = re.search(r"<P[^>]*class=['\"]section-3['\"][^>]*>[^<]*□", html[m.end():], re.I)
    end = m.end() + nxt.start() if nxt else min(len(html), m.end() + 400000)
    return html[start:end]


def parse_changes(sec_html):
    """정관 변경 대비표 행 -> [(before, after, reason)]"""
    soup = BeautifulSoup(sec_html, "html.parser")
    rows = []
    idx = (0, 1, 2)  # (변경전, 변경후, 목적) 열 위치 - 헤더로 결정, 연속 표에 승계
    ncol = 3
    for tb in soup.find_all("table"):
        trs = tb.find_all("tr")
        if not trs:
            continue
        hcells = [norm(c.get_text(" ", strip=True)) for c in trs[0].find_all(["td", "th"])]
        head = "".join(hcells)
        if "변경전" not in head and "현행" not in head and "개정전" not in head:
            # 헤더가 없는 연속 표(페이지 나눔)는 직전 표와 열 수가 같으면 허용
            if not rows or len(hcells) != ncol:
                continue
            body = trs
        else:
            def find(keys, default):
                for i, c in enumerate(hcells):
                    if any(k in c for k in keys):
                        return i
                return default
            ib = find(("변경전", "현행", "개정전"), 0)
            ia = find(("변경후", "개정후", "개정안", "변경안"), ib + 1)
            ir = find(("목적", "사유", "비고"), ia + 1)
            idx, ncol = (ib, ia, ir), len(hcells)
            body = trs[1:]
        for tr in body:
            tds = tr.find_all(["td", "th"])
            if len(tds) == ncol:
                g = lambda i: cell_text(tds[i]) if i < len(tds) else ""
                rows.append((g(idx[0]), g(idx[1]), g(idx[2])))
            elif len(tds) >= 3:
                rows.append((cell_text(tds[-3]), cell_text(tds[-2]), cell_text(tds[-1])))
            elif len(tds) == 2:
                rows.append((cell_text(tds[0]), cell_text(tds[1]), ""))
    return rows, soup.get_text("\n", strip=True)


STRONG_HINT = re.compile(r"사업\s*목적|목적\s*사업|사업\s*추가|목적\s*추가|목적\s*변경|신규\s*사업\s*(?:추가|진출)|신사업")


def purpose_rows(rows):
    """정관 제2조(목적) 조문 행 또는 '변경의 목적'에 사업목적 관련 문구가 있는 행"""
    out = []
    for b, a, r in rows:
        head = (b[:80] + " " + a[:80])
        is_article = bool(re.search(r"제\s*[1-3]\s*조\s*(?:의\s*\d\s*)?[\]\)】]?\s*[\(\[【]?\s*(?:목\s*적|사업\s*목적|목적\s*및\s*사업|사업)", head))             or bool(re.search(r"[\(\[【]\s*목\s*적\s*[\)\]】]", head))
        is_reason = bool(STRONG_HINT.search(r)) and not re.search(r"상호|명칭|사외이사|독립이사|주식|사채|배당|이사회|감사", r[:40])
        if is_article or is_reason:
            out.append((b, a, r))
    return out


def added_items(prows):
    before_all, after_all = [], []
    for b, a, r in prows:
        before_all += split_items(b)
        after_all += split_items(a)
    bset = {norm(x) for x in before_all}
    added = []
    for x in after_all:
        nx = norm(x)
        if not nx or len(nx) < 3 or nx in bset:
            continue
        if NOISE.search(x) and len(nx) < 25:
            continue
        if re.search(r"제\s*\d+\s*조|목\s*적\s*\]|회사는\s*다음의?\s*사업을|목적으로\s*한다", x):
            # 조문 머리말 제거 (예: '제2조(목적) 회사는 다음 사업을 영위함을 목적으로 한다')
            x2 = re.sub(r".*목적으로\s*한다\.?", "", x).strip()
            if len(norm(x2)) < 3:
                continue
            x = x2
        x = re.sub(r"^\s*[~\-]?\s*\d{1,3}\s*[\.\)]?\s*", "", x)
        x = re.split(r"부\s*칙|\[\s*삭\s*제|<\s*삭\s*제", x)[0].strip()
        x = re.sub(r"^\s*[\(\[<]\s*(?:추\s*가|신\s*설|신\s*규)\s*[\)\]>]\s*", "", x)
        x = re.sub(r"^\s*-\s*", "", x)
        if re.search(r"(?:현\s*행|기\s*존|변경\s*없음)\s*$", x):
            continue
        if re.match(r"^(?:위|상기|전)?\s*(?:각\s*(?:호|항|목)|제\s*\d+\s*호)", x):
            continue
        if re.fullmatch(r"[\s~\-\d\.]*", x):
            continue
        x = re.sub(r"\s*[\(<\[]\s*(?:추\s*가|신\s*설|개\s*정)[^\)>\]]{0,20}[\)>\]]\s*$", "", x).strip()
        if len(norm(x)) < 3 or (NOISE.search(x) and len(norm(x)) < 25):
            continue
        added.append(x[:200])
    # 중복 제거(순서 유지)
    seen, res = set(), []
    for x in added:
        k = norm(x)
        if k not in seen:
            seen.add(k); res.append(x)
    return res


def themes_of(text):
    return [k for k, rx in THEME_RE.items() if rx.search(text or "")]


def read(path):
    if not os.path.exists(path):
        return None
    return open(path, encoding="utf-8", errors="replace").read()


def analyze(rcp, d=None):
    d = d or HTML_DIR
    s_html = read(os.path.join(d, f"{rcp}_s.html")) or ""
    b_html = read(os.path.join(d, f"{rcp}_b.html"))
    s_txt = BeautifulSoup(s_html, "html.parser").get_text(" ", strip=True) if s_html else ""
    agenda_flag = bool(PURPOSE_HINT.search(s_txt))
    agenda_snip = ""
    m = PURPOSE_HINT.search(s_txt)
    if m:
        agenda_snip = s_txt[max(0, m.start() - 60): m.end() + 120]
    res = dict(rcept_no=rcp, has_small=bool(s_html), has_big=bool(b_html), agenda_flag=agenda_flag,
               agenda_snip=agenda_snip, has_aoi_change=None, purpose_change=False, n_added=0,
               added_items="", reason="", themes="")
    if b_html:
        sec = section_html(b_html)
        res["has_aoi_change"] = bool(sec)
        if sec:
            rows, sec_txt = parse_changes(sec)
            prows = purpose_rows(rows)
            items = added_items(prows)
            reason = " / ".join(sorted({re.sub(r"\s+", " ", r)[:150] for _, _, r in prows if r}))
            res.update(purpose_change=bool(prows),
                       n_added=len(items), added_items=" | ".join(items), reason=reason[:600],
                       themes=";".join(themes_of(" ".join(items))))
            # 표에서 항목을 못 찾았지만 목적 관련 문구가 있는 경우 표시
            if not prows and PURPOSE_HINT.search(sec_txt):
                mm = PURPOSE_HINT.search(sec_txt)
                res["reason"] = "(텍스트) " + sec_txt[max(0, mm.start() - 80): mm.end() + 200].replace("\n", " ")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--source", choices=["dart", "kind"], default="kind",
                    help="kind: data/kind_list_<tag>.csv + data/kind/ (기본) / dart: data/list_<tag>.csv + data/html/")
    a = ap.parse_args()
    recs = []
    if a.source == "dart":
        lst = pd.read_csv(os.path.join(DATA, f"list_{a.tag}.csv"), dtype=str)
        lst = lst.sort_values("rcept_no", ascending=False).drop_duplicates("corp_code")
        for _, r in lst.iterrows():
            if not os.path.exists(os.path.join(HTML_DIR, f"{r.rcept_no}_s.html")):
                continue
            d = analyze(r.rcept_no)
            d.update(corp_code=r.corp_code, corp_name=r.corp_name, rcept_dt=r.rcept_dt, market=r.market,
                     report_nm=r.report_nm, source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r.rcept_no}")
            recs.append(d)
    else:
        kd = os.path.join(DATA, "kind")
        lst = pd.read_csv(os.path.join(DATA, f"kind_list_{a.tag}.csv"), dtype=str)
        lst = lst.sort_values("acptno", ascending=False).drop_duplicates("corp_name")
        for _, r in lst.iterrows():
            sp = os.path.join(kd, f"{r.acptno}_s.html")
            if not os.path.exists(sp):
                continue
            d = analyze(r.acptno, kd)
            m = re.search(r"url=(\S+)", open(sp, encoding="utf-8", errors="replace").read(400))
            d.update(corp_code="", corp_name=r.corp_name, rcept_dt=str(r["dt"])[:10].replace("-", ""), market=r["market"],
                     report_nm=r["title"], source_url=m.group(1) if m else "")
            recs.append(d)
    df = pd.DataFrame(recs)
    cols = ["corp_name", "corp_code", "market", "rcept_dt", "rcept_no", "report_nm", "agenda_flag", "has_big",
            "has_aoi_change", "purpose_change", "n_added", "themes", "added_items", "reason", "agenda_snip", "source_url", "has_small"]
    df = df[[c for c in cols if c in df.columns]]
    out = os.path.join(DATA, f"purposes_{a.tag}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    # 항목 단위
    rows = []
    for _, r in df[df.n_added > 0].iterrows():
        for it in r.added_items.split(" | "):
            rows.append(dict(corp_name=r.corp_name, rcept_no=r.rcept_no, rcept_dt=r.rcept_dt, market=r.market,
                             item=it, themes=";".join(themes_of(it))))
    pd.DataFrame(rows).to_csv(os.path.join(DATA, f"added_items_{a.tag}.csv"), index=False, encoding="utf-8-sig")
    print(out, len(df), "agenda_flag", int(df.agenda_flag.sum()), "purpose_change", int(df.purpose_change.sum()),
          "with_items", int((df.n_added > 0).sum()))


if __name__ == "__main__":
    main()
