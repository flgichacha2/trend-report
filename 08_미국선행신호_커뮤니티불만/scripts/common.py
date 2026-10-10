# -*- coding: utf-8 -*-
"""[8] 미국 선행 신호 + 불만 글: 공통 모듈 (수집 함수 + 키워드 분류 규칙)

수집원(모두 키 없는 공개 경로)
- YC: ycombinator.com/companies 페이지에 박힌 Algolia 공개 검색키(AlgoliaOpts, 기한 있음)를 매번 페이지에서 읽어 사용
- Product Hunt: https://www.producthunt.com/feed (+ ?category=<slug>) Atom 피드, 피드당 50개
- GitHub Trending: https://github.com/trending?since=daily|weekly|monthly HTML
- Hacker News: https://hn.algolia.com/api/v1/search(_by_date)
- Reddit: /r/<sub>/new/.rss, /top/.rss?t=month (JSON(new.json)은 403 차단이라 RSS 사용, 429가 잦아 7초 간격)
선택 키: GITHUB_TOKEN(없어도 됨, 저장소 topics 조회 한도만 늘어남)
"""
import datetime as dt, html, json, os, re, sys, time
from pathlib import Path as _P
from urllib.parse import unquote as _unq

try:
    from dotenv import dotenv_values as _dv
    for _k, _v in _dv(_P(__file__).resolve().parents[2] / ".env").items():
        if _v and not os.environ.get(_k):
            os.environ[_k] = _unq(_v) if _k.endswith("_KEY") else _v
except Exception:
    pass
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/129.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
S = requests.Session()
S.headers.update(UA)
_last = [0.0]


def get(url, sleep=1.5, tries=3, **kw):
    """순차 요청 + 간격(sleep초) + 429/5xx 재시도"""
    for i in range(tries):
        wait = sleep - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = S.get(url, timeout=40, **kw)
        except requests.RequestException:
            _last[0] = time.time()
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1)); continue
        _last[0] = time.time()
        if r.status_code == 429 or r.status_code >= 500:
            if i == tries - 1:
                r.raise_for_status()
            time.sleep(int(r.headers.get("retry-after", 0) or 0) or 20 * (i + 1)); continue
        r.raise_for_status()
        return r


# ---------------------------------------------------------------- YC
YC_BATCHES = ["Winter 2024", "Summer 2024", "Fall 2024", "Winter 2025", "Spring 2025", "Summer 2025", "Fall 2025",
              "Winter 2026", "Spring 2026", "Summer 2026", "Fall 2026"]
YC_FIELDS = ["name", "slug", "batch", "industry", "subindustry", "industries", "tags", "one_liner", "team_size",
             "status", "regions", "all_locations", "website", "launched_at"]


def yc_opts():
    h = get("https://www.ycombinator.com/companies").text
    return json.loads(re.search(r"AlgoliaOpts = (\{.*?\});", h).group(1))


def yc_query(o, params):
    url = f"https://{o['app'].lower()}-dsn.algolia.net/1/indexes/*/queries"
    hd = {"x-algolia-application-id": o["app"], "x-algolia-api-key": o["key"], **UA}
    time.sleep(1.2)
    r = S.post(url, headers=hd, json={"requests": [{"indexName": "YCCompany_production", "params": params}]}, timeout=40)
    r.raise_for_status()
    return r.json()["results"][0]


def yc_facets(o):
    from urllib.parse import quote
    res = yc_query(o, "hitsPerPage=0&maxValuesPerFacet=1000&facets=" + quote(json.dumps(["batch"])))
    return res["facets"]["batch"], res["nbHits"]


def yc_batch(o, batch):
    from urllib.parse import quote
    out, page = [], 0
    while True:
        res = yc_query(o, f"hitsPerPage=1000&page={page}&facetFilters=" + quote(json.dumps([[f"batch:{batch}"]])))
        for h in res["hits"]:
            out.append({k: h.get(k) for k in YC_FIELDS})
        page += 1
        if page >= res.get("nbPages", 1):
            return out


# ---------------------------------------------------------------- Product Hunt
PH_CATS = ["", "productivity", "artificial-intelligence", "developer-tools", "chrome-extensions", "marketing",
           "design-tools", "sales", "finance"]


def ph_feed(cat=""):
    url = "https://www.producthunt.com/feed" + (f"?category={cat}" if cat else "")
    x = get(url).text
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        pid = re.search(r"Post/(\d+)</id>", e)
        tag = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        tagline = ""
        if tag:
            t = html.unescape(tag.group(1))
            m = re.search(r"<p>\s*(.*?)\s*</p>", t, re.S)
            tagline = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
        out.append({"id": pid.group(1) if pid else "", "title": html.unescape(re.search(r"<title>(.*?)</title>", e, re.S).group(1)),
                    "tagline": tagline, "url": re.search(r'href="([^"]+)"', e).group(1),
                    "published": re.search(r"<published>(.*?)</published>", e).group(1), "ph_cat": cat or "all"})
    return out


# ---------------------------------------------------------------- GitHub Trending
def gh_trending(since="daily"):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(get(f"https://github.com/trending?since={since}").text, "html.parser")
    out = []
    for i, a in enumerate(soup.select("article.Box-row")):
        link = a.select_one("h2 a")
        repo = link["href"].strip("/")
        desc = a.select_one("p")
        lang = a.select_one('[itemprop="programmingLanguage"]')
        stars = a.select_one('a[href$="/stargazers"]')
        gain = re.search(r"([\d,]+) stars? (today|this week|this month)", a.get_text(" "))
        out.append({"rank": i + 1, "repo": repo, "desc": desc.get_text(" ", strip=True) if desc else "",
                    "lang": lang.get_text(strip=True) if lang else "",
                    "stars": int(stars.get_text(strip=True).replace(",", "")) if stars else None,
                    "gain": int(gain.group(1).replace(",", "")) if gain else None, "since": since})
    return out


def gh_topics(repo):
    hd = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        hd["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    r = S.get(f"https://api.github.com/repos/{repo}", headers=hd, timeout=30)
    time.sleep(1)
    if r.status_code != 200:
        return None
    j = r.json()
    return {"topics": j.get("topics", []), "created_at": j.get("created_at", "")[:10]}


# ---------------------------------------------------------------- Hacker News
def hn(tags, since_ts, until_ts=None, query="", by_date=True, extra=""):
    nf = f"created_at_i>{int(since_ts)}" + (f",created_at_i<={int(until_ts)}" if until_ts else "") + extra
    ep = "search_by_date" if by_date else "search"
    j = get(f"https://hn.algolia.com/api/v1/{ep}", sleep=1.0,
            params={"tags": tags, "numericFilters": nf, "hitsPerPage": 1000, "query": query}).json()
    return [{"id": h["objectID"], "title": h.get("title") or "", "text": re.sub(r"<[^>]+>", " ", html.unescape(h.get("story_text") or ""))[:1500],
             "points": h.get("points") or 0, "comments": h.get("num_comments") or 0,
             "created": h.get("created_at", "")[:10], "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
             "tags": tags} for h in j.get("hits", [])], j.get("nbHits", 0)


# ---------------------------------------------------------------- Reddit (RSS)
SUBS = ["SaaS", "Entrepreneur", "productivity", "chrome_extensions", "excel", "smallbusiness", "automation", "nocode"]


def reddit_rss(sub, kind="new", tries=3, sleep=7):
    url = f"https://www.reddit.com/r/{sub}/{kind}/.rss?limit=100" + ("&t=month" if kind == "top" else "")
    x = get(url, sleep=sleep, tries=tries).text
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        c = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        body = re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(c.group(1)))) if c else ""
        body = re.sub(r"submitted by .*", "", re.sub(r"\s+", " ", body)).strip()
        pid = re.search(r"<id>t3_(\w+)</id>", e)
        if not pid:
            continue
        out.append({"id": pid.group(1), "sub": sub, "title": html.unescape(re.search(r"<title>(.*?)</title>", e, re.S).group(1)),
                    "text": body[:1500], "created": (re.search(r"<published>(.*?)</published>", e) or
                                                     re.search(r"<updated>(.*?)</updated>", e)).group(1)[:10],
                    "url": re.search(r'<link href="([^"]+)"', e).group(1), "kind": kind})
    return out


# ---------------------------------------------------------------- 분류 규칙
# 분야(카테고리) 키워드: 한 항목이 여러 분야에 속할 수 있음. \b 단어 경계, 대소문자 무시.
CATS = {
    "AI 에이전트": r"\bagent(s|ic)?\b|autonomous|ai (employee|worker|teammate|coworker)|digital worker",
    "MCP·LLM 인프라": r"\bmcp\b|model context protocol|\bllms?\b|inference|\bevals?\b|\brag\b|vector|fine-?tun|prompt|context engineering|guardrail|observability for ai",
    "개발도구·코딩": r"\bcod(e|ing)\b|developer|\bdevs?\b|\bide\b|debug|\btest(s|ing)?\b|\bqa\b|\bapis?\b|sdk|devops|deploy|github|terminal|\bcli\b|software engineer",
    "음성·전화": r"\bvoice\b|phone|calls?\b|speech|\btts\b|transcri|call center|receptionist",
    "영업·마케팅": r"\bsales\b|\bleads?\b|outreach|marketing|\bseo\b|\bgeo\b|\bads?\b|advertis|\bcrm\b|go-to-market|\bgtm\b|prospect|cold email|ai search|answer engine",
    "고객지원": r"customer (support|service|success)|helpdesk|help desk|support tickets?|\bticket",
    "재무·회계": r"accounting|bookkeep|invoice|\bfinanc|payments?\b|\btax\b|\bcfo\b|expense|payroll|treasury|billing|\bbank",
    "법무·컴플라이언스": r"compliance|\blegal\b|lawyer|law firm|contract|regulat|\baudit|soc ?2|\bkyc\b|\baml\b|\brisk\b|policy|governance",
    "보안": r"secur|cyber|fraud|identity|vulnerab|threat|pentest|malware|phishing|zero trust",
    "헬스케어": r"health|medical|clinic|patient|doctor|hospital|pharma|biotech|drug|therap|dental|care\b",
    "채용·HR": r"recruit|hiring|\bhr\b|talent|candidate|interview|employee|workforce|staffing",
    "문서·생산성": r"meeting|notes?\b|\bemail|inbox|calendar|\bdocs?\b|document|spreadsheet|excel|productiv|workflow|task|knowledge|\bpdf\b|slides|presentation",
    "브라우저·확장": r"browser|extension|chrome|\btabs?\b|bookmark|web agent|computer use",
    "데이터·분석": r"\bdata\b|analytics|dashboard|\bbi\b|\bsql\b|database|warehouse|etl|insight",
    "로봇·하드웨어": r"robot|hardware|drone|manufactur|factory|semiconductor|\bchip|sensor|satellite|defense|aerospace",
    "교육": r"educat|learn|student|tutor|teacher|course|school",
    "커머스·리테일": r"e-?commerce|shopify|retail|store\b|merchant|amazon|inventory|restaurant",
    "부동산·건설": r"real estate|property|construction|mortgage|housing|landlord|rental|contractor",
    "보험": r"insur",
    "콘텐츠·디자인·영상": r"\bvideo|image|design|creator|content|\bmusic|podcast|youtube|tiktok|instagram|social media|ugc|avatar",
    "물류·공급망": r"logistic|supply chain|freight|shipping|warehouse|procure|trucking",
}
CATS_RE = {k: re.compile(v, re.I) for k, v in CATS.items()}

# 요청·불만 글 판별(제목+본문 앞부분)
REQ = re.compile(r"is there (a|an|any)\b|are there any (good )?(tools?|apps?|extensions?|services?|alternatives?)|looking for (a|an)?\s*(tool|app|extension|service|software|way|solution|plugin)"
                 r"|alternative(s)? (to|for)\b|i wish (there|someone)|how do you (manage|handle|organi[sz]e|track|keep|deal with|automate|store|find|avoid)\b"
                 r"|any (tool|app|extension|software)s?\b|need (a|an) (tool|app|extension|way)|what (tools?|apps?|software|extensions?) do you use"
                 r"|frustrat|annoying|tired of|sick of|waste (so much|hours|time)|\bmanually\b|copy.?(and.?)?past(e|ing)|repetitive", re.I)

# 불만·요청 유형 (여러 개 가능)
PAIN = {
    "도구 찾기": r"is there (a|an|any)|are there any|looking for|any (tool|app|extension|software)|recommend|what (tool|app|software|do you use)|need (a|an) (tool|app)",
    "대안 찾기": r"alternative|replacement for|instead of|switch(ing)? from|cheaper than|open.?source (version|alternative)",
    "반복 수작업": r"manual(ly)?|copy.?(and.?)?paste|repetitive|tedious|every (day|week|month)|by hand|automat|spend(ing)? hours|time.?consuming",
    "가격·구독 부담": r"expensive|pric(e|ing|ey)|subscription|cost(s|ly)?\b|too much money|afford|free (tier|version|alternative)",
    "정보 과부하·정리": r"too many|overwhelm|organi[sz]|clutter|bookmarks?|\btabs\b|scattered|keep track|lose track|messy|find (it|things) later",
    "연동·내보내기": r"integrat|\bsync|export|import|\bapi\b|connect (to|with)|zapier|webhook|csv",
    "품질·버그 불만": r"broken|bug(gy|s)?\b|slow|crash|doesn.?t work|stopped working|frustrat|annoy|hate|terrible|worse",
    "집중·시간관리": r"focus|distract|procrastinat|time.?track|habit|adhd|pomodoro|schedul",
    "고객·매출 확보": r"first (customer|user|sale)|get(ting)? (customers|users|clients)|\bleads?\b|marketing|churn|growth|mrr|revenue",
    "개인정보·보안": r"privacy|tracking|track(s|ed) me|data (leak|sell)|secure|security|permission",
}
PAIN_RE = {k: re.compile(v, re.I) for k, v in PAIN.items()}

# 불만의 '대상'(무엇에 대한 글인가) → 크롬확장/자동화 아이디어 연결용
OBJ = {
    "이메일·받은편지함": r"\bemails?\b|inbox|gmail|outlook|newsletter",
    "엑셀·스프레드시트": r"\bexcel\b|spreadsheet|google sheets|\bsheets?\b|vlookup|xlookup|pivot|formula|vba|power query",
    "탭·북마크·브라우저": r"\btabs?\b|bookmark|browser|chrome|extension",
    "회의·노트": r"meeting|notes?\b|transcri|notion|obsidian|minutes",
    "SNS·콘텐츠 발행": r"linkedin|twitter|\bx\.com|instagram|tiktok|youtube|social media|reddit|post(s|ing)? schedul",
    "인보이스·결제·회계": r"invoice|billing|stripe|quickbooks|bookkeep|receipt|expense|payment",
    "CRM·리드·영업": r"\bcrm\b|\bleads?\b|hubspot|salesforce|prospect|outreach|cold (email|outreach)",
    "PDF·문서": r"\bpdf\b|docx|document|contract|form(s)?\b",
    "고객지원·리뷰": r"support ticket|customer support|reviews?\b|helpdesk|chatbot",
    "일정·예약": r"calendar|schedul|booking|appointment",
    "웹 스크래핑·데이터 수집": r"scrap(e|ing)|crawl|extract data|data from (websites?|web)|monitor (prices?|website)",
    "AI 사용(ChatGPT·Claude 등)": r"chatgpt|\bgpt\b|claude|gemini|\bllm|prompt|\bai\b",
    "구직·채용": r"job search|\bresumes?\b|\bcv\b|job applications?|hiring|recruit",
    "비밀번호·보안·개인정보": r"password|privacy|2fa|security",
}
OBJ_RE = {k: re.compile(v, re.I) for k, v in OBJ.items()}


def tag(text, table):
    return [k for k, rx in table.items() if rx.search(text or "")]


def j(x):
    return json.dumps(x, ensure_ascii=False)
