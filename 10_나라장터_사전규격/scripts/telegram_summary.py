# -*- coding: utf-8 -*-
"""
텔레그램용 요약 [10] 정부 장바구니(나라장터 사전규격) — 네트워크 사용 안 함, 일반 텍스트, 1,500자 이내
  python -I -X utf8 scripts\\telegram_summary.py [--snaproot 테스트용_스냅샷_폴더]

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 직전 1개의 summary.json,
         data/processed/baseline.json(보고서 기준값: 최근 6개월·작년 같은 기간 분야 비율, 읽기 전용). 쓰는 것: 없음.

비교 기준: ① 직전 스냅샷의 '최근 30일 분야 비율'과 비교(Δ%p) ② 직전이 없으면 보고서 기준값(작년 같은 기간 비율)과 비교.
새 건(new) = 직전 스냅샷 이후 처음 보인 사전규격(daily_update.py 가 계산).

[행동 규칙표]  N(x) = 새 사전규격 중 x 분야 건수, Δ(x) = 30일 비율 변화(%p, 직전 스냅샷 대비), L(x) = 30일 비율(%)
 ID | 조건(변화형)                                   | 조건(수준형: 직전 스냅샷 없을 때)      | 행동 문구(요지)
 B1 | N(AI) ≥ 10 또는 Δ(AI) ≥ +0.3                   | L(AI) ≥ 작년 비율 × 1.3              | AI 사업 큰 건 1개 과업지시서 열어 '요구 기능' 메모(자동화·확장 아이디어 후보)
 B2 | N(보안) ≥ 10 또는 Δ(보안) ≥ +0.3               | L(보안) ≥ 1                           | 보안관제·취약점 건 1개 요구사항 메모(본업 지식 연결)
 B3 | N(생성형AI) ≥ 3                                | L(생성형AI) ≥ 0.2                     | 생성형AI 사업의 보안·개인정보 요구(망분리·N2SF·가명처리) 확인
 B4 | N(개인정보) ≥ 3                                | -                                     | 개인정보 사업(영향평가·노출대응) 요구사항 훑기
 B5 | 새 건 중 AI·보안·클라우드 100억 이상 1건+      | -                                     | 수혜 업종 상장사 수주 공시 확인해볼 것(매수 권유 아님)
 B6 | 관심지역(제주 서귀포·영종·성남·강남) 새 건 1+  | -                                     | 그 지역 사업이 시설·개발 관련인지 확인(부동산 참고)
 B7 | N(스마트기기·PC)+N(노후교체) ≥ 15             | L(스마트기기·PC) ≥ 1                  | 교육청·학교 기기 교체 수요 → 관련 업종 확인
 B0 | 해당 없음                                      |                                       | 큰 변화 없음 → 주 1회 AI·보안 Top5만 훑기
 우선순위: 변화형 점수 = 100 + 건수÷임계값×10 (B5·B6 은 100 + 건수×5), 수준형 점수 = 비율÷임계값. 상위 3개.
"""
import argparse, json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [10] 정부 장바구니"
SHORT = {"AI(전체)": "AI", "생성형AI·LLM": "생성형AI", "정보보호·보안": "보안", "스마트기기·PC": "PC·태블릿",
         "노후시설·장비 교체": "노후교체", "정보시스템 구축·고도화": "정보시스템", "CCTV·영상감시": "CCTV"}
MAIN = ["AI(전체)", "생성형AI·LLM", "정보보호·보안", "클라우드", "개인정보", "데이터", "로봇", "드론", "디지털트윈",
        "스마트기기·PC", "노후시설·장비 교체"]


def nm(k):
    return SHORT.get(k, k)


def p1(x):
    return f"{x:.1f}".rstrip("0").rstrip(".") if abs(x) >= 0.1 or x == 0 else f"{x:.2f}"


def sgn(x):
    return ("+" if x > 0 else "") + p1(x)


def snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(root, d, "meta.json")))


def load(root, d):
    return json.load(open(os.path.join(root, d, "summary.json"), encoding="utf-8"))


def amt(e):
    return f"{e / 10000:.1f}조" if e >= 10000 else f"{e:,.0f}억" if e >= 10 else f"{e:.1f}억"


def cut(t, n=26):
    return t if len(t) <= n else t[:n - 1] + "…"


def actions(s, ps, base):
    N = s["new_by_cat"]; L = s["share_window"]
    D = (lambda k: L[k] - ps["share_window"].get(k, 0)) if ps else None
    ch, lv = [], []
    if ps:
        if N["AI(전체)"] >= 10 or D("AI(전체)") >= 0.3:
            ch.append((max(N["AI(전체)"] / 10, D("AI(전체)") / 0.3) * 10, "B1",
                       f"새 AI 사업 {N['AI(전체)']}건 → 큰 건 1개 과업지시서 열어 '요구 기능' 메모(자동화·크롬확장 아이디어 후보)"))
        if N["정보보호·보안"] >= 10 or D("정보보호·보안") >= 0.3:
            ch.append((max(N["정보보호·보안"] / 10, D("정보보호·보안") / 0.3) * 10, "B2",
                       f"새 보안 사업 {N['정보보호·보안']}건 → 보안관제·취약점 건 1개 요구사항 메모(본업 지식 연결)"))
        if N["생성형AI·LLM"] >= 3:
            ch.append((N["생성형AI·LLM"] / 3 * 10, "B3",
                       f"새 생성형AI 사업 {N['생성형AI·LLM']}건 → 보안·개인정보 요구(망분리·N2SF·가명처리) 문구 확인"))
        if N["개인정보"] >= 3:
            ch.append((N["개인정보"] / 3 * 10, "B4", f"새 개인정보 사업 {N['개인정보']}건 → 영향평가·노출대응 요구사항 훑어보기"))
        big = [x for x in s["new_focus_top"] if x["amount_eok"] >= 100]
        if big:
            ch.append((len(big) * 5, "B5", f"AI·보안 100억+ '{cut(big[0]['title'], 18)}' → 관련 업종 상장사 수주 공시 확인해볼 것(매수 권유 아님)"))
        wn = {k: v for k, v in s["watch_new"].items() if v["n"] > 0}
        if wn:
            k = max(wn, key=lambda x: wn[x]["n"])
            ch.append((sum(v["n"] for v in wn.values()) * 5, "B6", f"관심지역 새 사업 {k} {wn[k]['n']}건 등 → 시설·개발 관련인지 확인(부동산 참고)"))
        if N["스마트기기·PC"] + N["노후시설·장비 교체"] >= 15:
            ch.append(((N["스마트기기·PC"] + N["노후시설·장비 교체"]) / 15 * 10, "B7",
                       f"PC·태블릿·노후교체 새 건 {N['스마트기기·PC'] + N['노후시설·장비 교체']}건 → 학교·기관 기기 교체 수요 업종 확인"))
    else:
        prev_ai = (base or {}).get("share_prev", {}).get("AI(전체)", 0)
        if prev_ai and L["AI(전체)"] >= prev_ai * 1.3:
            lv.append((L["AI(전체)"] / (prev_ai * 1.3), "B1", f"AI 사업 비율 {p1(L['AI(전체)'])}%(작년 {p1(prev_ai)}%) → 큰 건 1개 과업지시서 열어 '요구 기능' 메모"))
        if L["정보보호·보안"] >= 1:
            lv.append((L["정보보호·보안"] / 1, "B2", f"보안 사업 비율 {p1(L['정보보호·보안'])}% → 보안관제·취약점 건 1개 요구사항 메모(본업 연결)"))
        if L["생성형AI·LLM"] >= 0.2:
            lv.append((L["생성형AI·LLM"] / 0.2, "B3", "생성형AI 사업의 보안·개인정보 요구(망분리·N2SF·가명처리) 문구 확인"))
        if L["스마트기기·PC"] >= 1:
            lv.append((L["스마트기기·PC"] / 1, "B7", f"PC·태블릿 사업 {p1(L['스마트기기·PC'])}% → 학교·기관 기기 교체 수요 업종 확인"))
    ch = sorted(((100 + v, i, t) for v, i, t in ch), key=lambda x: (-x[0], x[1]))
    lv = sorted(lv, key=lambda x: (-x[0], x[1]))
    out = (ch + lv)[:3]
    if not out:
        out = [(0, "B0", "큰 변화 없음 → 주 1회 AI·보안 Top5만 훑기")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snaproot", default=os.path.join(BASE, "data", "snapshots"))
    a = ap.parse_args()
    ds = snaps(a.snaproot)
    if not ds:
        print(f"{TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        sys.exit(1)
    cur = ds[-1]
    s = load(a.snaproot, cur)
    ps = load(a.snaproot, ds[-2]) if len(ds) >= 2 else None
    try:
        base = json.load(open(os.path.join(BASE, "data", "processed", "baseline.json"), encoding="utf-8"))
    except Exception:
        base = None
    date = f"{cur[:4]}-{cur[4:6]}-{cur[6:]}"
    L = s["share_window"]; N = s["new_by_cat"]

    changed = []
    if ps:
        pv = f"{ds[-2][4:6]}/{ds[-2][6:]}"
        changed.append(f"· 지난번({pv}) 이후 새 사전규격 {s['n_new']:,}건(예산 {amt(s['amt_new_eok'])}) — "
                       f"AI {N['AI(전체)']}·보안 {N['정보보호·보안']}·클라우드 {N['클라우드']}·개인정보 {N['개인정보']}건")
        d = {k: L[k] - ps["share_window"].get(k, 0) for k in MAIN}
        mv = sorted((k for k in d if abs(d[k]) >= 0.05), key=lambda k: -abs(d[k]) / max(ps["share_window"].get(k, 0), 0.5))[:3]
        if mv:
            changed.append("· 최근 30일 비율 변화: " + ", ".join(f"{nm(k)} {sgn(d[k])}%p" for k in mv))
        else:
            changed.append(f"· 최근 30일 분야 비율은 거의 그대로(AI {p1(L['AI(전체)'])}%, 보안 {p1(L['정보보호·보안'])}%)")
    else:
        changed.append(f"· 첫 스냅샷: 최근 30일 사전규격 {s['n_window']:,}건(예산 {amt(s['amt_window_eok'])})")
        if base:
            sp = base["share_prev"]
            changed.append(f"· 작년 4~10월 평균 대비 비율: AI {p1(sp['AI(전체)'])}→{p1(L['AI(전체)'])}%, "
                           f"생성형AI {p1(sp['생성형AI·LLM'])}→{p1(L['생성형AI·LLM'])}%, 보안 {p1(sp['정보보호·보안'])}→{p1(L['정보보호·보안'])}%")
    tops = s["new_focus_top"] or s["new_top"]
    if tops and ps:
        t = tops[0]
        changed.append(f"· 새 건 중 큰 것: {cut(t['title'])}({cut(t['org'], 12)}, {p1(t['amount_eok'])}억)")
    changed = changed[:3]

    meaning = []
    ai_l, sec_l = L["AI(전체)"], L["정보보호·보안"]
    if base and base["share_prev"].get("AI(전체)"):
        r = ai_l / base["share_prev"]["AI(전체)"]
        if r >= 1.3:
            meaning.append(f"· 공공 예산에서 AI 사업 비중이 작년의 {r:.1f}배. 본공고 전 단계라 1~2달 뒤 실제 입찰로 이어질 물량이에요.")
        else:
            meaning.append(f"· AI 사업 비중은 작년과 비슷한 수준({p1(ai_l)}%). 아직 '시범사업' 단계가 대부분이에요.")
    else:
        meaning.append(f"· 최근 30일 사전규격 중 AI {p1(ai_l)}%, 보안 {p1(sec_l)}% — 본공고 1~2달 전 미리 보는 정부 장바구니예요.")
    if N.get("생성형AI·LLM", 0) or L["생성형AI·LLM"] >= 0.2:
        meaning.append("· 생성형AI 사업은 보안·망분리 요건이 같이 붙어 '금융보안+AI' 경험이 쓰이는 영역이에요.")

    todo = [f"· {t}" for _, _, t in actions(s, ps, base)]

    ev = [f"· 최근 30일 {s['n_window']:,}건 · 예산 {amt(s['amt_window_eok'])} · SW사업 {p1(s['sw_share_window'])}%",
          "· 30일 비율: " + " · ".join(f"{nm(k)} {p1(L[k])}%" for k in ["AI(전체)", "생성형AI·LLM", "정보보호·보안", "클라우드", "데이터"]),
          f"· 새 건 {s['n_new']:,}건(기준: {s['new_basis']}) · 100억 이상 {s['new_big100']}건",
          "· 출처: 나라장터 사전규격공개(공개 조회)"]
    print(render(f"{TITLE} ({date})", changed, meaning, todo, ev))


def render(head, changed, meaning, todo, ev):
    def join(evl):
        return "\n".join([head, "🔄 무엇이 바뀌었나", *changed, "💡 무슨 의미", *meaning, "✅ 내가 할 일", *todo, "📊 근거", *evl])
    evl = list(ev)
    out = join(evl)
    while len(out) > LIMIT and len(evl) > 1:
        evl.pop(); out = join(evl)
    return out if len(out) <= LIMIT else out[:LIMIT - 1] + "…"


if __name__ == "__main__":
    main()
