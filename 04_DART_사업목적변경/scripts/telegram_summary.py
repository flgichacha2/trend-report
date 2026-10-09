# -*- coding: utf-8 -*-
"""
텔레그램용 '인사이트 중심' 요약 [4] 기업 신사업(DART) (네트워크 사용 안 함, 일반 텍스트, 1,500자 이내)
  python -I -X utf8 scripts\\telegram_summary.py [--snaproot 다른_스냅샷_폴더]   # --snaproot 는 테스트용

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 그 이전 스냅샷들,
         data/theme_counts.csv · summary_periods.csv · extra_hot_bulk_stats.csv (보고서 기준값, 읽기 전용).
쓰는 것: 없음(stdout 만).

출력: 🔄 무엇이 바뀌었나 → 💡 무슨 의미 → ✅ 내가 할 일 → 📊 근거
- '새 회사' = 이번 스냅샷 new_cases.csv 중 이전 스냅샷에 없던 회사(이미 알린 회사의 정정공고는 따로 셈).
- 새 회사가 MIN_NEW(3) 곳 미만이면 '새 공시 적음'으로 보고 보고서 기준 흐름(2025→2026 정기주총 테마 증감)을 쓴다.
- 핫테마 = AI·로봇·데이터센터·방산·우주항공·디지털자산·원전·2차전지·반도체·양자·드론 (보고서 ④와 같은 정의).

[행동 규칙표]  H = 핫테마 개수, N = 추가 항목 수, 유가 = 유가증권시장
 ID | 조건                                                        | 점수        | 행동 문구(요지)
 T1 | 디지털자산 또는 전자지급 테마 + (결제·금융사 이름/항목에 결제·송금·지급) | 90          | 본업(금융보안) 관점: 보관·결제 보안·내부통제 요구 체크
 T2 | H ≥ 3                                                       | 60 + H×5    | '말만 추가' 위험 — 매출·투자 실적 확인 전엔 테마 뉴스에 휩쓸리지 말 것
 T3 | 유가 그리고 1 ≤ H ≤ 2 그리고 N < 10                          | 50 + H×5    | 실제 투자·수주 공시(신규시설투자·공급계약) 나오는지 확인
 T4 | 새 회사 중 AI 또는 SW·클라우드 테마 ≥ 3곳                     | 40          | 그 회사들 AI·자동화 수요 → 크롬확장·업무자동화 아이디어 메모
 T5 | N ≥ 10 그리고 H < 3                                         | 30 + N÷10   | 다각화인지 업종 전환인지 사업보고서 매출 구성으로 확인
 B1 | (새 공시 적음) 보고서 기준                                  | -           | 보고서 상위 테마 대표 대형사의 투자·수주 공시 월 1회 확인
 B2 | (새 공시 적음) 보고서 기준                                  | -           | 핫테마 3개 이상 회사 비율 → 테마 뉴스 주의
 B3 | (새 공시 적음) 보고서 기준                                  | -           | 결제사 디지털자산 명문화 → 본업(금융보안) 규정 변화 체크
 점수 높은 순 3개, 같은 회사는 한 번만, 같은 규칙(T2·T3·T5)은 회사 2곳까지 묶어서 한 줄. 같은 데이터면 같은 결과.
 매수·매도 권유 문구는 쓰지 않는다.
"""
import argparse, json, os, re, sys
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [4] 기업 신사업(DART)"
MIN_NEW = 3
HOT = ["AI(인공지능)", "로봇", "데이터센터", "방산", "우주항공", "디지털자산·블록체인·STO(스테이블코인)",
       "원전·원자력", "2차전지·배터리", "반도체", "양자", "드론·UAM"]
SHORT = {"AI(인공지능)": "AI", "디지털자산·블록체인·STO(스테이블코인)": "디지털자산", "클라우드·SW·빅데이터": "SW·클라우드",
         "2차전지·배터리": "2차전지", "신재생·에너지·전력": "에너지·전력", "바이오·헬스케어": "바이오",
         "원전·원자력": "원전", "전자지급·결제(PG·선불)": "전자결제", "희토류·핵심광물·소재": "희토류·광물",
         "모빌리티·전기차·자율주행": "모빌리티", "엔터·콘텐츠·게임": "콘텐츠", "부동산·임대·건설": "부동산·건설",
         "식품·농업·외식": "식품·외식", "화장품·뷰티": "뷰티"}
FIN_NAME = re.compile(r"결제|페이|카드|은행|증권|금융|캐피탈|KCP|이니시스|정보통신|핀테크|코나아이|인증|웹케시|다날|갤럭시아", re.I)
FIN_ITEM = re.compile(r"결제|송금|지급|정산|보관|수탁|커스터디")


def iga(w):  # 받침 있으면 '이', 없으면 '가' (한글이 아니면 '이(가)')
    ch = w[-1]
    if not ("가" <= ch <= "힣"):
        return w + "이(가)"
    return w + ("이" if (ord(ch) - 0xAC00) % 28 else "가")


def nm(t):
    return SHORT.get(t, t)


def snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(root, d, "meta.json")))


def load(root, d):
    p = os.path.join(root, d)
    s = json.load(open(os.path.join(p, "summary.json"), encoding="utf-8"))
    m = json.load(open(os.path.join(p, "meta.json"), encoding="utf-8"))
    c = pd.read_csv(os.path.join(p, "new_cases.csv"), dtype=str, keep_default_na=False)
    if len(c):
        c["n_added"] = c["n_added"].astype(int); c["n_hot"] = c["n_hot"].astype(int)
        c["T"] = c["themes"].map(lambda x: [t for t in x.split(";") if t])
    else:
        c["T"] = []
    return s, m, c


def names(df, n=3):
    """유가증권 먼저, 같은 시장은 추가 항목 적은(본업 연관 가능성 큰) 순"""
    df = df.assign(_k=(df["market"] != "유가증권").astype(int)).sort_values(["_k", "n_added", "corp_name"])
    L = list(df["corp_name"])
    return "·".join(L[:n]) + (f" 외 {len(L) - n}" if len(L) > n else "")


def report_base():
    """보고서 기준값(읽기 전용)"""
    out = {}
    p = os.path.join(DATA, "theme_counts.csv")
    if os.path.exists(p):
        out["tc"] = pd.read_csv(p, encoding="utf-8-sig").set_index("theme")
    p = os.path.join(DATA, "summary_periods.csv")
    if os.path.exists(p):
        out["sp"] = pd.read_csv(p, encoding="utf-8-sig").set_index("period")
    p = os.path.join(DATA, "extra_hot_bulk_stats.csv")
    if os.path.exists(p):
        out["hb"] = pd.read_csv(p, encoding="utf-8-sig").set_index("period")
    return out


def tv(B, th, col):
    try:
        return int(B["tc"].loc[th, col])
    except Exception:
        return None


def flow_line(B):
    """2025→2026 정기주총 테마 증감(보고서 data 값)"""
    if "tc" not in B:
        return None
    seg = [f"{nm(t)} {tv(B, t, '2025H1reg')}→{tv(B, t, '2026H1reg')}" for t in ("로봇", "AI(인공지능)", "데이터센터", "방산")
           if tv(B, t, "2025H1reg") is not None]
    down = [t for t in HOT if (tv(B, t, "2026H1reg") or 0) < (tv(B, t, "2025H1reg") or 0)]
    s = "· 보고서 기준 2025→2026 정기주총 추가 회사: " + ", ".join(seg)
    if down:
        s += " / 줄어든 건 " + "·".join(f"{nm(t)}({tv(B, t, '2025H1reg')}→{tv(B, t, '2026H1reg')})" for t in down[:2])
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snaproot", default=os.path.join(DATA, "snapshots"))
    a = ap.parse_args()
    ds = snaps(a.snaproot)
    if not ds:
        print(f"{TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        sys.exit(1)
    cur = ds[-1]
    s, m, c = load(a.snaproot, cur)
    date = f"{cur[:4]}-{cur[4:6]}-{cur[6:]}"
    B = report_base()
    prev = ds[-2] if len(ds) >= 2 else None

    # 이전 스냅샷에서 이미 알린 회사 → 정정·재공고로 분리
    before = set()
    for d in ds[:-1]:
        before |= set(load(a.snaproot, d)[2]["corp_name"])
    fresh = c[~c["corp_name"].isin(before)] if len(c) else c
    again = len(c) - len(fresh)
    nf = len(fresh)
    few = nf < MIN_NEW

    def by_theme(df):
        cnt = {t: df[df["T"].map(lambda L: t in L)] for t in HOT + ["클라우드·SW·빅데이터"]} if len(df) else {}
        return {t: x for t, x in cnt.items() if len(x)}
    bt = by_theme(fresh)
    hot_rank = sorted((t for t in bt if t in HOT), key=lambda t: (-len(bt[t]), HOT.index(t)))

    # 🔄 무엇이 바뀌었나
    w = s["window"]
    changed = []
    if prev:
        pv = f"{prev[4:6]}/{prev[6:]}"
        head = f"· 지난번({pv}) 이후 새 소집공고·정관변경 공시 {s['notices_new']}건 → 사업목적을 새로 넣은 회사 {nf}곳"
    else:
        head = f"· 최근 {w['from'][5:7]}/{w['from'][8:]}~{w['to'][5:7]}/{w['to'][8:]} 소집공고·정관변경 공시 {s['notices_new']}건 → 사업목적을 새로 넣은 회사 {nf}곳"
    if again:
        head += f"(정정 등 재공고 {again}곳 별도)"
    changed.append(head)
    if not few and hot_rank:
        changed.append("· " + " / ".join(f"{nm(t)} 추가 {len(bt[t])}곳: {names(bt[t])}" for t in hot_rank[:2]))
        if prev:
            ps, _, pc = load(a.snaproot, prev)
            pt = ps.get("theme_counts", {})
            mv = [(t, pt.get(t, 0), len(bt.get(t, []))) for t in HOT if pt.get(t, 0) != len(bt.get(t, []))]
            mv.sort(key=lambda x: (-abs(x[2] - x[1]), HOT.index(x[0])))
            if mv:
                changed.append("· 지난 회차 대비 테마별 새 회사 수: " + ", ".join(f"{nm(t)} {p}→{q}" for t, p, q in mv[:3]))
        elif flow_line(B):
            changed.append(flow_line(B).replace("· 보고서 기준", "· 참고로 보고서 기준"))
    elif not few:
        changed.append("· 새로 넣은 사업목적은 핫테마(AI·로봇·데이터센터 등)와 무관한 업종 확장 위주")
    else:
        if nf:
            changed[0] += " (" + ", ".join(f"{r.corp_name}: {'·'.join(nm(t) for t in r.T[:3]) or '기타'}"
                                           for r in fresh.itertuples()) + ")"
        changed[0] += " → 새 공시가 적어 보고서 흐름으로 보면:"
        fl = flow_line(B)
        if fl:
            changed.append(fl)
        if "tc" in B:
            changed.append(f"· 정기주총 이후(4~10월)는 데이터센터 {tv(B, '데이터센터', '2025post')}→{tv(B, '데이터센터', '2026post')}곳, "
                           f"디지털자산 {tv(B, '디지털자산·블록체인·STO(스테이블코인)', '2025post')}→{tv(B, '디지털자산·블록체인·STO(스테이블코인)', '2026post')}곳(과열 후 식음)")
    changed = changed[:3]

    # 💡 무슨 의미 (규칙: 핫테마 3개 이상·10개 이상 대량 비율 ≥ 30% → 편승 경고 / 상위 테마가 AI 인프라 → 흐름 지속)
    meaning = []
    if not few:
        risky = fresh[(fresh["n_hot"] >= 3) | (fresh["n_added"] >= 10)]
        infra = [t for t in hot_rank[:2] if t in ("데이터센터", "로봇", "AI(인공지능)")]
        if infra:
            meaning.append(f"· {iga('·'.join(nm(t) for t in infra))} 여전히 상위 → 보고서의 'AI가 소프트웨어에서 데이터센터·로봇 같은 물리 인프라로' 흐름이 이어지는 중.")
        if len(risky) / nf >= 0.3:
            meaning.append(f"· 다만 {nf}곳 중 {len(risky)}곳이 핫테마 3개 이상 또는 10개 이상을 한꺼번에 넣었어요. 정관 추가는 '해도 된다'는 근거일 뿐 사업 시작 신호가 아니에요.")
        if not meaning:
            meaning.append("· 대부분 본업 주변으로 넓히는 추가예요. 실제 사업 착수는 이후 투자·계약 공시로 따로 확인해야 해요.")
    else:
        meaning.append("· 기업들이 'AI 인프라(데이터센터·전력)'와 '피지컬 AI(로봇)'로 신사업 근거를 옮기는 중. 2차전지는 ESS·전력 인프라로 바뀌는 흐름.")
        meaning.append("· 정관 추가는 '해도 된다'는 근거일 뿐이에요. 금감원 점검에서 신사업 추가사의 31%는 실적이 전무했어요.")
    meaning = meaning[:2]

    # ✅ 내가 할 일 (규칙표 T1~T5 / B1~B3)
    cands = []
    for r in fresh.itertuples() if not few else []:
        T = r.T
        if any(t in T for t in ("디지털자산·블록체인·STO(스테이블코인)", "전자지급·결제(PG·선불)")) and (
                FIN_NAME.search(r.corp_name) or "전자지급·결제(PG·선불)" in T or FIN_ITEM.search(r.added_items)):
            cands.append((90, "T1", r.corp_name, f"{iga(r.corp_name)} 디지털자산·결제 사업 추가 → 본업(금융보안) 관점에서 보관·결제 보안·내부통제 요구(전자금융·가상자산 규정)가 어떻게 바뀌는지 체크"))
        if r.n_hot >= 3:
            cands.append((60 + r.n_hot * 5, "T2", r.corp_name, f"핫테마 {r.n_hot}개"))
        elif r.market == "유가증권" and 1 <= r.n_hot <= 2 and r.n_added < 10:
            hot_t = [nm(t) for t in T if t in HOT]
            cands.append((50 + r.n_hot * 5, "T3", r.corp_name, "·".join(hot_t)))
        if r.n_added >= 10 and r.n_hot < 3:
            cands.append((30 + r.n_added / 10, "T5", r.corp_name, f"{r.n_added}개"))
    if not few:
        ai_sw = fresh[fresh["T"].map(lambda L: "AI(인공지능)" in L or "클라우드·SW·빅데이터" in L)]
        if len(ai_sw) >= 3:
            cands.append((40, "T4", "", f"AI·SW 사업을 넣은 회사 {len(ai_sw)}곳({names(ai_sw, 2)}) → 이 회사들의 AI 서비스·채용 공고에서 업무자동화(크롬확장·RPA) 수요 메모"))
    cands.sort(key=lambda x: (-x[0], x[1], x[2]))
    # 같은 규칙은 회사 2곳까지 한 줄로 묶음
    groups, order = {}, []
    for sc, rid, corp, txt in cands:
        key = rid if rid in ("T2", "T3", "T5") else f"{rid}:{corp}"
        if key not in groups:
            groups[key] = []; order.append((sc, key, rid))
        if len(groups[key]) < 2:
            groups[key].append((corp, txt))
    todo, used = [], set()
    for sc, key, rid in order:
        g = [(cp, t) for cp, t in groups[key] if cp not in used]
        if not g or len(todo) >= 3:
            continue
        used |= {cp for cp, _ in g}
        lab = ", ".join(f"{cp}({t})" for cp, t in g)
        if rid == "T2":
            todo.append(f"{lab} → '말만 추가' 위험 — 매출·투자 실적 확인 전엔 테마 뉴스에 휩쓸리지 말 것")
        elif rid == "T3":
            todo.append(f"{lab} 대형사 추가 → 실제 투자·수주 공시(신규시설투자·공급계약) 나오는지 DART 알림으로 확인")
        elif rid == "T5":
            todo.append(f"{lab} 한꺼번에 추가 → 다각화인지 업종 전환인지 다음 사업보고서 매출 구성으로 확인")
        else:
            todo.append(g[0][1])
    if not todo:
        hb = B.get("hb")
        h3 = f"{hb.loc['2026post', 'hot3%']:.1f}%" if hb is not None and "2026post" in hb.index else "약 11%"
        todo = ["보고서 상위 테마 대형사(LG유플러스·LS일렉트릭 데이터센터, 코웨이 로봇) → 실제 투자·수주 공시 나오는지 월 1회 확인",
                f"올해 4~10월 사업목적 추가사 {h3}가 핫테마 3개 이상 → '말만 추가' 위험, 실적 확인 전엔 테마 뉴스에 휩쓸리지 말 것",
                "나이스정보통신·NHN KCP 등 결제사의 디지털자산 명문화 → 본업(금융보안) 관점에서 스테이블코인 결제 보안 규정 변화 체크"]
    todo = [f"· {t}" for t in todo[:3]]

    # 📊 근거
    tcnt = s.get("theme_counts", {})
    mk = s.get("by_market", {})
    ev = [f"· 이번 회차({s['window']['from'][5:]}~{s['window']['to'][5:]}, {s['route']}): 공시 {s['notices_listed']}건 중 정관변경 {s['aoi_change_corps']}곳, "
          f"사업목적 추가 {s['purpose_added_corps']}곳(" + "·".join(f"{k} {v}" for k, v in mk.items()) + ")"]
    if tcnt:
        ev.append("· 추가 테마 상위: " + " · ".join(f"{nm(k)} {v}" for k, v in list(tcnt.items())[:5]))
    if s.get("hot3_corps") or s.get("bulk10_corps"):
        ev.append(f"· 핫테마 3개+: {'·'.join(s['hot3_corps'][:4]) or '없음'} / 10개+ 대량: {'·'.join(s['bulk10_corps'][:4]) or '없음'}")
    if "sp" in B and not few:
        sp = B["sp"]
        ev.append(f"· 보고서 기준 추가 회사: 2026 정기 {int(sp.loc['2026H1reg', 'purpose_added_corps'])}곳({sp.loc['2026H1reg', 'purpose_added_ratio']}%) · "
                  f"4~10월 {int(sp.loc['2026post', 'purpose_added_corps'])}곳")
    elif "tc" in B:
        ev.append(f"· 보고서 기준 4~10월(2025→2026): 로봇 {tv(B, '로봇', '2025post')}→{tv(B, '로봇', '2026post')} · AI {tv(B, 'AI(인공지능)', '2025post')}→{tv(B, 'AI(인공지능)', '2026post')}")
    foot = "※ 주총 소집공고 기준(가결 전). 투자 권유 아님"
    print(render(f"{TITLE} ({date})", changed, meaning, todo, ev, foot))


def render(head, changed, meaning, todo, ev, foot):
    def join(evl):
        return "\n".join([head, "🔄 무엇이 바뀌었나", *changed, "💡 무슨 의미", *meaning, "✅ 내가 할 일", *todo,
                          "📊 근거", *evl, foot])
    evl = list(ev)
    out = join(evl)
    while len(out) > LIMIT and len(evl) > 1:  # 근거 줄부터 줄임
        evl.pop(); out = join(evl)
    return out if len(out) <= LIMIT else out[:LIMIT - 1] + "…"


if __name__ == "__main__":
    main()
