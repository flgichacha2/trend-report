# -*- coding: utf-8 -*-
"""
[10] 정부 장바구니(나라장터 사전규격) 공통 모듈: 수집 함수 + 분류 규칙

수집 경로 (2026-10-10 확인)
 1) 공공데이터포털 '조달청_나라장터 사전규격정보서비스'(apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService)
    -> 루트 .env MOLIT_API_KEY 로 시도했으나 403 SERVICE_KEY_IS_NOT_REGISTERED(활용신청 안 됨). try_open_api() 참고.
 2) 키 없는 공개 경로(현재 사용): 나라장터(www.g2b.go.kr) 화면 '발주 > 발주목록 > 사전규격공개' 검색이 부르는 JSON
    POST https://www.g2b.go.kr/pr/prc/prca/OderReq/selectOderReqList.do  (srchTy=0002 = 사전규격공개)
    로그인 불필요. 메인 페이지 방문으로 세션 쿠키만 받은 뒤 조회. 한 번에 최대 1,000건.
"""
import html, json, os, re, sys, time
from pathlib import Path
from urllib.parse import unquote

try:
    import truststore; truststore.inject_into_ssl()   # 사내망 SSL
except Exception:
    pass
import requests
from dotenv import dotenv_values

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
RAW = BASE / "data" / "raw"
PROC = BASE / "data" / "processed"
SNAPROOT = BASE / "data" / "snapshots"
SLEEP = 1.5

# 루트 .env 로드(환경변수가 우선, Encoding 형식 키는 Decoding)
for _k, _v in dotenv_values(ROOT / ".env").items():
    if _v and not os.environ.get(_k):
        os.environ[_k] = unquote(_v) if _k.endswith("_KEY") else _v

G2B = "https://www.g2b.go.kr"
LIST_URL = G2B + "/pr/prc/prca/OderReq/selectOderReqList.do"
OPEN_API = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc"
OPEN_API_NAME = "조달청_나라장터 사전규격정보서비스"

KEEP = ["id", "date", "biz_type", "domestic", "title", "org", "dept", "amount", "status",
        "bid_linked", "opinion_cnt", "sw"]


def try_open_api():
    """공공데이터포털 사전규격 API 상태 확인(키 값은 절대 출력하지 않음). 반환: 'OK' 또는 오류코드 문자열"""
    key = os.environ.get("MOLIT_API_KEY") or os.environ.get("DATA_GO_KR_KEY")
    if not key:
        return "NO_KEY"
    try:
        r = requests.get(OPEN_API, params=dict(serviceKey=key, pageNo=1, numOfRows=1, type="json", inqryDiv=1,
                                               inqryBgnDt="202610010000", inqryEndDt="202610012359"), timeout=30)
        t = r.text
        m = re.search(r'"errMsg"\s*:\s*"([A-Z_]+)"', t) or re.search(r"<errMsg>([^<]+)", t)
        if r.status_code == 200 and '"resultCode"' in t and '"00"' in t:
            return "OK"
        return m.group(1) if m else f"HTTP_{r.status_code}"
    except Exception as e:
        return type(e).__name__


class G2B_Client:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36",
            "Accept": "application/json", "Content-Type": "application/json;charset=UTF-8",
            "Referer": G2B + "/", "Origin": G2B,
        })
        self._ready = False

    def _init(self):
        self.s.get(G2B + "/", timeout=30)
        time.sleep(SLEEP)
        self.s.post(G2B + "/co/coz/coza/util/getSession.do", json={}, timeout=30)
        time.sleep(SLEEP)
        self.s.headers.update({
            "Menu-Info": json.dumps({"menuNo": "13713", "menuCangVal": "PRCA001_04",
                                     "bsneClsfCd": "%EC%97%85130025", "scrnNo": "00963"}),
            "submissionid": "mf_wfm_container_smSearchOderReqLstList", "Target-Id": "btnS0001", "Usr-Id": "null"})
        self._ready = True

    def page(self, bgn, end, page, n=1000, sw=""):
        if not self._ready:
            self._init()
        today = time.strftime("%Y%m")
        body = {"dlOderReqSrchM": {
            "srchTy": "0002", "srchTyNm": "", "bizNm": "", "tkcgSe": "", "picNm": "", "stepCd": "", "prssCd": "",
            "oderInstUntyGrpNo": "", "oderInstUntyGrpNm": "", "pbancInstUntyGrpNo": "", "pbancInstUntyGrpNm": "",
            "instSearchRangeYn": "", "pbancSearchRangeYn": "", "prgrsBgngYmd": bgn, "prgrsEndYmd": end,
            "currentPage": page, "recordCountPerPage": str(n), "preSrchTy": "", "oderPlanPgstCd": "", "myPrnmYn": "",
            "dtlsPrnmNo": "", "dtlsPrnm": "", "itemClsfNo": "", "itemCfnm": "", "itemIdnfNm": "", "hskCd": "",
            "hskNm": "", "prcmBsneSeCd": "", "ctknSeCd": "", "swBizTrgtYn": sw, "specRlsYn": "", "bfSpecRegNo": "",
            "oderStYm": today, "oderEdYm": today, "lgdngCd": "", "extlPbfnCtrtDmndNo": "", "extlPbfnAsetDmndNoVal": ""}}
        for attempt in range(3):
            try:
                r = self.s.post(LIST_URL, json=body, timeout=90)
                if r.status_code == 403 and attempt < 2:
                    self._init(); continue
                r.raise_for_status()
                d = r.json()
                return d.get("dlOderReqL") or []
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  재시도({type(e).__name__})", flush=True)
                time.sleep(5)
        return []

    def fetch(self, bgn, end, sw="", log=True):
        """기간(YYYYMMDD) 사전규격 전체 목록. 반환: (rows, totCnt)"""
        rows, p, tot = [], 1, None
        while True:
            L = self.page(bgn, end, p, sw=sw)
            time.sleep(SLEEP)
            if not L:
                break
            tot = L[0].get("totCnt", tot)
            rows += L
            if log:
                print(f"  {bgn}~{end}{' SW' if sw else ''} p{p}: {len(rows):,}/{tot:,}", flush=True)
            if len(L) < 1000 or len(rows) >= (tot or 0):
                break
            p += 1
        return rows, (tot or 0)


def norm(r):
    t = html.unescape(html.unescape(r.get("bizNm") or "")).strip()
    return {"id": r.get("oderPlanNo") or r.get("unikey"), "date": r.get("prcsYmd"),
            "biz_type": r.get("prcmBsneSeNm") or "", "domestic": r.get("pbancSeYnNm") or "",
            "title": re.sub(r"\s+", " ", t), "org": html.unescape(r.get("oderInstUntyGrpNm") or "").strip(),
            "dept": html.unescape(r.get("tkcgDeptNm") or "").strip(), "amount": r.get("bgtSumAmt") or 0,
            "status": r.get("oderPlanPgstNm") or "", "bid_linked": r.get("bidPbancRfrnYn") or "",
            "opinion_cnt": r.get("bfSpecOpnnCnt") or 0, "sw": ""}


# ---------------- 분류 규칙 ----------------
# 키워드 분야(사업명 기준, 한 건이 여러 분야에 들어갈 수 있음)
_A = r"(?<![A-Za-z])"; _Z = r"(?![A-Za-z])"
CATS = [
    ("생성형AI·LLM", rf"생성형|{_A}LLM{_Z}|{_A}sLLM{_Z}|거대언어|초거대|언어모델|{_A}GPT|챗봇|챗GPT|에이전트|{_A}RAG{_Z}"),
    ("AI(전체)", rf"{_A}AI{_Z}|{_A}AICC{_Z}|인공지능|머신러닝|딥러닝|생성형|{_A}LLM{_Z}|거대언어|초거대|챗봇|지능형"),
    ("클라우드", rf"클라우드|{_A}SaaS{_Z}|{_A}IaaS{_Z}|{_A}PaaS{_Z}|{_A}cloud{_Z}"),
    ("정보보호·보안", r"정보보호|정보보안|사이버(?!\s?(교육|강의|연수|대학|강좌|학습|교실))|침해|보안관제|보안 관제|취약점|방화벽|제로트러스트|망분리|망연계|안티바이러스|"
                    r"(?<![A-Za-z])(EDR|DLP|SIEM|SOAR|NAC|DDoS|WAF|ISMS|SSL VPN)(?![A-Za-z])|"
                    r"(?<!정)보안(?!등|경|관|용역\s*\(경비|요원|검색|검색대)"),
    ("개인정보", r"개인정보|가명정보|가명처리|비식별"),
    ("데이터", r"데이터|빅데이터|(?<![A-Za-z])DB(?![A-Za-z])|데이터베이스"),
    ("로봇", r"로봇"),
    ("드론", r"드론|무인기|무인비행|(?<![A-Za-z])UAV(?![A-Za-z])"),
    ("디지털트윈", r"디지털\s?트윈"),
    ("스마트기기·PC", r"태블릿|스마트기기|스마트패드|노트북|크롬북|전자칠판|(?<![A-Za-z])PC(?![A-Za-z])(?!\s?(관|파일|암거|맨홀|박스|구조물|빔|거더|블록|조립|옹벽|벽체|판넬|패널))|컴퓨터(?!\s?단층)|데스크톱|데스크탑"),
    ("노후시설·장비 교체", r"노후.{0,20}(교체|개선|정비|보강|개량)|(교체|개선).{0,10}노후"),
    ("CCTV·영상감시", r"(?<![A-Za-z])CCTV(?![A-Za-z])|영상감시|방범카메라|지능형\s?관제"),
    ("정보시스템 구축·고도화", r"정보시스템|시스템\s?(구축|고도화|개발)|플랫폼\s?(구축|고도화)|홈페이지|"
                         r"(?<![A-Za-z])(ISP|ISMP)(?![A-Za-z])|전산|소프트웨어|(?<![A-Za-z])SW(?![A-Za-z])"),
]
CAT_RE = [(n, re.compile(p, re.I)) for n, p in CATS]
FOCUS = ["생성형AI·LLM", "AI(전체)", "클라우드", "정보보호·보안", "개인정보", "데이터", "로봇", "드론",
         "디지털트윈", "스마트기기·PC", "노후시설·장비 교체"]


def cats(title):
    return [n for n, rx in CAT_RE if rx.search(title or "")]


SIDO = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
        "경기도", "강원특별자치도", "강원도", "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도",
        "전남광주통합특별시", "경상북도", "경상남도", "제주특별자치도"]
_EDU = re.compile(r"교육청|교육지원청|초등학교|중학교|고등학교|(?<!대)학교$|유치원|특수학교|교육시설관리")
_CENTRAL = re.compile(r"^(국방|국군|육군|해군|공군|해병|합동참모|방위사업|병무|국가정보|대법원|법원|검찰|경찰|해양경찰|"
                      r"국회|감사원|헌법재판소|중앙선거|관세|국세|조달|통계|기상|산림|특허|문화재|국가유산|질병관리|식품의약|"
                      r"새만금|행정중심|우정|우체국|지방법원|교정|소방청|인사혁신|법제|국가보훈|재외동포|농촌진흥|"
                      r"국립(?!.*대학))|"
                      r"(부|처|청|위원회|본부|지방청|세관|세무서|교도소|구치소)$|부 |처 |청 ")
_PUBLIC = re.compile(r"주식회사|\(주\)|공사|공단|재단|진흥원|연구원|연구소|센터|협회|대학교|대학|병원|의료원|은행|"
                     r"공기업|진흥회|기술원|정보원|평가원|관리원|원$|기금|마사회|적십자|테크노파크|공제회|연구회|"
                     r"국제협력단|상공회의소|중앙회|보증|공사$|발전")
_COMPANY = re.compile(r"\(주\)|주식회사|공사|공단|^한국|테크노파크|대학교")


def org_type(name):
    n = (name or "").strip()
    if not n or "테스트기관" in n:
        return "기타"
    if _EDU.search(n):
        return "교육청·학교"
    if any(n.startswith(s) for s in SIDO) and not re.search(r"대학교|공사$|공단$|재단$", n):
        return "지자체"
    if re.search(r"(시|군|구)$", n.split()[0]) and len(n.split()) >= 1 and not _PUBLIC.search(n):
        return "지자체"
    if _COMPANY.search(n) and not re.match(r"^(국방|국군|육군|해군|공군|해병)", n):
        return "공공기관"
    if (_CENTRAL.search(n) or re.search(r"(실|군수지원단|사령부|사단|여단|비행단|함대|부대)$", n)) and "교육청" not in n:
        return "중앙부처·소속"
    if _PUBLIC.search(n):
        return "공공기관"
    return "기타"


def sido_of(name):
    n = (name or "").strip()
    for s in SIDO:
        if n.startswith(s):
            return s
    return ""


# 관심지역(받는 사람): 제주 영어교육도시(서귀포 대정), 영종도(인천 중구·영종구), 야탑·판교(성남), 강남
WATCH = {"제주(서귀포)": r"제주특별자치도 서귀포|서귀포", "인천 중구·영종": r"인천광역시 (?:중구|영종구)|영종",
         "성남(야탑·판교)": r"경기도 성남|성남시|판교|야탑", "서울 강남구": r"서울특별시 강남구|강남구"}

BANDS = [(0, "미기재(0원)"), (1, "1억 미만"), (1e8, "1~5억"), (5e8, "5~20억"), (2e9, "20~100억"), (1e10, "100억 이상")]


def band(a):
    a = float(a or 0)
    lab = BANDS[0][1]
    for lo, name in BANDS:
        if a >= lo:
            lab = name
    return lab
