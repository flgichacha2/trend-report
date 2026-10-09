"""[3] 인기 앱·크롬확장 — 인사이트 중심 텔레그램 요약 (네트워크 없음, UTF-8 stdout, 1,500자 이내).

사용: python -I scripts\\telegram_summary.py                  (기본: data/snapshots)
      python -I scripts\\telegram_summary.py --snap-root <폴더>   (테스트용 스냅샷 루트)

비교 기준
  1순위 직전 스냅샷: 한국 무료 전체 Top100(아이폰·갤럭시) 신규 진입/급상승/이탈, 아이폰 카테고리 Top50 신규,
        미국 Top50 신규(한국 차트에 없는 앱), 크롬 목록 신규 확장·사용자/평점 변화
  2순위(직전 스냅샷이 없거나 변화가 없을 때): 출시일 기반 신규(출시 60일 이내인데 Top100), 최근 1년 등록 크롬 확장,
        미국에만 있는 앱 — 모두 오늘 스냅샷에서 계산
앱 유형(APP_TYPES)을 이름으로 분류하고, 유형마다 '한국어·국내 사이트용 크롬 확장'을 오늘 크롬 목록에서 찾아
최대 사용자 수로 빈자리를 판단한다: <5만=공백(크롬확장 후보) / <100만=경쟁 있음 / 그 이상=포화.

규칙 표 (점수 높은 순으로 섹션에 노출, 같은 데이터면 같은 결과)
| ID        | 조건                                                                 | 🔄 변화 / 💡 의미 / ✅ 행동                                   | 점수                 |
|-----------|----------------------------------------------------------------------|---------------------------------------------------------------|----------------------|
| A-NEW     | 직전 Top200에 없던 앱이 한국 무료 전체 Top100에 진입(아이폰·갤럭시)     | 신규 진입 목록                                                 | 4 (고정)             |
| A-UP      | 같은 차트에서 10계단 이상 상승                                          | 급상승 목록                                                    | 3.5 (고정)           |
| A-CAT     | 아이폰 생산성·교육·쇼핑·유틸·비즈니스·금융 Top50 신규 진입               | 카테고리 신규 목록                                              | 2.5 (고정)           |
| A-OUT     | 직전 Top30이던 앱이 Top100 밖으로                                        | 반짝 순위 경고                                                  | 1.5 (고정)           |
| A-AI      | 한국 Top100(두 스토어 합) AI 앱 수 변화 |Δ| ≥ 2                        | AI 앱 확산/주춤                                                 | 1.0|Δ|               |
| T-GAP     | 신규·급상승·출시60일 앱의 유형이 '공백'(국내용 크롬 확장 최대 <5만)      | "PC·크롬 쪽 빈자리 → 크롬확장 후보로 메모"                        | 3+순위가점(≤1)       |
| T-COMP    | 같은 조건, 국내용 크롬 확장 5만~100만                                    | "경쟁 있음 → 한국 사이트 특화로 차별화 메모"                      | 2+순위가점           |
| T-SAT     | 같은 조건, 100만 이상 또는 AI 도우미 유형                                | "범용 AI 확장은 포화 → 직군·상황 특화 AI 확장 메모"               | 1.5+순위가점         |
| T-FIN     | 같은 조건, 유형이 금융·증권                                              | 관련 기업 실적/뉴스 확인해볼 것(매수·매도 권유 아님, 1개만)        | 1.2+순위가점         |
| T-MOBILE  | 같은 조건, 숏폼 드라마·카메라(모바일 전용 유행)                          | 의미 줄만                                                       | 0.8                  |
| US-NEW    | 직전 미국 Top50에 없던 앱 중 한국 어떤 차트에도 없는 앱                   | "미국에서 뜨는 X, 한국엔 없음 → 아이디어 메모"                    | 1.8 (고정)           |
| C-NEW     | 크롬 목록에 처음 보인 확장 중 사용자 ≥ 1만                               | 신규 확장 목록                                                   | 1.6 (고정)           |
| C-USERS   | 사용자 ≥ 10만 확장의 사용자 수 +20% 이상                                 | 빠르게 크는 확장 → 그 카테고리 경쟁 확장 조사                      | 1.4 (고정)           |
| C-RATE    | 사용자 ≥ 100만 확장 평점 −0.05 이상 하락                                 | 불만 증가 → 대체 확장 기회 메모                                   | 1.3 (고정)           |
| NOCHG     | 직전 스냅샷 대비 위 A-/US-/C- 규칙이 하나도 안 걸림(또는 직전 없음)         | "큰 변화 없음" 문구                                              | 3.5 (고정)           |
| B-FRESH   | 직전 스냅샷이 없거나 NOCHG: 출시 60일 이내인데 아이폰 Top100(카테고리 포함) | 출시일 기반 신규 → T-* 규칙으로 행동                             | 3.0 (고정)           |
| B-CHROME  | 같은 때: 최근 1년 등록 크롬 확장 수와 AI 비중                             | AI 보조도구 흐름                                                 | 1.0+회전             |
| B-US      | 같은 때: 미국 Top50 중 한국 차트에 없는 앱                                | 아이디어 메모                                                     | 1.0+회전             |
| E-*       | 항상: 1~3위, Top100 AI 앱 수, 크롬 AI 확장 1위                            | 근거 줄                                                          | 0.2~0.5              |
'회전' = 날짜에 따라 결정적으로 바뀌는 가산점(0~0.6). 변화 없는 날에도 같은 문구만 반복되지 않게 한다.
"""
import json
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # -I 모드 대응

import pandas as pd  # noqa: E402

import insight_fmt as F  # noqa: E402

TITLE = "[3] 인기 앱·크롬확장"
SNAP_ROOT = os.path.join(os.path.dirname(HERE), "data", "snapshots")

FRESH_DAYS, UP_STEPS, GAP_USERS, COMP_USERS = 60, 10, 50_000, 1_000_000
AI_RE = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|GPT|Gemini|Claude|Copilot|Perplexity|Grok|DeepSeek|챗봇|인공지능|뤼튼|에이닷",
                   re.I)
MAIN = [("아이폰", "appstore_itunes", "kr", "top-free", "all"),
        ("갤럭시", "gplay", "kr", "top-free", "APPLICATION")]
CATS = [("아이폰 생산성", "6007"), ("아이폰 교육", "6017"), ("아이폰 쇼핑", "6024"), ("아이폰 유틸", "6002"),
        ("아이폰 비즈니스", "6000"), ("아이폰 금융", "6015")]
IOS_CAT_NAME = {"all": "전체", "6007": "생산성", "6017": "교육", "6024": "쇼핑", "6002": "유틸", "6000": "비즈니스",
                "6015": "금융", "6013": "건강", "6012": "라이프", "6016": "엔터", "6008": "사진", "6005": "소셜"}

# (유형, 앱 이름 정규식, 한국어·국내 사이트용 크롬 확장 정규식 또는 None, 성격)
APP_TYPES = [
    ("녹음·요약", r"녹음|회의록|강의|요약|노트|note|transcri|summary", r"녹음|회의록|강의\s?요약|회의\s?요약", "tool"),
    ("가격비교·쇼핑비서", r"최저가|가격|폴센트|칩스|쇼핑\s?비서|쇼포트|price|쿠폰", r"쿠팡|네이버|g마켓|지마켓|11번가|다나와", "tool"),
    ("HWP·PDF 문서", r"pdf|hwp|한글\s?뷰어|문서|docx|ocr|스캐너|scan", r"hwp|한글\s?(?:문서|뷰어|파일)", "tool"),
    ("숏폼 차단·집중", r"차단|집중|focus|block|디톡스|스크린\s?타임|screen\s?time", r"쇼츠|숏폼|릴스|hide shorts|shorts block|집중\s?모드",
     "tool"),
    ("번역·외국어", r"번역|자막|영어|일본어|회화|translat|subtitle|speak|보카|vocab|duolingo|듀오링고",
     r"이중\s?자막|쿠팡플레이|티빙|웨이브|단어장", "tool"),
    ("투두·플래너", r"투두|todo|to-do|플래너|planner|캘린더|calendar|schedule", r"투두|할\s?일\s?(?:목록|관리)|플래너", "tool"),
    ("금융·증권", r"은행|증권|bank|mts|투자|주식|카드|머니|금융|페이(?!지)", None, "fin"),
    ("숏폼 드라마·영상", r"drama|드라마|short|reels|숏폼|쇼츠|릴스|cashflicks", None, "mobile"),
    ("카메라·사진", r"카메라|cam(?![a-z])|필름|photo|포토|보정|사진", None, "mobile"),
    ("AI 도우미", AI_RE.pattern, r"chatgpt|claude|gemini", "tool"),
]


def load(d):
    with open(os.path.join(d, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    return {"summary": s, "date": s["date"],
            "ranks": pd.read_csv(os.path.join(d, "app_ranks.csv"), dtype={"app_id": str, "genre": str}),
            "chrome": pd.read_csv(os.path.join(d, "chrome_extensions.csv"))}


def chart(ranks, store, country, ch, genre, top=100):
    g = ranks[(ranks.store == store) & (ranks.country == country) & (ranks.chart == ch) & (ranks.genre == genre)]
    return g[g["rank"] <= top].sort_values("rank")


def short(name, k=12):
    name = re.split(r"\s[-–:|]\s|:|,|\(|\sby\s|\s-", str(name))[0].strip()
    return name if len(name) <= k else name[:k - 1] + "…"


def users(x):
    if x >= 10000:
        return f"{x / 10000:,.0f}만명"
    return f"{int(x):,}명"


def app_type(name):
    for label, pat, crx, nature in APP_TYPES:
        if re.search(pat, str(name), re.I):
            return label, crx, nature
    return None, None, None


def chrome_gap(chrome, crx):
    """국내용 같은 기능 확장 중 사용자 최다(이름, 사용자수). 없으면 (None, 0)."""
    c = chrome.dropna(subset=["users"]).drop_duplicates("ext_id")
    txt = c.name.fillna("") + " " + c.short_desc.fillna("")
    m = c[txt.str.contains(crx, case=False, regex=True)]
    if m.empty:
        return None, 0
    t = m.sort_values(["users", "name"], ascending=[False, True]).iloc[0]
    return t["name"], t["users"]


def type_item(key, name, where, rank, chrome, base_score):
    """앱 1개 → 유형별 행동(T-*) Item. 해당 유형이 없으면 None."""
    label, crx, nature = app_type(name)
    if label is None:
        return None
    rb = max(0.0, (101 - rank) / 100)  # 순위 가점(1위≈1)
    app = f"{short(name)}({where} {rank}위)"
    if nature == "fin":
        return F.Item(f"T-FIN-{key}", base_score + 1.2 + rb, kind="stock", mtopic="fin",
                      meaning="금융 앱 순위 변화는 앱 개편·이벤트 영향이 커요. 트렌드보다 개별 이슈로 보세요.",
                      action=f"{app} 상승 → 관련 기업 실적·뉴스 확인해볼 것(매수·매도 권유 아님)")
    if nature == "mobile":
        return F.Item(f"T-MOB-{key}", base_score + 0.8, mtopic="mobile",
                      meaning=f"{label} 앱은 모바일 전용 유행이라 크롬확장과는 거리가 있어요.")
    ext, u = chrome_gap(chrome, crx)
    if label == "AI 도우미" or u >= COMP_USERS:
        return F.Item(f"T-SAT-{key}", base_score + 1.5 + rb, mtopic="sat",
                      meaning="AI 앱은 계속 뜨지만 크롬 쪽 AI 확장은 이미 대형 제품이 자리 잡았어요.",
                      action=f"{app}: 크롬 AI 확장은 '{short(ext, 10)}'({users(u)}) 등 이미 포화 → 이 앱처럼 "
                             f"직군·상황을 좁힌 AI 확장 아이디어로 메모")
    if u >= GAP_USERS:
        return F.Item(f"T-COMP-{key}", base_score + 2 + rb, mtopic="comp",
                      meaning=f"{label} 수요는 앱·크롬 모두 있어요. 국내 사이트 특화가 차별점이에요.",
                      action=f"{app}: 국내용 크롬 확장은 '{short(ext, 10)}'({users(u)}) 수준 → 한국 사이트 특화로 "
                             f"차별화 가능한지 메모")
    gap_txt = f"최대 {users(u)}" if u else "수집 목록에 없음"
    return F.Item(f"T-GAP-{key}", base_score + 3 + rb, mtopic="gap",
                  meaning=f"앱으로는 {label} 수요가 뜨는데 PC·크롬 쪽은 비어 있어요 — 사이드 사업 기회예요.",
                  action=f"{app}: 같은 기능의 국내용 크롬 확장 {gap_txt} → 크롬확장 후보로 메모",
                  evidence=f"{label} 국내용 크롬 확장 {gap_txt}")


def ai_count(ranks):
    kr = pd.concat([chart(ranks, *k) for _, *k in MAIN])
    return kr[kr["name"].astype(str).str.contains(AI_RE)]["name"].nunique()


def main():
    F.setup_stdout()
    root = F.parse_args(SNAP_ROOT)
    cur_dir, prev_dir = F.pick_snapshots(root)
    if cur_dir is None:
        print(f"📌 {TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        return 1
    cur = load(cur_dir)
    prev = load(prev_dir) if prev_dir else None
    ranks, chrome, day = cur["ranks"], cur["chrome"], cur["date"]
    today = date.fromisoformat(day)
    items, fired = [], 0
    kr_ids = set(ranks[ranks.country == "kr"].app_id) | set(ranks[ranks.country == "kr"]["name"])

    # ---------- 직전 스냅샷 대비 ----------
    if prev:
        pr, pday = prev["ranks"], prev["date"][5:]
        news, ups, outs = [], [], []
        for label, *key in MAIN:
            c, p = chart(ranks, *key), chart(pr, *key, top=200)
            if c.empty or p.empty:
                continue
            m = c.merge(p[["app_id", "rank"]], on="app_id", how="left", suffixes=("", "_p"))
            for r in m[m.rank_p.isna()].itertuples():
                news.append((r.rank, label, r.name, r.app_id))
            m = m.dropna(subset=["rank_p"])
            for r in m[(m.rank_p - m["rank"]) >= UP_STEPS].itertuples():
                ups.append((-(r.rank_p - r.rank), label, r.name, int(r.rank_p), r.rank, r.app_id))
            p30 = chart(pr, *key, top=30)
            for r in p30[~p30.app_id.isin(c.app_id)].itertuples():
                outs.append((r.rank, label, r.name))
        news.sort(), ups.sort(), outs.sort()
        if news:
            fired += 1
            items.append(F.Item("A-NEW", 4, change=f"지난번({pday}) 대비 한국 Top100 신규 진입 {len(news)}개: "
                                + " · ".join(f"{short(x[2])}({x[1]} {x[0]}위)" for x in news[:3])))
            for rk, label, name, aid in news[:6]:
                it = type_item(f"N-{label}-{aid}", name, label, rk, chrome, 0.5)
                if it:
                    items.append(it)
        if ups:
            fired += 1
            items.append(F.Item("A-UP", 3.5, change="순위 급상승: " + " · ".join(
                f"{short(x[2])}({x[1]} {x[3]}→{x[4]}위)" for x in ups[:3])))
            for g, label, name, rp, rk, aid in ups[:6]:
                it = type_item(f"U-{label}-{aid}", name, label, rk, chrome, 0.3)
                if it:
                    items.append(it)
        if outs:
            fired += 1
            items.append(F.Item("A-OUT", 1.5, change="Top100 밖으로 밀려난 상위권 앱: "
                                + " · ".join(f"{short(x[2])}({x[1]} 전 {x[0]}위)" for x in outs[:2]),
                                meaning="며칠 만에 빠지는 앱은 광고·이벤트성 반짝 순위일 가능성이 커요."))
        cat_new = []
        for label, g in CATS:
            c, p = chart(ranks, "appstore_itunes", "kr", "top-free", g, 50), chart(pr, "appstore_itunes", "kr",
                                                                                 "top-free", g, 100)
            if c.empty or p.empty:
                continue
            for r in c[~c.app_id.isin(p.app_id)].itertuples():
                cat_new.append((r.rank, label, r.name, r.app_id))
        cat_new.sort()
        if cat_new:
            fired += 1
            items.append(F.Item("A-CAT", 2.5, change="카테고리 신규 진입: " + " · ".join(
                f"{short(x[2])}({x[1]} {x[0]}위)" for x in cat_new[:3])))
            for rk, label, name, aid in cat_new[:6]:
                it = type_item(f"C-{label}-{aid}", name, label, rk, chrome, 0.0)
                if it:
                    items.append(it)
        a_now, a_prev = ai_count(ranks), ai_count(pr)
        if abs(a_now - a_prev) >= 2:
            fired += 1
            items.append(F.Item("A-AI", abs(a_now - a_prev),
                                change=f"한국 Top100의 AI 앱 {a_prev}→{a_now}개",
                                meaning=("AI 앱이 일상 앱으로 더 퍼지고 있어요." if a_now > a_prev else
                                         "AI 앱 수가 줄었어요. 신규 AI 앱의 반짝 효과가 빠지는 중일 수 있어요.")))
        us_c, us_p = chart(ranks, "appstore_itunes", "us", "top-free", "all", 50), chart(
            pr, "appstore_itunes", "us", "top-free", "all", 100)
        if not us_c.empty and not us_p.empty:
            us_new = us_c[~us_c.app_id.isin(us_p.app_id) & ~us_c.app_id.isin(kr_ids) & ~us_c["name"].isin(kr_ids)]
            if len(us_new):
                fired += 1
                r = us_new.iloc[0]
                items.append(F.Item("US-NEW", 1.8,
                                    change=f"미국 Top50 새 얼굴(한국 차트엔 없음): {short(r['name'])} {r['rank']}위",
                                    action=f"미국에서 뜨는 {short(r['name'])} — 한국엔 없음 → 기능을 확인해 한국판 아이디어로 메모"))
        pc = prev["chrome"].dropna(subset=["users"]).drop_duplicates("ext_id").set_index("ext_id")
        cc = chrome.dropna(subset=["users"]).drop_duplicates("ext_id").set_index("ext_id")
        new_ext = cc[~cc.index.isin(pc.index) & (cc.users >= 10000)].sort_values(["users", "name"], ascending=[False, True])
        if len(new_ext):
            fired += 1
            t = new_ext.iloc[0]
            ai_new = new_ext["name"].astype(str).str.contains(AI_RE).sum()
            items.append(F.Item("C-NEW", 1.6,
                                change=f"크롬 인기 목록에 새로 보인 확장 {len(new_ext)}개(AI {ai_new}개), 최다 {short(t['name'], 16)} "
                                       f"{users(t['users'])}",
                                meaning=("크롬에서도 AI 보조 확장이 계속 새로 나와요." if ai_new else None)))
        both = cc.join(pc[["users", "rating"]], rsuffix="_p", how="inner")
        grow = both[(both.users_p >= 100000) & (both.users >= both.users_p * 1.2)].sort_values(
            ["users", "name"], ascending=[False, True])
        if len(grow):
            fired += 1
            t = grow.iloc[0]
            items.append(F.Item("C-USERS", 1.4,
                                change=f"크롬 '{short(t['name'], 16)}' 사용자 {users(t['users_p'])}→{users(t['users'])}",
                                action=f"빠르게 크는 '{short(t['name'], 16)}' — 같은 카테고리 국내용 확장이 있는지 조사"))
        drop = both[(both.users >= 1_000_000) & ((both.rating_p - both.rating) >= 0.05)].sort_values(
            ["users", "name"], ascending=[False, True])
        if len(drop):
            fired += 1
            t = drop.iloc[0]
            items.append(F.Item("C-RATE", 1.3,
                                change=f"크롬 '{short(t['name'], 16)}'({users(t['users'])}) 평점 {t['rating_p']:.2f}→{t['rating']:.2f}",
                                meaning="대형 확장의 평점이 떨어지면 불만이 쌓이는 중 — 대체 확장의 기회예요.",
                                action=f"'{short(t['name'], 16)}' 최근 1~2점 리뷰를 읽고 불만 1개를 해결하는 확장 아이디어 메모"))

    # ---------- 직전 없음 / 변화 없음 → 출시일 기반 신규 등 ----------
    if fired == 0:
        if prev:
            items.append(F.Item("NOCHG", 3.5,
                                change=f"지난번({prev['date'][5:]}) 대비 Top100 신규·급상승·크롬 신규 없음 — 큰 변화 없음",
                                meaning="상위권이 그대로라는 건 지금 인기 앱이 '반짝'이 아니라는 뜻이에요."))
        else:
            items.append(F.Item("NOCHG", 3.5, change="직전 스냅샷이 없어 출시일 기준으로 '새로 뜬 앱'을 봤어요."))
        ios_all = ranks[(ranks.store == "appstore_itunes") & (ranks.country == "kr") & (ranks.chart == "top-free")]
        rel = pd.to_datetime(ios_all.release_date, errors="coerce")
        fresh = ios_all[rel >= pd.Timestamp(today - timedelta(days=FRESH_DAYS))].sort_values(["rank", "genre"])
        fresh = fresh.drop_duplicates("app_id")
        if len(fresh):
            items.append(F.Item("B-FRESH", 3.0, change=f"출시 {FRESH_DAYS}일 안 된 앱 {len(fresh)}개가 아이폰 Top100(카테고리 포함)에: "
                                + " · ".join(f"{short(r['name'])}({IOS_CAT_NAME.get(r['genre'], r['genre'])} {r['rank']}위)"
                                             for _, r in fresh.head(3).iterrows())))
            for _, r in fresh.head(12).iterrows():
                it = type_item(f"F-{r['app_id']}", r["name"], f"아이폰 {IOS_CAT_NAME.get(r['genre'], r['genre'])}",
                               int(r["rank"]), chrome, 0.0)
                if it:
                    items.append(it)
        rb = lambda k: 1.0 + F.rotate_bonus(k, day, span=7)  # noqa: E731
        cu = chrome.dropna(subset=["users"]).drop_duplicates("ext_id")
        reg = pd.to_datetime(cu.updated, errors="coerce")
        new1y = cu[reg >= pd.Timestamp(today - timedelta(days=365))]
        if len(new1y):
            ai1 = new1y["name"].astype(str).str.contains(AI_RE) | new1y.short_desc.fillna("").str.contains(AI_RE)
            items.append(F.Item("B-CHROME", rb("B-CHROME"),
                                change=f"크롬: 최근 1년 등록 확장 {len(new1y)}개 중 AI 관련 {int(ai1.sum())}개",
                                meaning="크롬은 범용 AI보다 ChatGPT·Claude를 '보조'하는 작은 확장이 새로 생기는 흐름이에요.",
                                action="자주 쓰는 AI 채팅의 불편 1개(대화 정리·내보내기 등)를 적어 두고 확장 MVP 범위로 정리"))
        us = chart(ranks, "appstore_itunes", "us", "top-free", "all", 50)
        us_only = us[~us.app_id.isin(kr_ids) & ~us["name"].isin(kr_ids)]
        if len(us_only):
            ai_us = us_only[us_only["name"].astype(str).str.contains(AI_RE)]
            r = (ai_us if len(ai_us) else us_only).iloc[0]
            items.append(F.Item("B-US", rb("B-US"),
                                meaning=f"미국 Top50 중 {len(us_only)}개는 한국 차트에 없어요 — 1~2년 뒤 한국에 올 수 있는 후보예요.",
                                action=f"미국 {r['rank']}위 {short(r['name'])}(한국 차트 없음)의 기능을 확인해 한국판 아이디어로 메모",
                                evidence=f"미국 Top50 중 한국 차트에 없는 앱 {len(us_only)}개"))

    # ---------- 근거(항상) ----------
    tops = []
    for label, *key in MAIN:
        c = chart(ranks, *key, top=3)
        if len(c):
            tops.append(f"{label} 1~3위 " + "·".join(short(x, 10) for x in c["name"]))
    if tops:
        items.append(F.Item("E-TOP", 0.5, evidence=" / ".join(tops)))
    items.append(F.Item("E-AI", 0.4, evidence=f"한국 무료 Top100(두 스토어)의 AI 앱 {ai_count(ranks)}개"))
    ac = chrome[chrome["name"].astype(str).str.contains(AI_RE)].dropna(subset=["users"]).drop_duplicates("ext_id")
    if len(ac):
        t = ac.sort_values(["users", "name"], ascending=[False, True]).iloc[0]
        items.append(F.Item("E-CRX", 0.3, evidence=f"크롬 AI 확장 사용자 1위 {short(t['name'], 16)} {users(t['users'])}"
                                                   f"(평점 {t['rating']:.1f})"))

    print(F.render(TITLE, day, items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
