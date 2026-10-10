# -*- coding: utf-8 -*-
"""
텔레그램용 요약 [8] 미국 선행 신호 (네트워크 사용 안 함, 일반 텍스트, 1,500자 이내)
  python -I -X utf8 scripts\\telegram_summary.py [--snaproot 다른_스냅샷_폴더]   # --snaproot 는 테스트용

읽는 것: data/snapshots/YYYYMMDD/(meta.json 있는 완료 스냅샷) 최신 1개 + 직전 1개의 summary.json,
         data/processed/findings.json(보고서 기준값, 읽기 전용). 쓰는 것: 없음(stdout 만).
용어: 출시글 = Product Hunt 신규 + Show HN + GitHub Trending 신규 저장소, 요청글 = HN Ask·Reddit 중 "is there a tool",
      "alternative to", "I wish", "frustrated", "manually" 등 요청·불만 표현이 있는 글(최근 2일).

[변화 규칙] ① 직전 스냅샷이 있으면: 요청글 수 직전→오늘, 출시글 분야 1위 변화, 새로 뜬 GitHub 저장소
            ② 없으면: 보고서 기준(YC 2025→2026 분야 비중 변화, 12개월 HN 요청글 대상 1위)

[행동 규칙표]  n = 오늘 스냅샷 값
 ID | 조건                                                  | 점수        | 행동 문구(요지)
 A1 | 요청글 최다 아이디어 X 의 n ≥ 2 (1개만)               | 50 + 10n    | 'X' 요청 n건 → 대표 글 읽고 기능 메모
 A2 | 출시글 중 '브라우저·확장' n ≥ 3                        | 40 + n      | 확장 경쟁작 n개 → PH 에서 기능·가격 확인
 A3 | 출시글 중 '법무·컴플라이언스'+'보안' n ≥ 3             | 45 + n      | 본업 연결 신규 n개 → 국내 대체 서비스 있는지 검색
 A4 | 새 GitHub 급상승 저장소 설명에 agent/MCP/claude/skill  | 35          | 저장소 1개 골라 30분 직접 써보기
 A5 | YC 주간 스냅샷 2개 이상 & 최근배치 분야 비중 ±3%p 이상 | 30 + |Δ|   | YC 분야 변화 → 국내 같은 서비스 검색
 A6 | 요청글 대상 1위가 직전 스냅샷과 다름                   | 25          | 새 불만 대상 → 크롬확장 아이디어 노트에 추가
 A7 | Reddit 일부/전체 실패                                  | 5           | Reddit 차단 → 내일 다시 확인(계속되면 RSS 간격 늘리기)
 A0 | 해당 없음                                              | -           | 큰 변화 없음 → 보고서 아이디어 Top10 중 1개 검증
 점수 높은 순 3개. 같은 데이터면 같은 결과.
"""
import argparse, json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
LIMIT = 1500
TITLE = "📌 [8] 미국 선행 신호"
HOT = re.compile(r"agent|mcp|claude|skill", re.I)


def snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if re.fullmatch(r"\d{8}", d) and os.path.exists(os.path.join(root, d, "meta.json")))


def load(root, d):
    return json.load(open(os.path.join(root, d, "summary.json"), encoding="utf-8"))


def top(d, n=1, skip=()):
    items = sorted(((k, v) for k, v in (d or {}).items() if k not in skip), key=lambda x: (-x[1], x[0]))
    return items[:n]


def short(t, n=48):
    t = re.sub(r"\s+", " ", str(t)).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


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
    p = load(a.snaproot, ds[-2]) if len(ds) >= 2 else None
    fp = os.path.join(BASE, "data", "processed", "findings.json")
    F = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    nc = s.get("new_counts", {})
    launch_top = top(s.get("launch_cats"), 2, skip=("개발도구·코딩",))
    obj_top = top(s.get("objs"), 1, skip=("AI 사용(ChatGPT·Claude 등)",))

    # 🔄 변화
    changed = []
    if p:
        pv = f"{ds[-2][4:6]}/{ds[-2][6:]}"
        changed.append(f"· 요청·불만 글: 지난번({pv}) {p.get('req_n', 0)}건 → 오늘 {s.get('req_n', 0)}건 (HN·Reddit 최근 {s['days']}일)")
        pl = top(p.get("launch_cats"), 1, skip=("개발도구·코딩",))
        if launch_top:
            was = f"{pl[0][0]}" if pl else "-"
            changed.append(f"· 새로 잡힌 출시 {s.get('launch_n', 0)}개 중 많은 분야: " + ", ".join(f"{k} {v}" for k, v in launch_top)
                           + (f" (지난번 1위 {was})" if was != launch_top[0][0] else " (지난번과 같음)"))
        if s.get("gh_new_repos"):
            changed.append("· 새로 뜬 GitHub 저장소: " + ", ".join(short(r.split("/")[-1], 24) for r in s["gh_new_repos"][:3]))
    else:
        cs = (F.get("yc") or {}).get("cat_share") or []
        if cs:
            up = sorted(cs, key=lambda r: -(r.get("2025→2026(%p)") or 0))[:2]
            changed.append("· YC(미국 스타트업 학교) 2025→2026 비중 증가: " + ", ".join(f"{r['분야']} {r['2025']}→{r['2026']}%" for r in up))
        ob = (F.get("demand") or {}).get("obj") or []
        ob = [r for r in ob if not r["index"].startswith("AI 사용")]
        if ob:
            changed.append(f"· 12개월 HN·Reddit 요청 글 대상 1위: {ob[0]['index']}({ob[0]['합계']}건)")
        if launch_top:
            changed.append(f"· 최근 출시 {s.get('launch_n', 0)}개(PH·Show HN·GitHub) 중 많은 분야: " + ", ".join(f"{k} {v}" for k, v in launch_top))
    changed = changed[:3]

    # 💡 의미
    meaning = []
    if launch_top:
        meaning.append(f"· 미국에선 지금 '{launch_top[0][0]}' 쪽 신제품이 가장 많이 나와요. 1~2년 뒤 국내에도 비슷한 서비스가 나올 후보예요.")
    if obj_top:
        meaning.append(f"· 최근 수집분에서 가장 많이 불편해하는 대상은 '{obj_top[0][0]}'({obj_top[0][1]}건) — 작은 확장 프로그램으로 풀 수 있는 문제인지 볼 만해요.")
    if not meaning:
        meaning = ["· 오늘은 눈에 띄는 쏠림이 없어요."]

    # ✅ 할 일
    cands = []
    ir = top(s.get("ideas_req"), 1)   # A1 은 요청이 가장 많은 아이디어 1개만
    if ir and ir[0][1] >= 2:
        k, v = ir[0]
        cands.append((50 + 10 * v, "A1", f"'{k}' 요청 {v}건 → 대표 글 읽고 필요한 기능 메모"))
    lc = s.get("launch_cats") or {}
    if lc.get("브라우저·확장", 0) >= 3:
        cands.append((40 + lc["브라우저·확장"], "A2", f"브라우저·확장 신제품 {lc['브라우저·확장']}개 → Product Hunt에서 기능·가격 확인"))
    comp = lc.get("법무·컴플라이언스", 0) + lc.get("보안", 0)
    if comp >= 3:
        cands.append((45 + comp, "A3", f"컴플라이언스·보안 신제품 {comp}개(본업 연결) → 국내에 같은 서비스 있는지 검색"))
    hot = [r for r in s.get("gh_new_repos", []) if HOT.search(r)]
    hot_desc = [t for t, _, d in s.get("gh_daily_top", []) if HOT.search(f"{t} {d}")]
    pick = (hot or hot_desc)
    if pick:
        cands.append((35, "A4", f"GitHub 급상승 '{short(pick[0], 40)}' → 30분 직접 설치해 써보기"))
    y, yp = s.get("yc"), s.get("yc_prev")
    if y and yp and y.get("date") != yp.get("date"):
        diffs = sorted(((k, v - yp.get("recent_cat_share", {}).get(k, 0)) for k, v in y.get("recent_cat_share", {}).items()),
                       key=lambda x: (-abs(x[1]), x[0]))
        if diffs and abs(diffs[0][1]) >= 3:
            k, d = diffs[0]
            cands.append((30 + abs(d), "A5", f"YC 최근 배치 '{k}' 비중 {d:+.1f}%p → 국내 같은 서비스 검색"))
    if p and obj_top:
        po = top(p.get("objs"), 1, skip=("AI 사용(ChatGPT·Claude 등)",))
        if po and po[0][0] != obj_top[0][0]:
            cands.append((25, "A6", f"새 불만 대상 '{obj_top[0][0]}' → 크롬확장 아이디어 노트에 추가"))
    rs = str((s.get("status") or {}).get("Reddit", ""))
    if "차단" in rs or not rs.startswith("ok"):
        cands.append((5, "A7", "Reddit 일부 수집 실패 → 내일 다시 확인"))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    todo = [f"· {t}" for _, _, t in cands[:3]] or ["· 큰 변화 없음 → 보고서 아이디어 Top10 중 1개 골라 검증"]

    # 📊 근거
    cnt = s.get("counts", {})
    m = re.match(r"ok (\d+)/(\d+)", rs)
    rsub = f"({m.group(1)}/{m.group(2)}개 게시판)" if m and m.group(1) != m.group(2) else ("(수집 실패)" if not m else "")
    ev = [f"· 수집: PH {cnt.get('PH', 0)}(신규 {nc.get('PH', 0)}) · Show HN {cnt.get('Show HN', 0)} · Ask HN {cnt.get('HN Ask', 0)}"
          f" · Reddit {cnt.get('Reddit', 0)}{rsub} · GitHub {nc.get('GitHub', 0)}개 신규"]
    if s.get("req_top"):
        src, t, c = s["req_top"][0]
        ev.append(f"· 반응 많은 요청 글({src}): \"{short(t, 60)}\"")
    if s.get("gh_daily_top"):
        t, g, _ = s["gh_daily_top"][0]
        ev.append(f"· 오늘 GitHub 1위: {short(t, 40)}" + (f" (+{int(float(g)):,}★)" if g not in (None, "") else ""))
    if s.get("show_top"):
        t, sc = s["show_top"][0]
        ev.append(f"· Show HN 1위: {short(t, 50)} ({sc}점)")
    y = s.get("yc")
    if y:
        ev.append(f"· YC 최근 배치({', '.join(b.split()[0][:1] + b.split()[1][2:] for b in y['recent_batches'])}) {y['recent_n']}곳 기준({y['date'][5:]})")
    foot = "※ 미국 커뮤니티 키워드 규칙 분류라 오차 있음. 투자 권유 아님"
    print(render(f"{TITLE} ({cur[:4]}-{cur[4:6]}-{cur[6:]})", changed, meaning, todo, ev, foot))


def render(head, changed, meaning, todo, ev, foot):
    def join(evl):
        return "\n".join([head, "🔄 무엇이 바뀌었나", *changed, "💡 무슨 의미", *meaning, "✅ 내가 할 일", *todo, "📊 근거", *evl, foot])
    evl = list(ev)
    out = join(evl)
    while len(out) > LIMIT and len(evl) > 1:
        evl.pop(); out = join(evl)
    return out if len(out) <= LIMIT else out[:LIMIT - 1] + "…"


if __name__ == "__main__":
    main()
