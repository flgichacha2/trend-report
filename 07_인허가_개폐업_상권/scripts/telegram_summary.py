# -*- coding: utf-8 -*-
"""
텔레그램용 '인사이트 중심' 요약 [7] 동네 가게 개·폐업 (네트워크 사용 안 함, 일반 텍스트, 1,500자 이내)
  python -I scripts\\telegram_summary.py [--snaproot 다른_스냅샷_폴더]   # --snaproot 는 테스트용

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 직전 1개,
         data/processed/interest_area_periods.csv(보고서 12개월 기준값, 읽기 전용). 쓰는 것: 없음(stdout 만).
대상: API 업종(일반음식점·휴게음식점(카페 등)·제과점) 4개 지역. 개업 = 팝업·한시적 상호 제외, 폐업 = 60일 안 폐업·팝업 제외
      (daily_update.py 의 '실질' 기준). 그 밖의 업종(미용·헬스 등)은 주 1회 파일 기준으로 보조 사용.

출력: 🔄 무엇이 바뀌었나 → 💡 무슨 의미 → ✅ 내가 할 일 → 📊 근거
- 변화 기준: ① 직전 스냅샷 대비 새로 잡힌 개업·폐업 ② 직전이 없거나 '변화 미미'(새 개업+폐업 합계 < 5)면
  보고서 12개월 추이(최근12M vs 직전12M 폐업/개업 배율)와 최근 30일 속도(12개월 월평균 대비)를 쓴다.
  (12개월 '실질 개업'은 60일 안 폐업까지 뺀 값이라 30일 값과 정의가 조금 달라 '대략' 비교다.)

[행동 규칙표]  O/C = 최근 30일 개업/폐업, R12 = 최근 12개월 폐업÷개업, pace = 30일 개업 ÷ 12개월 월평균 개업
 ID | 조건                                               | 점수                     | 행동 문구(요지)
 P1 | (직전 대비) 새 폐업 ≥ 5 그리고 새 폐업 > 새 개업      | 100 + 새 폐업            | 문 닫은 업종 확인, 공실 나오는지 지켜보기
 P2 | (직전 대비) 새 개업 ≥ 5 그리고 새 개업 > 새 폐업      | 100 + 새 개업            | 새로 연 업종 메모
 S1 | C > O 그리고 R12 > 1                                | 20 + (C−O)÷O×100         | 폐업>개업 지속 → 공실 상가 임대 조건(보증금·월세) 확인
 S2 | C > O 그리고 R12 ≤ 1                                | (C−O)÷O×100              | 최근 한 달만 폐업 우세 → 일시적인지 다음 주 재확인
 S3 | O ≥ 1.3×C 그리고 O ≥ 10                             | min(100, (O−C)÷C×50)     | 개업 우세 → 많이 연 업종 메모(R12>1 이면 '일시적인지 지켜보기' 덧붙임)
 S4 | pace ≥ 1.3 (S3 이 없을 때)                          | (pace−1)×50              | 개업 속도 빨라짐 → 새 가게 위치(신축 상가 등) 확인
 S5 | 팝업 개업 ≥ 전체 개업의 40% 그리고 팝업 ≥ 20         | 15                       | 팝업 많음 → 팝업 운영(예약·재고) 자동화 도구 수요 메모
 S6 | (주 1회 파일) 한 업종 폐업 − 개업 ≥ 5                | 12                       | 그 업종 공실·매물 나오는지 확인
 S7 | C ≤ O 이고 R12 ≥ 1.2 이고 R12 − 직전12M ≥ 0.1         | 10 + 증가폭×100          | 1년 새 폐업 배율 상승 → 공실·임대 매물 시세 확인
 S0 | 해당 없음                                           | -                        | 큰 변화 없음 → 관심 상권 주 1회 확인
 상위 점수부터 3개, 같은 지역은 한 번만(지역이 모자라면 허용). 같은 데이터면 같은 결과.
"""
import argparse, json, os, re, sys
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [7] 동네 가게 개·폐업"
AREAS = [("서울 강남구", "강남"), ("성남 분당구", "분당"), ("인천 영종(옛 중구)", "영종"), ("제주 서귀포시", "서귀포")]
FOOD = ("일반음식점", "휴게음식점", "제과점")
SKIP_TYPE = {"기타", "기타 휴게음식점", ""}
RENAME = {"제과점영업": "제과점", "백화점": "백화점 매장", "일반조리판매": "조리판매", "호프/통닭": "호프·치킨",
          "정종/대포집/소주방": "주점", "까페": "카페", "외국음식전문점(인도,태국등)": "외국음식", "식육(숯불구이)": "고깃집"}
FNAMES = {"beauty_salons": "미용실", "fitness_centers": "헬스장", "food_vending_machines": "자판기", "lodgings": "숙박",
          "animal_hospitals": "동물병원", "pc_bangs": "PC방", "laundries": "세탁소", "karaoke_rooms": "노래방",
          "pet_grooming": "애견미용", "animal_boarding": "애견호텔", "martial_arts_dojo": "체육도장"}
POPUP = r"한시적|팝업|(?i:pop-?up)"


def snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(root, d, "meta.json")))


def load(root, d):
    s = json.load(open(os.path.join(root, d, "summary.json"), encoding="utf-8"))
    e = pd.read_csv(os.path.join(root, d, "api_events.csv"), dtype=str, keep_default_na=False)
    return s, e


def types(lst, n=2):
    out = []
    for _, t, v in lst:
        if t in SKIP_TYPE:
            continue
        out.append(f"{RENAME.get(t, t)} {v}")
        if len(out) == n:
            break
    return ", ".join(out)


def ev_sets(e, ref, days):
    """api_events에서 최근 days일 실질 개업/폐업 {(area, slug, mng_no)}"""
    a = (pd.Timestamp(ref) - pd.Timedelta(days=days - 1)).strftime("%Y-%m-%d")
    pop = e["name"].str.contains(POPUP)
    short = (pd.to_datetime(e["clo"], errors="coerce") - pd.to_datetime(e["lic"], errors="coerce")).dt.days.le(60)
    o = e[(e["lic"] >= a) & ~pop]
    c = e[(e["clo"] >= a) & e["status"].eq("폐업") & ~pop & ~short]
    return set(zip(o["area"], o["slug"], o["mng_no"])), set(zip(c["area"], c["slug"], c["mng_no"]))


def base12():
    """보고서 12개월 기준값: 지역별 음식 3업종 합 {area: (최근12M 개업, 폐업, 직전12M 개업, 폐업)}"""
    p = os.path.join(BASE, "data", "processed", "interest_area_periods.csv")
    if not os.path.exists(p):
        return {}
    d = pd.read_csv(p)
    d = d[d["업종"].isin(FOOD)].groupby("관심지역")[["최근12M_실질개업", "최근12M_실질폐업", "직전12M_실질개업", "직전12M_실질폐업"]].sum()
    return {a: tuple(int(x) for x in r) for a, r in d.iterrows()}


def eun(w):  # 받침 있으면 '은', 없으면 '는'
    c = w[-1]
    return w + ("은" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "는")


def sg(x):
    return ("+" if x > 0 else "") + f"{x:.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snaproot", default=os.path.join(BASE, "data", "snapshots"))
    a = ap.parse_args()
    ds = snaps(a.snaproot)
    if not ds:
        print(f"{TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        sys.exit(1)
    cur = ds[-1]
    s, e = load(a.snaproot, cur)
    days = s["days"]; api = s["api"]
    B = base12()
    SH = dict(AREAS)
    A = {}
    for key, sh in AREAS:
        r = api.get(key)
        if not r:
            continue
        b = B.get(key)
        m = {"O": r["open_real"], "C": r["close_real"], "pop": r.get("popup_open", 0), "r": r}
        if b and b[0]:
            m["R12"] = b[1] / b[0]; m["R12p"] = (b[3] / b[2]) if b[2] else None
            m["paceO"] = r["open_real"] / (b[0] / 12 * days / 30)
            m["paceC"] = r["close_real"] / (b[1] / 12 * days / 30) if b[1] else None
        A[key] = m

    prev = ds[-2] if len(ds) >= 2 else None
    changed, cands = [], []
    minor = True
    if prev:
        ps, pe = load(a.snaproot, prev)
        co, cc = ev_sets(e, s["date"], days)
        po, pc = ev_sets(pe, s["date"], days + (pd.Timestamp(s["date"]) - pd.Timestamp(ps["date"])).days)
        no, nc = co - po, cc - pc
        per = {k: (sum(1 for x in no if x[0] == k), sum(1 for x in nc if x[0] == k)) for k in A}
        minor = len(no) + len(nc) < 5
        pv = f"{prev[4:6]}/{prev[6:]}"
        order = sorted(A, key=lambda k: (-(per[k][0] + per[k][1]), k))
        changed.append(f"· 지난번({pv}) 이후 새로 잡힌 개업 {len(no)}곳 · 폐업 {len(nc)}곳 ("
                       + (" · ".join(f"{SH[k]} +{per[k][0]}/-{per[k][1]}" for k in order if sum(per[k])) or "변화 없음") + ")")
        mv = []
        for k in A:
            pr = ps["api"].get(k)
            if pr:
                mv.append((abs(A[k]["O"] - pr["open_real"]) + abs(A[k]["C"] - pr["close_real"]), k, pr))
        mv.sort(key=lambda x: (-x[0], x[1]))
        if mv and mv[0][0] >= 3:
            _, k, pr = mv[0]
            changed.append(f"· {days}일 합계가 가장 많이 바뀐 곳: {SH[k]} 개업 {pr['open_real']}→{A[k]['O']}, 폐업 {pr['close_real']}→{A[k]['C']}")
        def main_type(keys, k):
            x = e[[t in keys and t[0] == k for t in zip(e["area"], e["slug"], e["mng_no"])]]["업태"].map(lambda t: RENAME.get(t, t))
            x = x[~x.isin(SKIP_TYPE)].value_counts()
            return f"(주로 {sorted(x[x == x.max()].index)[0]})" if len(x) else ""
        for k, (n_o, n_c) in per.items():
            if n_c >= 5 and n_c > n_o:
                cands.append((100 + n_c, "P1", k, f"{SH[k]} 지난번 이후 폐업 {n_c}곳{main_type(nc, k)} → 문 닫은 자리 공실로 나오는지 지켜보기"))
            if n_o >= 5 and n_o > n_c:
                cands.append((100 + n_o, "P2", k, f"{SH[k]} 지난번 이후 개업 {n_o}곳{main_type(no, k)} → 업종·위치 메모(입점·창업 아이디어용)"))
        if minor:
            changed = [changed[0] + " → 큰 변화 없음, 12개월 흐름으로 보면:"]
    if not prev or minor:
        net = sorted(A, key=lambda k: (-(A[k]["O"] - A[k]["C"]), k))
        changed.append(f"· 최근 {days}일 개업−폐업: " + " · ".join(f"{SH[k]} {sg(A[k]['O'] - A[k]['C'])}" for k in net))
        r12 = [k for k in A if A[k].get("R12") is not None]
        if r12:
            r12.sort(key=lambda k: (-abs(A[k]["R12"] - (A[k]["R12p"] or A[k]["R12"])), k))
            changed.append("· 12개월 폐업÷개업(직전→최근): " + " · ".join(
                f"{SH[k]} {A[k]['R12p']:.2f}→{A[k]['R12']:.2f}" if A[k]["R12p"] else f"{SH[k]} {A[k]['R12']:.2f}" for k in r12))
    changed = changed[:3]

    # 💡 의미 (규칙: 12개월 배율 >1 & 30일 C>O → 축소 상권 / 개업 우세 → 확장 상권)
    shrink = [k for k in A if A[k]["C"] > A[k]["O"] and A[k].get("R12", 0) > 1]
    grow = [k for k in A if A[k]["O"] > A[k]["C"] and A[k].get("R12", 0) <= 1]
    turn = [k for k in A if A[k]["O"] > A[k]["C"] and A[k].get("R12", 0) > 1]
    seg = []
    if shrink:
        seg.append(f"{'·'.join(SH[k] for k in shrink)}: 문 닫는 가게가 더 많은 흐름이 1년째 이어지는 중")
    if grow:
        seg.append(f"{'·'.join(SH[k] for k in grow)}: 1년 내내 여는 가게가 더 많은 확장 상권")
    if turn:
        seg.append(f"{'·'.join(SH[k] for k in turn)}: 1년 기준 폐업 우세인데 최근 한 달은 개업이 많음(일시적일 수 있음)")
    meaning = ["· " + (" / ".join(seg) if seg else f"4개 지역 모두 최근 {days}일 개업과 폐업이 비슷해요.")]
    fast = [k for k in A if A[k].get("paceO", 0) >= 1.3]
    if fast:
        meaning.append(f"· {eun('·'.join(SH[k] for k in fast))} 개업 속도가 12개월 월평균보다 빨라요(계절·행사 영향일 수 있음).")

    # ✅ 할 일 (규칙표 S1~S6)
    for k, m in A.items():
        O, C, sh = m["O"], m["C"], SH[k]
        R12 = m.get("R12")
        if C > O and R12 and R12 > 1:
            cands.append((20 + (C - O) / max(O, 1) * 100, "S1", k,
                          f"{sh} 폐업>개업 지속({C}>{O}, 12개월 {R12:.2f}배) → 공실 상가 임대 조건(보증금·월세) 확인해볼 것"))
        elif C > O:
            cands.append(((C - O) / max(O, 1) * 100, "S2", k, f"{sh} 최근 한 달만 폐업 우세({C}>{O}) → 일시적인지 다음 주 다시 보기"))
        tp = types(m["r"].get("open_by_type", []))
        if O >= 1.3 * C and O >= 10:
            warn = " (1년 기준은 폐업 우세라 일시적인지 지켜보기)" if R12 and R12 > 1 else ""
            cands.append((min(100, (O - C) / max(C, 1) * 50), "S3", k,
                          f"{sh} 개업 우세({O}>{C}) → 많이 연 업종 메모" + (f": {tp}" if tp else "") + warn))
        elif m.get("paceO", 0) >= 1.3:
            cands.append(((m["paceO"] - 1) * 50, "S4", k, f"{sh} 개업 속도 월평균 대비 {sg((m['paceO'] - 1) * 100)}% → 새 가게 위치(신축 상가 등) 확인"))
        if R12 and m.get("R12p") and R12 >= 1.2 and R12 - m["R12p"] >= 0.1 and not C > O:
            cands.append((10 + (R12 - m["R12p"]) * 100, "S7", k,
                          f"{sh} 1년 새 폐업÷개업 {m['R12p']:.2f}→{R12:.2f} → 상권 축소 흐름, 공실·임대 매물 시세 확인"))
        if m["pop"] >= 20 and m["pop"] >= 0.4 * (O + m["pop"]):
            cands.append((15, "S5", k, f"{sh} 팝업 {m['pop']}곳 → 팝업 운영(예약·재고) 자동화 도구 수요 메모"))
    fasof = None
    for slug, v in (s.get("files") or {}).items():
        fasof = v.get("asof") or fasof
        for k, x in v.get("areas", {}).items():
            if k in A and x["close_real"] - x["open_real"] >= 5:
                cands.append((12, "S6", k, f"{SH[k]} {FNAMES.get(slug, slug)} 폐업 {x['close_real']} > 개업 {x['open_real']} → 그 업종 공실·매물 나오는지 확인"))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    todo, used = [], set()
    for sc, rid, k, txt in cands:
        if k not in used and len(todo) < 3:
            todo.append(txt); used.add(k)
    for sc, rid, k, txt in cands:
        if len(todo) < 2 and txt not in todo:
            todo.append(txt)
    if not todo:
        todo = ["큰 변화 없음 → 관심 상권 주 1회 확인"]
    todo = [f"· {t}" for t in todo]

    # 📊 근거
    ev = []
    for k in sorted(A, key=lambda k: (-abs(A[k]["O"] - A[k]["C"]), k)):
        m = A[k]
        seg = f"· {SH[k]}: 개업 {m['O']}·폐업 {m['C']}"
        if m["pop"]:
            seg += f"(팝업 {m['pop']} 별도)"
        if m.get("R12") is not None:
            seg += f" · 12개월 폐업÷개업 {m['R12']:.2f}"
        tp = types(m["r"].get("open_by_type", []), 1)
        if tp:
            seg += f" · 많이 연: {tp}"
        ev.append(seg)
    fs = []
    for slug, v in (s.get("files") or {}).items():
        o = sum(x["open_real"] for x in v["areas"].values()); c = sum(x["close_real"] for x in v["areas"].values())
        if o + c:
            fs.append((o + c, slug, o, c))
    if fs and fasof:
        fs.sort(key=lambda x: (-x[0], x[1]))
        ev.append(f"· 기타 업종(4곳 합, {fasof[5:7]}/{fasof[8:10]} 파일): " + ", ".join(f"{FNAMES.get(sl, sl)} +{o}/-{c}" for _, sl, o, c in fs[:2]))
    foot = f"※ 최근 {days}일 음식점·카페·제과점, 팝업·60일 안 폐업 제외"
    print(render(f"{TITLE} ({cur[:4]}-{cur[4:6]}-{cur[6:]})", changed, meaning, todo, ev, foot))


def render(head, changed, meaning, todo, ev, foot):
    def join(evl):
        return "\n".join([head, "🔄 무엇이 바뀌었나", *changed, "💡 무슨 의미", *meaning, "✅ 내가 할 일", *todo,
                          "📊 근거", *evl, foot])
    evl = list(ev)
    out = join(evl)
    while len(out) > LIMIT and evl:  # 근거 줄부터 줄임
        evl.pop(); out = join(evl)
    return out if len(out) <= LIMIT else out[:LIMIT - 1] + "…"


if __name__ == "__main__":
    main()
