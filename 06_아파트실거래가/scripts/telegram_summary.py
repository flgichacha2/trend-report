# -*- coding: utf-8 -*-
"""
텔레그램용 '인사이트 중심' 요약 [6] 관심지역 아파트 (네트워크 사용 안 함, 일반 텍스트, 1,500자 이내)
  python -I scripts\\telegram_summary.py [--snaproot 다른_스냅샷_폴더]   # --snaproot 는 테스트용

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 직전 1개. 쓰는 것: 없음(stdout 만).
매수·매도 권유를 하지 않는다. 행동 문구는 '확인해볼 것 / 지켜볼 것' 수준으로만 쓴다.

출력: 🔄 무엇이 바뀌었나 → 💡 무슨 의미 → ✅ 내가 할 일 → 📊 근거(지역별 한 줄)
- 변화 기준: ① 직전 스냅샷 대비(새로 신고된 거래·새 신고가·새 계약해제·신고가 비율 변화)
  ② 직전이 없거나 '변화 미미'(새 거래 합계 < 5 이고 새 신고가 0, 신고가 비율 변화 모두 < 5%p)면
     summary.json 의 전년 동기(최근 3개월 vs 1년 전 같은 3개월) 대비 동일단지 가격·거래량.
- 신고가 비율 = 7월 이후(창 시작월) 신고가 건수 ÷ 같은 기간 거래 건수. 최근 계약분은 신고기한(30일)이 남아
  거래 '건수'가 덜 잡혀 있음 → 거래량 비교는 summary 의 '최근 3개월'(신고가 거의 끝난 달까지) 기준을 쓴다.

[행동 규칙표]  r = 지역, NH = 신고가 비율(%), YoY = 동일단지 가격 전년 대비(%), VOL = 거래량 전년 대비(%)
 ID | 조건                                                   | 점수              | 행동 문구(요지)
 C1 | (직전 대비) 새 신고가 ≥ 3건                             | 100 + 5×건수      | 그 단지 호가·최근 실거래 비교
 C2 | (직전 대비) 새 계약해제 ≥ 3건                           | 100 + 5×건수      | 과열·분쟁 신호인지 지켜보기
 C3 | (직전 대비) 신고가 비율 |Δ| ≥ 5%p                       | 100 + 3×|Δ|       | 오름: 호가 따라 오르는지 확인 / 내림: 둔화인지 지켜보기
 C4 | (직전 대비) 동일단지 전년比 |Δ| ≥ 3%p                   | 100 + 3×|Δ|       | 가격 흐름 바뀌는지 다음 주 재확인
 H1 | NH ≥ 30%                                               | NH                | 관심 단지 호가와 실거래 차이 확인 + 지역별 체크(아래 EXTRA)
 H2 | 10%↓ 거래 ≥ 3건 그리고 10%↓ ≥ 신고가                     | 3×10%↓비율        | 저층·직거래인지 확인, 급매 흐름인지 지켜보기
 H4 | VOL ≤ -40% (전년 동기 거래 ≥ 30건)                       | |VOL|÷2           | 거래가 적어 한두 건이 시세 좌우 → 여러 중개소 호가 비교
 H5 | VOL ≥ +10% 그리고 |YoY| ≤ 3%                            | 20                | 거래는 늘고 가격은 제자리 → 미분양·신규 분양가와 비교
 H6 | 7월 이후 거래 < 20건                                    | 10                | 표본 적음 → 개별 매물·지역 일정 직접 확인
 H3 | |YoY| ≤ 3% 그리고 7월 이후 거래 ≥ 50건                  | 5                 | 가격 정체 → 서두르지 말고 월 1회 실거래만 점검
 상위 점수부터 3개, 같은 지역은 한 번만(지역이 모자라면 허용). 같은 데이터면 같은 결과.
"""
import argparse, json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [6] 관심지역 아파트"
SHOW = [("jeju_edu", "제주교육도시"), ("yeongjong", "영종"), ("yatap", "야탑"), ("pangyo", "판교"), ("gangnam", "강남")]
sys.path.insert(0, str(HERE))
from common import REGIONS  # 관심지역 정의만 사용(기존 폴더라 생성되는 것 없음)
RDEF = {r["key"]: (r["sgg"], r["emd"]) for r in REGIONS}
# H1 지역별 추가 체크(보고서 ③ 특이사항 근거)
EXTRA = {"yatap": "재건축 선도지구(목련마을) 일정 체크", "pangyo": "토허·대출(LTV) 조건 다시 확인",
         "gangnam": "토허·세제개편안 국회 일정 체크", "yeongjong": "미분양·신규 분양가와 비교",
         "jeju_edu": "국제학교(FSAA 2028 개교) 일정 체크"}


def snaps(root):
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and (p / "meta.json").exists())


def won(v):
    v = int(v)
    return (f"{v / 10000:.2f}".rstrip("0").rstrip(".") + "억") if v >= 10000 else f"{v:,}만"


def sg(x, nd=0):
    return ("+" if x > 0 else "") + f"{x:.{nd}f}"


def rd_csv(root, d, name):
    try:
        return pd.read_csv(root / d / name, dtype={"sgg_cd": str, "ym": str, "ri": str, "cancel_date": str})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def region_rows(w, key):
    if w.empty:
        return w
    sgg, emd = RDEF[key]
    x = w[w["sgg_cd"] == sgg]
    return x[x["emd"].isin(emd)] if emd else x


def tkey(x):
    if x.empty:
        return set()
    return set(zip(x["sgg_cd"], x["apt"], x["area_m2"].round(2), x["ym"], x["day"], x["price_manwon"], x["floor"].fillna(-1)))


def hkey(x):
    return set(zip(x["계약일"], x["단지"], x["전용㎡"].round(2), x["거래가(만원)"])) if len(x) else set()


def metrics(s, key):
    r = s.get(key)
    if not r:
        return None
    p = r["period"]; pr = r["paired"]
    v_now, v_ly = p["최근3개월"]["거래량"], p["전년동기"]["거래량"]
    yoy = pr["전년동기대비"]["중앙변화율(%)"]
    yoy = None if yoy is None or yoy != yoy else float(yoy)
    return {"n": r["recent_trades"], "nh": r["newhigh_recent"], "dr": r["drop10_recent"],
            "nhr": (r["newhigh_recent"] / r["recent_trades"] * 100) if r["recent_trades"] else 0.0,
            "yoy": yoy, "yoy_pairs": int(pr["전년동기대비"]["비교쌍"] or 0),
            "vol": (v_now / v_ly - 1) * 100 if v_ly else None, "v_now": v_now, "v_ly": v_ly,
            "ppy": p["최근3개월"]["중위평당(만원)"], "per": p["최근3개월"]["기간"]}


def eun(w):  # 받침 있으면 '은', 없으면 '는'
    c = w[-1]
    return w + ("은" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "는")


def per_label(per):  # "2026-06~2026-08" -> "6~8월"
    a, b = per.split("~")
    return f"{int(a[5:7])}~{int(b[5:7])}월"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snaproot", default=str(HERE.parent / "data" / "snapshots"))
    a = ap.parse_args()
    root = Path(a.snaproot)
    ds = snaps(root)
    if not ds:
        print(f"{TITLE}\n아직 수집된 스냅샷이 없어요. daily_update.py를 먼저 실행해 주세요.")
        sys.exit(1)
    cur = ds[-1]
    meta = json.loads((root / cur / "meta.json").read_text(encoding="utf-8"))
    s = json.loads((root / cur / "summary.json").read_text(encoding="utf-8"))
    since = f"{int(min(meta['window_months'])[4:])}월"
    M = {k: metrics(s, k) for k, _ in SHOW}
    M = {k: v for k, v in M.items() if v}
    NAME = dict(SHOW)
    plabel = per_label(next(iter(M.values()))["per"]) if M else ""
    prev = ds[-2] if len(ds) >= 2 else None

    changed, cands = [], []
    minor = True
    if prev:
        ps = json.loads((root / prev / "summary.json").read_text(encoding="utf-8"))
        pmeta = json.loads((root / prev / "meta.json").read_text(encoding="utf-8"))
        PM = {k: metrics(ps, k) for k in M}
        w, pw = rd_csv(root, cur, "trades_window.csv"), rd_csv(root, prev, "trades_window.csv")
        pmin = min(pmeta["window_months"])
        news, highs, cancs, ratio_moves = {}, {}, {}, {}
        for key in M:
            x = region_rows(w, key); y = region_rows(pw, key)
            x = x[x["ym"] >= pmin] if not x.empty else x
            news[key] = len(tkey(x) - tkey(y))
            cx = x[x["cancel_date"].fillna("").str.strip().ne("")] if not x.empty else x
            cy = y[y["cancel_date"].fillna("").str.strip().ne("")] if not y.empty else y
            cancs[key] = len(tkey(cx) - tkey(cy))
            h1, h0 = rd_csv(root, cur, f"newhigh_{key}.csv"), rd_csv(root, prev, f"newhigh_{key}.csv")
            nk = hkey(h1) - hkey(h0)
            if nk:
                top = h1[[k in nk for k in zip(h1["계약일"], h1["단지"], h1["전용㎡"].round(2), h1["거래가(만원)"])]]
                top = top.sort_values(["상승률(%)", "단지"], ascending=[False, True]).iloc[0]
                highs[key] = (len(nk), f"{top['단지']} {round(top['전용㎡'])}㎡ {won(top['거래가(만원)'])}")
            if PM.get(key):
                ratio_moves[key] = (PM[key]["nhr"], M[key]["nhr"])
                py, cy_ = PM[key]["yoy"], M[key]["yoy"]
                if py is not None and cy_ is not None and abs(cy_ - py) >= 3:
                    cands.append((100 + 3 * abs(cy_ - py), "C4", key,
                                  f"{NAME[key]} 동일단지 전년比 {sg(py, 1)}→{sg(cy_, 1)}% → 흐름이 바뀌는지 다음 주 다시 확인"))
        big_ratio = {k: v for k, v in ratio_moves.items() if abs(v[1] - v[0]) >= 5}
        minor = sum(news.values()) < 5 and not highs and not big_ratio
        pv = f"{prev[4:6]}/{prev[6:]}"
        order = sorted(M, key=lambda k: (-news[k], k))
        nz = [k for k in order if news[k]]
        changed.append(f"· 지난번({pv}) 이후 새로 신고된 거래: "
                       + (" · ".join(f"{NAME[k]} +{news[k]}" for k in nz) if nz else "없음"))
        if highs:
            hs = sorted(highs.items(), key=lambda kv: (-kv[1][0], kv[0]))
            changed.append("· 새 신고가: " + " / ".join(f"{NAME[k]} {n}건(예: {ex})" for k, (n, ex) in hs[:2]))
        if big_ratio:
            k, (p0, p1) = max(big_ratio.items(), key=lambda kv: abs(kv[1][1] - kv[1][0]))
            changed.append(f"· 신고가 비율 {NAME[k]} {p0:.0f}→{p1:.0f}%"
                           + (f", 새 계약해제 {sum(cancs.values())}건" if sum(cancs.values()) else ""))
        elif sum(cancs.values()) and len(changed) < 3:
            changed.append(f"· 새로 접수된 계약 해제(취소) {sum(cancs.values())}건")
        for k in M:
            if k in highs and highs[k][0] >= 3:
                cands.append((100 + 5 * highs[k][0], "C1", k, f"{NAME[k]} 새 신고가 {highs[k][0]}건({highs[k][1]}) → 그 단지 호가와 최근 실거래 비교해보기"))
            if cancs[k] >= 3:
                cands.append((100 + 5 * cancs[k], "C2", k, f"{NAME[k]} 계약 해제 {cancs[k]}건 새로 접수 → 과열·분쟁 신호인지 지켜보기"))
            if k in big_ratio:
                p0, p1 = big_ratio[k]
                txt = "호가가 따라 오르는지 확인" if p1 > p0 else "상승세가 둔화되는지 지켜보기"
                cands.append((100 + 3 * abs(p1 - p0), "C3", k, f"{NAME[k]} 신고가 비율 {p0:.0f}→{p1:.0f}% → {txt}"))
        if minor:
            changed = [changed[0] + " → 큰 변화 없음, 1년 전과 비교하면:"]
    if not prev or minor:
        yo = sorted((k for k in M if M[k]["yoy"] is not None), key=lambda k: (-abs(M[k]["yoy"]), k))
        changed.append(f"· 동일단지 가격({plabel}, 전년 같은 때 대비): "
                       + " · ".join(f"{NAME[k]} {sg(M[k]['yoy'], 0)}%" + ("(표본적음)" if M[k]["yoy_pairs"] < 10 else "") for k in yo))
        vo = sorted((k for k in M if M[k]["vol"] is not None), key=lambda k: (-abs(M[k]["vol"]), k))
        changed.append(f"· 거래량({plabel}, 전년 대비): " + " · ".join(f"{NAME[k]} {sg(M[k]['vol'], 0)}%" + ("(표본적음)" if M[k]["v_ly"] < 30 else "") for k in vo))
    changed = changed[:3]

    # 💡 의미 (규칙: 거래↓+가격↑ / 가격 정체 묶음)
    meaning = []
    hot = [k for k in M if M[k]["yoy"] is not None and M[k]["yoy"] >= 10 and (M[k]["vol"] or 0) < 0]
    flat = [k for k in M if M[k]["yoy"] is not None and abs(M[k]["yoy"]) <= 3]
    seg = []
    if hot:
        seg.append(f"{eun('·'.join(NAME[k] for k in hot))} 거래가 줄어도 값이 오르는 '적게, 비싸게' 흐름")
    if flat:
        seg.append(f"{eun('·'.join(NAME[k] for k in flat))} 가격이 거의 제자리")
    meaning.append("· " + (", ".join(seg) + "." if seg else "지역별로 뚜렷한 방향이 없어요."))
    pend = next(iter(M.values()))["per"].split("~")[1].replace("-", "") if M else ""
    lag = [int(x[4:]) for x in meta["window_months"] if x > pend]
    lagtxt = (f"{lag[0]}~{lag[-1]}월" if len(lag) > 1 else f"{lag[0]}월") if lag else "최근"
    meaning.append(f"· {lagtxt} 계약은 신고기한(30일)이 남아 건수가 앞으로 늘어나요(거래 감소로 오해 금지).")

    # ✅ 할 일 (규칙표 H1~H6)
    for k, m in M.items():
        nm = NAME[k]
        if m["nhr"] >= 30:
            cands.append((m["nhr"], "H1", k, f"{nm} 신고가 비율 {m['nhr']:.0f}% → 관심 단지 호가와 실거래 차이 확인, {EXTRA[k]}"))
        if m["dr"] >= 3 and m["dr"] >= m["nh"]:
            cands.append((3 * m["dr"] / max(m["n"], 1) * 100, "H2", k,
                          f"{nm} 10%↓ 거래 {m['dr']}건(신고가 {m['nh']}) → 저층·직거래인지 확인, 급매 흐름인지 지켜보기"))
        if m["vol"] is not None and m["vol"] <= -40 and m["v_ly"] >= 30:
            cands.append((abs(m["vol"]) / 2, "H4", k, f"{nm} 거래 {sg(m['vol'], 0)}% → 한두 건이 시세를 좌우, 여러 중개소 호가 비교"))
        if m["vol"] is not None and m["vol"] >= 10 and m["yoy"] is not None and abs(m["yoy"]) <= 3:
            cands.append((20, "H5", k, f"{nm} 거래 {sg(m['vol'], 0)}%인데 가격 {sg(m['yoy'], 1)}% → {EXTRA[k] if k == 'yeongjong' else '미분양·신규 분양가와 비교'}"))
        if m["n"] < 20:
            cands.append((10, "H6", k, f"{nm} {since} 이후 거래 {m['n']}건뿐 → 통계보다 개별 매물 확인, {EXTRA[k]}"))
        if m["yoy"] is not None and abs(m["yoy"]) <= 3 and m["n"] >= 50:
            cands.append((5, "H3", k, f"{nm} 가격 정체(전년比 {sg(m['yoy'], 1)}%) → 서두르지 말고 월 1회 실거래만 점검"))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    todo, used = [], set()
    for sc, rid, k, txt in cands:
        if k not in used and len(todo) < 3:
            todo.append(txt); used.add(k)
    for sc, rid, k, txt in cands:  # 지역이 모자라면 같은 지역 두 번째 항목 허용
        if len(todo) < 2 and txt not in todo:
            todo.append(txt)
    if not todo:
        todo = ["큰 변화 없음 → 관심 단지 실거래만 주 1회 확인"]
    todo = [f"· {t}" for t in todo]

    # 📊 근거: 지역별 한 줄(변화 큰 지역부터)
    ev = []
    for k in sorted(M, key=lambda k: (-(abs(M[k]["yoy"] or 0) + M[k]["nhr"]), k)):
        m = M[k]
        y = f"전년比 {sg(m['yoy'], 1)}%" if m["yoy"] is not None else "전년比 -"
        ev.append(f"· {NAME[k]}: 평당 {m['ppy']:,}만({plabel}) · {y} · 신고가 {m['nh']}/{m['n']}({m['nhr']:.0f}%) · 10%↓ {m['dr']}")
    print(render(f"{TITLE} ({cur[:4]}-{cur[4:6]}-{cur[6:]})", changed, meaning, todo, ev,
                 f"※ 신고가·거래는 {since} 이후 계약, 평당은 전용면적 기준"))


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
