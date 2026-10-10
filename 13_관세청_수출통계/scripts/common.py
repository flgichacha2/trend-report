# -*- coding: utf-8 -*-
"""
[13] 수출 성적표 공통 모듈: 관심 품목(HS)·관련 상장사, 관세청 수출입무역통계(tradedata.go.kr) 수집 함수, 분석 함수.

데이터 경로
 1) 공공데이터포털 관세청 API (키: MOLIT_API_KEY 와 같은 계정 키) — probe_api() 로 먼저 시도.
    2026-10-10 기준 '관세청_품목별 국가별 수출입실적(GW)' 등 3개 모두 SERVICE_KEY_IS_NOT_REGISTERED(403) → 활용신청 필요.
 2) 키 없이: tradedata.go.kr 화면이 쓰는 공개 조회(POST, 로그인 없음)
    - /cts/hmpg/retrieveTrade.do          : 수출입 실적(품목별 국가별, tradeKind=ETS_MNK_1020000E), 월별, 금액 단위 천 달러
    - /cts/hmpg/retrieveTentativeValues.do : 10일 단위 잠정치(품목 ETS_MNK_1050000A / 국가 ETS_MNK_1050000B), 천 달러
    - /cts/hmpg/retrieveSetSelectBoxTentative.do : 잠정치 최신 월(maxYear)
"""
import datetime as dt, os, sys, time
from pathlib import Path
from urllib.parse import unquote

try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parent

# 루트 .env 로드 (환경변수가 우선, Encoding 형식 키는 자동으로 Decoding) — 키 값은 출력하지 않음
try:
    from dotenv import dotenv_values
    for _k, _v in dotenv_values(ROOT / ".env").items():
        if _v and not os.environ.get(_k):
            os.environ[_k] = unquote(_v) if _k.endswith("_KEY") else _v
except Exception:
    pass

TD = "https://tradedata.go.kr"
H = {"X-Requested-With": "XMLHttpRequest", "Referer": TD + "/cts/index.do",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
SLEEP = 1.5

# 관심 품목: code, 이름, 묶음, 관련 상장사('확인해볼 것' 용, 매수·매도 권유 아님)
ITEMS = [
    ("8542", "반도체(집적회로)", "IT", "삼성전자, SK하이닉스"),
    ("3304", "화장품", "소비재", "실리콘투, 아모레퍼시픽, 코스맥스, 한국콜마, 에이피알"),
    ("190230", "라면(그 밖의 파스타)", "K푸드", "삼양식품, 농심, 오뚜기"),
    ("2103", "소스·조미료(불닭소스·고추장 등)", "K푸드", "삼양식품, CJ제일제당, 대상"),
    ("121221", "김 등 식용 해조류", "K푸드", "동원F&B, CJ제일제당(김 전문 상장사는 적음)"),
    ("121120", "인삼", "K푸드", "KT&G(정관장)"),
    ("850423", "초고압 변압기(1만kVA 초과)", "전력기기", "HD현대일렉트릭, 효성중공업, LS ELECTRIC"),
    ("8504", "변압기·전력변환기 전체", "전력기기", "HD현대일렉트릭, 효성중공업, LS ELECTRIC, 산일전기"),
    ("8544", "전선·케이블", "전력기기", "LS, 대한전선, 가온전선"),
    ("8901", "선박(여객·화물선)", "조선", "HD한국조선해양, 삼성중공업, 한화오션"),
    ("8703", "승용차", "자동차", "현대차, 기아"),
    ("850760", "리튬이온 2차전지", "2차전지", "LG에너지솔루션, 삼성SDI, SK이노베이션"),
    ("8710", "전차·장갑차(K2·K9 등)", "방산", "현대로템, 한화에어로스페이스"),
    ("9301", "무기(자주포·로켓 등)", "방산", "한화에어로스페이스, LIG넥스원"),
    ("9306", "탄약", "방산", "풍산"),
]
ITEM_NAME = {c: n for c, n, _, _ in ITEMS}
ITEM_GROUP = {c: g for c, _, g, _ in ITEMS}
ITEM_CORP = {c: k for c, _, _, k in ITEMS}
FOCUS_CNTY = ["미국", "중국", "베트남", "폴란드", "일본", "인도", "대만", "네덜란드", "아랍에미리트연합", "사우디아라비아"]

# 10일 잠정치 열 이름 (ETS0100173Q.js 표 머리글 순서, 수출 기준)
TENT_P = ["전체", "반도체", "철강제품", "승용차", "석유제품", "무선통신기기", "선박", "자동차부품", "컴퓨터주변기기", "정밀기기", "가전제품"]
TENT_N = ["전체", "중국", "미국", "유럽연합", "베트남", "홍콩", "일본", "대만", "인도", "싱가포르", "말레이시아"]


def num(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[4:])
    t = y * 12 + (m - 1) + k
    return f"{t // 12}{t % 12 + 1:02d}"


# ---------------------------------------------------------------- 공공데이터포털 API (키 시도)
API_LIST = [
    ("관세청_품목별 국가별 수출입실적(GW)", "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
     {"strtYymm": "202501", "endYymm": "202501", "hsSgn": "3304", "cntyCd": "US"}),
]


def probe_api():
    """MOLIT_API_KEY 로 관세청 API 활용 승인 여부만 확인. 키 값은 어디에도 남기지 않는다."""
    key = os.environ.get("MOLIT_API_KEY") or os.environ.get("DATA_GO_KR_KEY")
    if not key:
        return {"status": "no_key"}
    out = {}
    for name, url, p in API_LIST:
        try:
            r = requests.get(url, params={**p, "serviceKey": key}, timeout=30)
            t = r.text
            if "SERVICE_KEY_IS_NOT_REGISTERED" in t or r.status_code in (401, 403):
                out[name] = f"미승인({r.status_code})"
            elif "<resultCode>00</resultCode>" in t or "<item>" in t:
                out[name] = "승인"
            else:
                out[name] = f"기타({r.status_code})"
        except Exception as e:
            out[name] = f"오류:{type(e).__name__}"
        time.sleep(SLEEP)
    return {"status": "ok", "apis": out}


# ---------------------------------------------------------------- tradedata.go.kr (키 없음)
class TD_Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = H["User-Agent"]
        self.s.get(TD + "/cts/index.do", timeout=60)
        time.sleep(SLEEP)

    def post(self, path, data, timeout=180, tries=3):
        last = None
        for i in range(tries):
            try:
                r = self.s.post(TD + path, data=data, headers=H, timeout=timeout)
                r.raise_for_status()
                j = r.json()
                if j.get("error") == "true":
                    raise RuntimeError(f"tradedata 오류: {j.get('message')}")
                time.sleep(SLEEP)
                return j
            except Exception as e:
                last = e
                time.sleep(3 + 3 * i)
        raise last

    def open_menu(self, url, menu_id):
        self.s.get(TD + url, params={"menuId": menu_id}, headers={"Referer": TD + "/cts/index.do"}, timeout=60)
        time.sleep(SLEEP)


def tentative_maxmonth(sess):
    j = sess.post("/cts/hmpg/retrieveSetSelectBoxTentative.do", {})
    return j["item"]["maxYear"]


def fetch_tentative(sess, kind, fr, to):
    """10일 단위 잠정치(수출). kind='P'(품목) 또는 'N'(국가). 긴 표(월, 구간, 이름, 금액천달러)"""
    sk = {"P": "ETS_MNK_1050000A", "N": "ETS_MNK_1050000B"}[kind]
    names = TENT_P if kind == "P" else TENT_N
    j = sess.post("/cts/hmpg/retrieveTentativeValues.do",
                  {"statsKind": sk, "imexTpcd": "E", "priodKind": "MON", "priodFr": fr, "priodTo": to, "priodDate": "",
                   "selectPaging": "1", "showPagingLine": "1000", "sortColumn": "", "sortOrder": ""})
    rows = []
    for it in j.get("items", []):
        for i, nm in enumerate(names):
            rows.append({"ym": it["priodMon"], "period": it["priodDt"], "kind": kind, "name": nm,
                         "usd_k": num(it.get(f"itemUsdAmt{i:02d}"))})
    return pd.DataFrame(rows)


def monthly_latest(sess, probe_from):
    """월별 확정(수리일 기준) 통계가 공개된 최신 월: probe_from 부터 한 달씩 올려가며 HS 8542 조회"""
    base = {"priodKind": "MON", "statsBase": "acptDd", "ttwgTpcd": "1000", "selectPaging": "1", "showPagingLine": "15",
            "sortColumn": "", "sortOrder": "", "tradeKind": "ETS_MNK_1020000A", "hsSgnGrpCol": "HS4_SGN",
            "hsSgnWhrCol": "HS4_SGN", "hsSgn": "8542", "subHsSgn": ""}
    ym, last = probe_from, None
    for _ in range(4):
        j = sess.post("/cts/hmpg/retrieveTrade.do", {**base, "priodFr": ym, "priodTo": ym})
        if j.get("count", 0) and num(j["items"][0].get("expUsdAmt")) > 0:
            last = ym
            ym = ym_add(ym, 1)
        else:
            break
    return last


def fetch_item_country(sess, codes, fr, to):
    """품목별 국가별 월별 수출입(천 달러). 같은 자릿수 코드끼리 한 번에 조회"""
    out = []
    for digits in sorted({len(c) for c in codes}):
        grp = [c for c in codes if len(c) == digits]
        col = f"HS{digits}_SGN"
        for c in grp:  # 코드별로 나눠 요청(응답 크기·실패 범위 줄이기)
            j = sess.post("/cts/hmpg/retrieveTrade.do",
                          {"priodKind": "MON", "statsBase": "acptDd", "ttwgTpcd": "1000", "selectPaging": "1",
                           "showPagingLine": "20000", "sortColumn": "", "sortOrder": "", "tradeKind": "ETS_MNK_1020000E",
                           "priodFr": fr, "priodTo": to, "cntyNm": "", "hsSgnGrpCol": col, "hsSgnWhrCol": col,
                           "hsSgn": c, "subHsSgn": ""})
            n = 0
            for it in j.get("items", []):
                if it.get("priodTitle") == "총계" or not it.get("cntyNm"):
                    continue
                out.append({"ym": it["priodTitle"].replace(".", ""), "hs": it.get("hsSgn") or c, "cnty_cd": it.get("cntyCd"),
                            "cnty": it.get("cntyNm"), "exp_usd_k": num(it.get("expUsdAmt")), "exp_ton": num(it.get("expTtwg")),
                            "imp_usd_k": num(it.get("impUsdAmt"))})
                n += 1
            print(f"[monthly] {c} {fr}~{to} {n}행", flush=True)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- 분석
def pct(a, b):
    return None if not b else round((a / b - 1) * 100, 1)


def analyze_monthly(df, latest):
    """df: fetch_item_country 결과(25개월 이상). latest: 'YYYYMM'. 반환: dict(표들)"""
    M = latest
    m1, y1 = ym_add(M, -1), ym_add(M, -12)
    q = [ym_add(M, -k) for k in range(3)]
    qy = [ym_add(m, -12) for m in q]
    ytd = [m for m in sorted(df["ym"].unique()) if m[:4] == M[:4] and m <= M]
    ytdy = [ym_add(m, -12) for m in ytd]
    piv = df.groupby(["hs", "ym"])["exp_usd_k"].sum().unstack(fill_value=0)

    def g(row, ms):
        return float(sum(row.get(m, 0) for m in ms))

    items = []
    for hs in [c for c, *_ in ITEMS]:
        if hs not in piv.index:
            continue
        r = piv.loc[hs]
        items.append({"hs": hs, "name": ITEM_NAME[hs], "group": ITEM_GROUP[hs], "corp": ITEM_CORP[hs],
                      "m": g(r, [M]), "m_prev": g(r, [m1]), "m_ly": g(r, [y1]),
                      "mom": pct(g(r, [M]), g(r, [m1])), "yoy": pct(g(r, [M]), g(r, [y1])),
                      "q3": g(r, q), "q3_ly": g(r, qy), "q3_yoy": pct(g(r, q), g(r, qy)),
                      "ytd": g(r, ytd), "ytd_ly": g(r, ytdy), "ytd_yoy": pct(g(r, ytd), g(r, ytdy)),
                      "trend12": [round(g(r, [ym_add(M, -k)]) / 1000, 1) for k in range(11, -1, -1)]})
    # 품목×국가
    pc = df.groupby(["hs", "cnty", "ym"])["exp_usd_k"].sum().unstack(fill_value=0)
    ic = {it["hs"]: it for it in items}
    cells = []
    for (hs, cn), r in pc.iterrows():
        if hs not in ic:
            continue
        q3, q3l = g(r, q), g(r, qy)
        cells.append({"hs": hs, "name": ITEM_NAME[hs], "cnty": cn, "m": g(r, [M]), "m_ly": g(r, [y1]), "m_prev": g(r, [m1]),
                      "yoy": pct(g(r, [M]), g(r, [y1])), "q3": q3, "q3_ly": q3l, "q3_yoy": pct(q3, q3l),
                      "q3_diff": q3 - q3l, "share_q3": round(q3 / ic[hs]["q3"] * 100, 1) if ic[hs]["q3"] else None,
                      "item_q3_yoy": ic[hs]["q3_yoy"]})
    cells = pd.DataFrame(cells)
    return {"latest": M, "q3_months": sorted(q), "items": items, "cells": cells}


def pick_tops(res, min_q3_k=3000, n=8):
    """급증·급감 Top(3개월 합 기준, 증감액 순)과 '쪼개 볼수록 강해짐'"""
    c = res["cells"]
    big = c[(c["q3"] + c["q3_ly"]) >= min_q3_k * 2].copy() if len(c) else c
    up = big.sort_values("q3_diff", ascending=False).head(n)
    down = big.sort_values("q3_diff").head(n)
    # 쪼개 볼수록 강해짐: 품목 전체보다 3개월 증가율이 30%p 이상 높고, 직전 3개월 대비 의미 있는 규모(품목 내 비중 ≥3% 또는 300만달러↑)
    split = big[(big["q3_yoy"].notna()) & (big["item_q3_yoy"].notna())
                & (big["q3_yoy"] - big["item_q3_yoy"] >= 30) & (big["q3_diff"] > 0)
                & ((big["share_q3"] >= 3) | (big["q3"] >= 3000))].copy()
    split["gap"] = split["q3_yoy"] - split["item_q3_yoy"]
    # 품목마다 증감액 1위 → 그다음 2위 순으로 섞어서(반도체·선박 같은 큰 품목이 표를 독차지하지 않게)
    split = split.sort_values("q3_diff", ascending=False)
    split["rk"] = split.groupby("hs").cumcount()
    split = split[split["rk"] < 2].sort_values(["rk", "q3_diff"], ascending=[True, False]).head(n + 4).drop(columns="rk")
    # 새로 열린 시장: 작년 3개월 합 < 100만달러 → 올해 ≥ 1,000만달러
    new = c[(c["q3_ly"] < 1000) & (c["q3"] >= 10000)].sort_values("q3", ascending=False).head(n)
    return up, down, split, new


def per_item_movers(res, k=3, min_k=1000):
    """품목별 3개월 증감액 상위/하위 국가 (3개월 합 또는 작년 3개월 합 ≥ 100만달러)"""
    c = res["cells"]
    out = {}
    for hs in [x for x, *_ in ITEMS]:
        d = c[(c["hs"] == hs) & ((c["q3"] >= min_k) | (c["q3_ly"] >= min_k))]
        cols = ["cnty", "q3", "q3_ly", "q3_diff", "q3_yoy", "share_q3"]
        out[hs] = {"up": d[d["q3_diff"] > 0].sort_values("q3_diff", ascending=False).head(k)[cols].to_dict("records"),
                   "down": d[d["q3_diff"] < 0].sort_values("q3_diff").head(k)[cols].to_dict("records"),
                   "top": d.sort_values("q3", ascending=False).head(k)[cols].to_dict("records")}
    return out


def analyze_tentative(tp, tn):
    """10일 잠정치: 최신 월의 최신 구간 vs 전년 같은 월 같은 구간"""
    out = {}
    for kind, d in (("P", tp), ("N", tn)):
        if d is None or not len(d):
            continue
        lm = d["ym"].max()
        cur = d[d["ym"] == lm]
        stage = sorted(cur["period"].unique(), key=lambda s: int(s.split("~")[1]))[-1]
        ly = ym_add(lm, -12)
        prev = d[d["ym"] == ly]
        # 같은 단계: 01~10 / 01~20 / 말일
        def stage_of(p):
            e = int(p.split("~")[1]); return "10" if e == 10 else "20" if e == 20 else "END"
        st = stage_of(stage)
        prevp = [p for p in prev["period"].unique() if stage_of(p) == st]
        rows = []
        for nm in (TENT_P if kind == "P" else TENT_N):
            a = cur[(cur["period"] == stage) & (cur["name"] == nm)]["usd_k"].sum()
            b = prev[(prev["period"].isin(prevp)) & (prev["name"] == nm)]["usd_k"].sum()
            rows.append({"name": nm, "cur": a, "ly": b, "yoy": pct(a, b)})
        out[kind] = {"ym": lm, "period": stage, "ly_ym": ly, "ly_period": prevp[0] if prevp else None, "rows": rows}
    return out
