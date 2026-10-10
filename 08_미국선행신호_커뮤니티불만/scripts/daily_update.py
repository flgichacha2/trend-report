# -*- coding: utf-8 -*-
"""
일일 자동 갱신: [8] 미국 선행 신호 + 불만 글   (cwd=과제 폴더)
  python -I -X utf8 scripts\\daily_update.py [--days 2] [--force-yc]

가볍게(약 3~5분) 최근 1~2일 신규만 모은다. 순차 요청, 요청 사이 1~1.5초(Reddit 7초).
 - Product Hunt: 공개 Atom 피드(전체 + 8개 카테고리, 9회) → 직전 스냅샷에 없던 제품 = 신규
 - Hacker News: Algolia API, 최근 --days 일 Ask HN 전부 + Show HN 전부(2회)
 - Reddit: 8개 서브레딧 /new/.rss (8회, 10초 간격, JSON 은 403 차단). 최근 --days 일 글만. 429/403 이면 해당 서브만 건너뜀
 - GitHub Trending: daily·weekly HTML(2회) → 직전 스냅샷에 없던 저장소 = 신규
 - YC: 주 1회(마지막 YC 스냅샷이 7일 이상 지났을 때만) 배치별 기업 수 + 최근 2개 배치 기업 목록(간략)
쓰는 곳: data/snapshots/YYYYMMDD/ (items.csv, summary.json, meta.json=완료 표시), data/snapshots/yc/YYYYMMDD/
 data/raw, data/processed 는 건드리지 않음. 같은 날 재실행 시 같은 폴더를 다시 씀.
 모든 수집원이 실패하면 종료코드 1 (일부 실패는 summary.json 의 status 에 기록하고 계속).
"""
import argparse, datetime as dt, json, os, re, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import common as C
from analyze import IDEAS

TODAY = dt.date.today()
SNAPROOT = os.path.join(C.BASE, "data", "snapshots")
YCROOT = os.path.join(SNAPROOT, "yc")


def done_snaps(root):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if d.isdigit() and len(d) == 8 and os.path.exists(os.path.join(root, d, "meta.json")))


def prev_items(cur):
    ds = [d for d in done_snaps(SNAPROOT) if d < cur]
    if not ds:
        return None, pd.DataFrame(columns=["src", "id"])
    return ds[-1], pd.read_csv(os.path.join(SNAPROOT, ds[-1], "items.csv"), dtype=str, keep_default_na=False)


def tagrow(r):
    full = f"{r['title']} . {str(r.get('text', ''))[:600]}"
    r["cats"] = "|".join(C.tag(full, C.CATS_RE))
    r["is_req"] = bool(C.REQ.search(full)) if r["src"] in ("HN Ask", "Reddit") else False
    r["pains"] = "|".join(C.tag(full, C.PAIN_RE)) if r["is_req"] else ""
    r["objs"] = "|".join(C.tag(full, C.OBJ_RE)) if r["is_req"] else ""
    r["ideas"] = "|".join(n for n, dem, comp in IDEA_RE
                          if (r["is_req"] and dem.search(full)) or (r["src"] in ("PH", "Show HN", "GitHub") and comp.search(full)))
    return r


IDEA_RE = [(n, re.compile(d, re.I), re.compile(c, re.I)) for n, d, c, _ in IDEAS]


def run_yc(force):
    ds = done_snaps(YCROOT)
    if ds and not force and (TODAY - dt.datetime.strptime(ds[-1], "%Y%m%d").date()).days < 7:
        return {"skipped": True, "last": ds[-1]}
    out = os.path.join(YCROOT, TODAY.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    if os.path.exists(os.path.join(out, "meta.json")):
        os.remove(os.path.join(out, "meta.json"))
    o = C.yc_opts()
    counts, total = C.yc_facets(o)
    order = [b for b in C.YC_BATCHES if b in counts]
    recent = order[-2:]
    rows = []
    for b in recent:
        rows += C.yc_batch(o, b)
    df = pd.DataFrame(rows)[["name", "slug", "batch", "industry", "tags", "one_liner", "team_size"]]
    df["tags"] = df["tags"].map(lambda v: "|".join(v or []))
    df["cats"] = (df["one_liner"].fillna("") + " " + df["tags"]).map(lambda t: "|".join(C.tag(t, C.CATS_RE)))
    df.to_csv(os.path.join(out, "yc_recent.csv.gz"), index=False, encoding="utf-8", compression="gzip")
    cat = df["cats"].str.split("|").explode()
    cat = cat[cat != ""].value_counts()
    info = {"date": TODAY.isoformat(), "total": total, "batch_counts": {b: counts[b] for b in order},
            "recent_batches": recent, "recent_n": len(df),
            "recent_cat_share": {k: round(v / len(df) * 100, 1) for k, v in cat.items()}}
    json.dump(info, open(os.path.join(out, "yc.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"complete": True, "finished_at": dt.datetime.now().isoformat(timespec="seconds")},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"))
    return {"skipped": False, "last": os.path.basename(out)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--force-yc", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    cur = TODAY.strftime("%Y%m%d")
    snap = os.path.join(SNAPROOT, cur)
    os.makedirs(snap, exist_ok=True)
    meta_path = os.path.join(snap, "meta.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)
    prev, P = prev_items(cur)
    since = time.time() - a.days * 86400
    since_d = (TODAY - dt.timedelta(days=a.days)).isoformat()
    rows, status = [], {}

    # Product Hunt
    try:
        ph = []
        for c in C.PH_CATS:
            ph += C.ph_feed(c)
        seen = set()
        for x in ph:
            if x["id"] in seen:
                continue
            seen.add(x["id"])
            rows.append({"src": "PH", "id": x["id"], "title": x["title"], "text": x["tagline"], "created": x["published"][:10],
                         "score": "", "url": x["url"], "extra": x["ph_cat"]})
        status["PH"] = f"ok {len(seen)}"
    except Exception as e:
        status["PH"] = f"실패 {type(e).__name__}"
    # Hacker News
    try:
        ask, _ = C.hn("ask_hn", since)
        show, _ = C.hn("show_hn", since)
        for src, lst in (("HN Ask", ask), ("Show HN", show)):
            for x in lst:
                rows.append({"src": src, "id": x["id"], "title": x["title"], "text": x["text"][:600], "created": x["created"],
                             "score": x["points"], "url": x["url"], "extra": x["comments"]})
        status["HN"] = f"ok ask {len(ask)} / show {len(show)}"
    except Exception as e:
        status["HN"] = f"실패 {type(e).__name__}"
    # Reddit
    ok_sub, bad = 0, []
    for sub in C.SUBS:
        try:
            for x in C.reddit_rss(sub, "new", tries=2, sleep=10):
                if x["created"] >= since_d:
                    rows.append({"src": "Reddit", "id": x["id"], "title": x["title"], "text": x["text"][:600], "created": x["created"],
                                 "score": "", "url": x["url"], "extra": sub})
            ok_sub += 1
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", "")
            bad.append(f"{sub}:{type(e).__name__}{code}")
    status["Reddit"] = f"ok {ok_sub}/{len(C.SUBS)}" + (f" (차단·실패: {', '.join(bad)})" if bad else "")
    # GitHub Trending
    try:
        n = 0
        for s in ("daily", "weekly"):
            for x in C.gh_trending(s):
                rows.append({"src": "GitHub", "id": f"{x['repo']}@{s}", "title": x["repo"], "text": x["desc"], "created": TODAY.isoformat(),
                             "score": x["gain"], "url": f"https://github.com/{x['repo']}", "extra": f"{s}|{x['lang']}|{x['rank']}"})
                n += 1
        status["GitHub"] = f"ok {n}"
    except Exception as e:
        status["GitHub"] = f"실패 {type(e).__name__}"
    # YC (주 1회)
    try:
        status["YC"] = run_yc(a.force_yc)
    except Exception as e:
        status["YC"] = {"error": type(e).__name__}

    if not rows:
        raise RuntimeError(f"모든 수집원 실패: {status}")
    df = pd.DataFrame(rows).drop_duplicates(["src", "id"])
    df = df.apply(tagrow, axis=1)
    pk = set(zip(P["src"], P["id"]))
    df["is_new"] = [(s, i) not in pk for s, i in zip(df["src"], df["id"])]
    # PH 피드는 몇 주 전 제품도 섞여 있어 '최근 30일 이내 게시 + 직전에 없던 것'만 신규
    ph_old = (df["src"] == "PH") & (df["created"] < (TODAY - dt.timedelta(days=30)).isoformat())
    df.loc[ph_old, "is_new"] = False
    if prev is None:   # 첫 스냅샷: HN·Reddit 은 기간 내 전부, PH 는 최근 30일 게시분만 신규
        df.loc[df["src"] == "GitHub", "is_new"] = True
    df.to_csv(os.path.join(snap, "items.csv.tmp"), index=False, encoding="utf-8-sig")
    os.replace(os.path.join(snap, "items.csv.tmp"), os.path.join(snap, "items.csv"))

    def vc(x, col):
        s = x[col].astype(str).str.split("|").explode()
        return s[s != ""].value_counts().to_dict()
    new = df[df["is_new"]]
    launch = new[new["src"].isin(["PH", "Show HN", "GitHub"])]
    gh_repo_new = new[new["src"] == "GitHub"]["title"].unique().tolist()
    req = df[df["is_req"]]
    summary = {
        "date": TODAY.isoformat(), "days": a.days, "prev_snapshot": prev, "status": status,
        "counts": df.groupby("src").size().to_dict(), "new_counts": new.groupby("src").size().to_dict(),
        "launch_cats": vc(launch, "cats"), "launch_n": len(launch),
        "req_n": len(req), "req_by_src": req.groupby("src").size().to_dict(),
        "pains": vc(req, "pains"), "objs": vc(req, "objs"), "ideas_req": vc(req, "ideas"), "ideas_launch": vc(launch, "ideas"),
        "gh_new_repos": gh_repo_new[:10],
        "gh_daily_top": df[(df["src"] == "GitHub") & df["id"].str.endswith("@daily")].head(5)[["title", "score", "text"]].values.tolist(),
        "ph_new": new[new["src"] == "PH"][["title", "text"]].head(8).values.tolist(),
        "show_top": df[df["src"] == "Show HN"].assign(p=lambda x: pd.to_numeric(x["score"], errors="coerce")).sort_values("p", ascending=False)
                     .head(5)[["title", "score"]].values.tolist(),
        "req_top": req.assign(c=lambda x: pd.to_numeric(x["extra"], errors="coerce").fillna(0))
                     .sort_values(["c"], ascending=False).head(8)[["src", "title", "extra"]].values.tolist(),
    }
    ycd = done_snaps(YCROOT)
    if ycd:
        summary["yc"] = json.load(open(os.path.join(YCROOT, ycd[-1], "yc.json"), encoding="utf-8"))
        summary["yc_prev"] = json.load(open(os.path.join(YCROOT, ycd[-2], "yc.json"), encoding="utf-8")) if len(ycd) >= 2 else None
    json.dump(summary, open(os.path.join(snap, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    meta = {"date": cur, "finished_at": dt.datetime.now().isoformat(timespec="seconds"), "elapsed_sec": round(time.time() - t0, 1),
            "rows": len(df), "new": len(new), "status": status, "prev_snapshot": prev, "complete": True}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(meta, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        for k in ("GITHUB_TOKEN",):
            v = os.environ.get(k)
            if v:
                msg = msg.replace(v, "***")
        print(msg, file=sys.stderr)
        sys.exit(1)
