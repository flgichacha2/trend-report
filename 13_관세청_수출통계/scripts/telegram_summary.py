# -*- coding: utf-8 -*-
"""
텔레그램용 요약 [13] 수출 성적표 (네트워크 사용 안 함, 일반 텍스트, 1,500자 이내)
  python -I -X utf8 scripts\\telegram_summary.py [--snaproot 다른_스냅샷_폴더]   # --snaproot 는 테스트용

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 직전 1개의 summary.json. 쓰는 것: 없음(stdout).
용어: 3M = 최근 3개월 합 전년 같은 3개월 대비(%), 잠정 = 관세청 10일 단위 잠정치(조업일수 차이 미반영)

[🔄 변화 규칙]
 C1 직전 스냅샷 있음 + 잠정치 새 구간 → "10일 잠정치 새로 나옴: 월·구간, 총수출 X억달러(전년비), 반도체(전년비)"
 C2 직전 스냅샷 있음 + 월별 확정치 새 달 → "월별 품목 통계 M월분 공개" + 3M 전년비가 가장 많이 바뀐 품목 2개(직전→최신)
 C3 직전 스냅샷 있음 + 새 데이터 없음 → "새로 공개된 수출 데이터 없음(직전 데이터 유지)" + 다음 공개 예상일
 C4 직전 스냅샷 없음 → 보고서 기준 비교: 최신 잠정 총수출·반도체 전년비 + 월별 3M 전년비 상·하위 품목

[✅ 행동 규칙표]  (덩어리 품목 = 조선·방산 묶음: 인도 시점에 따라 월별 출렁임이 커서 A2·A4 제외)
 ID | 조건                                                         | 점수                   | 행동 문구(요지)
 A1 | 잠정치 새 구간(C1)                                           | 50                     | 다음 잠정치(예상일)에서 반도체·총수출 증가세 유지되는지 다시 보기
 A2 | 덩어리 아님, 3M ≥ +25% 그리고 최근월 전년비 ≥ +20%           | min(3M, 100)           | {품목} 강세 → {상장사} 다음 실적에 반영되는지 확인해볼 것
 A3 | '쪼개 볼수록 강해짐'(국가 3M − 품목 3M ≥ 30%p, 증가액>0)     | 20 + min(차이,200)÷4   | {품목}×{국가} 급증 → {상장사} 그 지역 매출 비중 IR자료로 확인
 A4 | 덩어리 아님, 3M ≤ −10%                                       | 10 − 3M                | {품목} 둔화 → {상장사} 실적 눈높이 낮아지는지 확인
 A5 | 방산 묶음 중 3M 증가액 1위 국가(증가액 ≥ 5천만달러)           | 30                     | {국가}향 {품목} 늘어남 → {상장사} 수출 인도 일정 확인
 A0 | 해당 없음                                                    | -                      | 큰 변화 없음 → 다음 잠정치 공개일에 다시 보기
 점수 높은 순 3개, 같은 품목은 한 번만. 매수·매도 권유가 아니라 '확인해볼 것' 목록. 같은 데이터면 같은 결과.
"""
import argparse, datetime as dt, json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [13] 수출 성적표"
LUMPY = {"조선", "방산"}
SHORT = {"8542": "반도체", "3304": "화장품", "190230": "라면", "2103": "소스", "121221": "김", "121120": "인삼",
         "850423": "초고압변압기", "8504": "변압기전체", "8544": "전선", "8901": "선박", "8703": "승용차",
         "850760": "2차전지", "8710": "전차·장갑차", "9301": "무기", "9306": "탄약"}
CORP1 = {"8542": "SK하이닉스·삼성전자", "3304": "실리콘투·아모레퍼시픽", "190230": "삼양식품·농심", "2103": "삼양식품·대상",
         "121221": "동원F&B", "121120": "KT&G", "850423": "HD현대일렉트릭·효성중공업", "8504": "HD현대일렉트릭·LS ELECTRIC",
         "8544": "LS·대한전선", "8901": "HD한국조선해양·한화오션", "8703": "현대차·기아", "850760": "LG에너지솔루션·삼성SDI",
         "8710": "현대로템·한화에어로스페이스", "9301": "한화에어로스페이스·LIG넥스원", "9306": "풍산"}


def snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(root, d, "meta.json")))


def load(root, d):
    return json.load(open(os.path.join(root, d, "summary.json"), encoding="utf-8"))


def sg(x, d=0):
    if x is None or x != x:
        return "-"
    return f"{x:+.1f}%" if abs(x) < 1 and d == 0 else f"{x:+.{d}f}%"


def eok(k):  # 천 달러 → 억 달러
    return f"{k / 100000:,.0f}억달러" if k >= 1e6 else f"{k / 1000:,.0f}백만달러"


def mlabel(ym):
    return f"{int(ym[4:])}월"


def plabel(p):
    a, b = p.split("~")
    return "1~10일" if b == "10" else "1~20일" if b == "20" else "한 달 전체"


def next_release(tkey, monthly):
    ym, p = tkey.split(":")
    y, m = int(ym[:4]), int(ym[4:])
    e = int(p.split("~")[1])
    nm = dt.date(y + (m == 12), m % 12 + 1, 1)
    if e == 10:
        t = f"{m}/21경 {m}월 1~20일"
    elif e == 20:
        t = f"{nm.month}/1경 {m}월 전체"
    else:
        t = f"{nm.month}/11경 {nm.month}월 1~10일"
    my, mm = int(monthly[:4]), int(monthly[4:])
    n1 = dt.date(my + (mm == 12), mm % 12 + 1, 1)
    n2 = dt.date(n1.year + (n1.month == 12), n1.month % 12 + 1, 15)
    return t, f"{n2.month}/{n2.day}경 {n1.month}월 품목별"


def tent_rows(s, kind):
    t = (s.get("tentative") or {}).get(kind)
    return t, {r["name"]: r for r in (t or {}).get("rows", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snaproot", default=os.path.join(BASE, "data", "snapshots"))
    a = ap.parse_args()
    ds = snaps(a.snaproot)
    if not ds:
        print(f"{TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        sys.exit(1)
    cur = ds[-1]
    S = load(a.snaproot, cur)
    P = load(a.snaproot, ds[-2]) if len(ds) >= 2 else None
    items = {r["hs"]: r for r in S["items"]}
    M = S["monthly_latest"]
    q3 = S["q3_months"]
    qlab = f"{int(q3[0][4:])}~{int(q3[-1][4:])}월"
    tP, TP = tent_rows(S, "P")
    tN, TN = tent_rows(S, "N")
    nt, nmo = next_release(S["tentative_key"], M)

    # 잠정치 핵심 수치
    tot, semi = TP.get("전체"), TP.get("반도체")
    ex = None
    if tot and semi and tot["ly"] - semi["ly"] > 0:
        ex = ((tot["cur"] - semi["cur"]) / (tot["ly"] - semi["ly"]) - 1) * 100
    share = semi["cur"] / tot["cur"] * 100 if tot and semi and tot["cur"] else None
    tline = (f"{mlabel(tP['ym'])} {plabel(tP['period'])} 수출 {eok(tot['cur'])}(작년보다 {sg(tot['yoy'])}), 반도체 {sg(semi['yoy'])}"
             if tot and semi else "")

    # 🔄 변화
    ch = []
    if P is not None:
        if S.get("new_tentative") and tline:
            ch.append(f"· 10일 잠정치 새로 나옴: {tline}")
        if S.get("new_monthly"):
            pi = {r["hs"]: r for r in P.get("items", [])}
            diffs = sorted(((abs((r["q3_yoy"] or 0) - (pi[h]["q3_yoy"] or 0)), h) for h, r in items.items() if h in pi), reverse=True)[:2]
            ch.append(f"· 월별 품목 통계 {mlabel(M)}분 공개: " + ", ".join(
                f"{SHORT[h]} 3M {sg(pi[h]['q3_yoy'])}→{sg(items[h]['q3_yoy'])}" for _, h in diffs))
        if not S.get("data_updated") or not ch:
            ch.append(f"· 새로 공개된 수출 데이터 없음 → {(S.get('kept_from') or ds[-2])[4:6]}/{(S.get('kept_from') or ds[-2])[6:]} 데이터 그대로")
            ch.append(f"· 다음 공개 예상: {nt} 잠정치, {nmo} 확정치")
    else:
        if tline:
            ch.append(f"· {tline}")
        nl = [r for r in S["items"] if r["group"] not in LUMPY and r["q3_yoy"] is not None]
        nl.sort(key=lambda r: -r["q3_yoy"])
        ch.append(f"· {qlab} 3개월 전년비 상위: " + ", ".join(f"{SHORT[r['hs']]} {sg(r['q3_yoy'])}" for r in nl[:3])
                  + " / 하위: " + ", ".join(f"{SHORT[r['hs']]} {sg(r['q3_yoy'])}" for r in nl[-2:]))
    ch = ch[:3]

    # 💡 의미
    mean = []
    if share is not None and ex is not None:
        if share >= 40:
            mean.append(f"· 수출이 반도체에 쏠림(비중 {share:.0f}%). 반도체 빼면 {sg(ex)}라 체감 업황은 숫자보다 약할 수 있어요.")
        else:
            mean.append(f"· 반도체 비중 {share:.0f}%, 반도체 빼고도 {sg(ex)}로 고르게 늘어나는 중.")
    kc = [items[h] for h in ("3304", "190230", "2103", "121221") if h in items]
    if kc:
        good = [f"{SHORT[r['hs']]} {sg(r['q3_yoy'])}" for r in kc if (r["q3_yoy"] or 0) > 0]
        bad = [f"{SHORT[r['hs']]} {sg(r['q3_yoy'])}" for r in kc if (r["q3_yoy"] or 0) <= 0]
        mean.append("· K뷰티·K푸드 3개월: " + (", ".join(good) + " 강세" if good else "강세 품목 없음")
                    + (" / " + ", ".join(bad) + " 약세" if bad else ""))

    # ✅ 할 일
    cands = []
    if P is not None and S.get("new_tentative"):
        cands.append((50, "A1", "_tent", f"다음 잠정치({nt})에서 반도체·총수출 증가세 유지되는지 다시 보기"))
    for h, r in items.items():
        g, q, y = r["group"], r["q3_yoy"], r["yoy"]
        if q is None:
            continue
        if g not in LUMPY and q >= 25 and (y or 0) >= 20:
            cands.append((min(q, 100), "A2", h, f"{SHORT[h]} 3개월 {sg(q)}·{mlabel(M)} {sg(y)} → {CORP1[h]} 다음 실적에 반영되는지 확인해볼 것"))
        if g not in LUMPY and q <= -10:
            cands.append((10 - q, "A4", h, f"{SHORT[h]} 3개월 {sg(q)} 둔화 → {CORP1[h]} 실적 눈높이 낮아지는지 확인"))
    for c in S.get("split", []):
        h = c["hs"]
        gap = (c["q3_yoy"] or 0) - (c["item_q3_yoy"] or 0)
        cands.append((20 + min(gap, 200) / 4, "A3", h,
                      f"{SHORT[h]}×{c['cnty']} {sg(c['q3_yoy'])}(전체 {sg(c['item_q3_yoy'])}) → {CORP1[h]} {c['cnty']} 매출 비중 IR자료로 확인"))
    best = None
    for h in ("8710", "9301", "9306"):
        for u in (S.get("movers", {}).get(h, {}).get("up") or [])[:1]:
            if u["q3_diff"] >= 50000 and (best is None or u["q3_diff"] > best[1]["q3_diff"]):
                best = (h, u)
    if best:
        h, u = best
        cands.append((30, "A5", h, f"{u['cnty']}향 {SHORT[h]} 3개월 +{u['q3_diff'] / 1000:,.0f}백만달러 → {CORP1[h]} 수출 인도 일정 확인"))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    todo, used = [], set()
    for sc, rid, h, txt in cands:
        if h not in used and len(todo) < 3:
            todo.append(f"· {txt}"); used.add(h)
    if not todo:
        todo = [f"· 큰 변화 없음 → 다음 잠정치({nt}) 공개 때 다시 보기"]

    # 📊 근거
    ev = []
    if tline:
        cn = sorted((r for n, r in TN.items() if n != "전체" and r["yoy"] is not None), key=lambda r: -r["cur"])[:3]
        ev.append(f"· 잠정 {mlabel(tP['ym'])} {plabel(tP['period'])}: " + ", ".join(f"{r['name']} {sg(r['yoy'])}" for r in cn)
                  + (f" · 반도체 비중 {share:.0f}%" if share else ""))
    order = ["8542", "3304", "190230", "850423", "850760", "8703", "8901", "8710"]
    ev.append(f"· {qlab} 3개월 전년비: " + ", ".join(f"{SHORT[h]} {sg(items[h]['q3_yoy'])}" for h in order[:5] if h in items))
    ev.append("  " + ", ".join(f"{SHORT[h]} {sg(items[h]['q3_yoy'])}" for h in order[5:] if h in items)
              + (f", 김 {sg(items['121221']['q3_yoy'])}" if "121221" in items else ""))
    sp = [c for c in S.get("split", []) if c["hs"] in ("3304", "190230", "2103", "850423", "8544", "850760")][:2]
    if sp:
        ev.append("· 쪼개 보면: " + ", ".join(f"{SHORT[c['hs']]}×{c['cnty']} {sg(c['q3_yoy'])}" for c in sp))
    foot = f"※ 관세청 수출입무역통계(잠정 {mlabel(tP['ym']) if tP else '-'}, 품목별 확정 {mlabel(M)}까지), 투자 권유 아님"
    print(render(f"{TITLE} ({cur[:4]}-{cur[4:6]}-{cur[6:]})", ch, mean, todo, ev, foot))


def render(head, ch, mean, todo, ev, foot):
    def join(e):
        return "\n".join([head, "🔄 무엇이 바뀌었나", *ch, "💡 무슨 의미", *mean, "✅ 내가 할 일", *todo, "📊 근거", *e, foot])
    e = list(ev)
    out = join(e)
    while len(out) > LIMIT and e:
        e.pop(); out = join(e)
    return out if len(out) <= LIMIT else out[:LIMIT - 1] + "…"


if __name__ == "__main__":
    main()
