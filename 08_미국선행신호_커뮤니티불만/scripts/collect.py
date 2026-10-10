# -*- coding: utf-8 -*-
"""최초 전체 수집 → data/raw/ (약 10~15분, 순차 요청)
  python -I -X utf8 scripts\\collect.py [--only yc,ph,gh,hn,rd] [--hn-days 365]
"""
import argparse, datetime as dt, json, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import common as C

RAW = os.path.join(C.BASE, "data", "raw")
os.makedirs(RAW, exist_ok=True)
status = {}


def save(df, name):
    df.to_csv(os.path.join(RAW, name), index=False, encoding="utf-8-sig")
    print(f"[save] {name} {len(df)}행", flush=True)


def do_yc():
    o = C.yc_opts()
    counts, total = C.yc_facets(o)
    json.dump({"total": total, "batch_counts": counts, "collected_at": dt.datetime.now().isoformat(timespec="seconds")},
              open(os.path.join(RAW, "yc_batch_counts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rows = []
    for b in C.YC_BATCHES:
        if b in counts:
            x = C.yc_batch(o, b); rows += x
            print(f"[yc] {b} {len(x)}/{counts[b]}", flush=True)
    df = pd.DataFrame(rows)
    for c in ("industries", "tags", "regions"):
        df[c] = df[c].map(lambda v: "|".join(v or []))
    save(df, "yc_companies.csv")
    return len(df)


def do_ph():
    rows = []
    for c in C.PH_CATS:
        rows += C.ph_feed(c)
    df = pd.DataFrame(rows)
    cats = df.groupby("id")["ph_cat"].agg(lambda s: "|".join(sorted(set(s))))
    df = df.drop_duplicates("id").drop(columns="ph_cat").merge(cats, left_on="id", right_index=True)
    save(df, "ph_items.csv")
    return len(df)


def do_gh():
    rows = []
    for s in ("daily", "weekly", "monthly"):
        rows += C.gh_trending(s)
    df = pd.DataFrame(rows)
    topics = {}
    for repo in df["repo"].unique()[:55]:   # 비인증 한도 60/시간
        t = C.gh_topics(repo)
        if t is None:
            print("[gh] topics 조회 중단(한도/차단)"); break
        topics[repo] = t
    df["topics"] = df["repo"].map(lambda r: "|".join(topics.get(r, {}).get("topics", [])))
    df["created_at"] = df["repo"].map(lambda r: topics.get(r, {}).get("created_at", ""))
    save(df, "gh_trending.csv")
    return len(df)


def windowed(tags, start, end, step_days, extra=""):
    out, t = [], start
    while t < end:
        t2 = min(end, t + step_days * 86400)
        hits, nb = C.hn(tags, t, t2, extra=extra)
        if nb > len(hits) and step_days > 1:          # 1000개 넘으면 창을 반으로
            out += windowed(tags, t, t2, max(1, step_days // 2), extra)
        else:
            out += hits
        t = t2
    return out


def do_hn(days):
    now = int(time.time())
    ask = pd.DataFrame(windowed("ask_hn", now - days * 86400, now, 14)).drop_duplicates("id")
    save(ask, "hn_ask.csv")
    show = pd.DataFrame(windowed("show_hn", now - 180 * 86400, now, 30, extra=",points>=20")).drop_duplicates("id")
    save(show, "hn_show.csv")
    return len(ask) + len(show)


def do_rd():
    rows, blocked = [], []
    for sub in C.SUBS:
        for kind in ("new", "top"):
            try:
                x = C.reddit_rss(sub, kind); rows += x
                print(f"[reddit] r/{sub} {kind} {len(x)}", flush=True)
            except Exception as e:
                blocked.append(f"{sub}/{kind}:{type(e).__name__}")
                print(f"[reddit] r/{sub} {kind} 실패 {e}", flush=True)
    df = pd.DataFrame(rows)
    if len(df):
        kinds = df.groupby("id")["kind"].agg(lambda s: "|".join(sorted(set(s))))
        df = df.drop_duplicates("id").drop(columns="kind").merge(kinds, left_on="id", right_index=True)
    save(df, "reddit.csv")
    status["reddit_blocked"] = blocked
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="yc,ph,gh,hn,rd")
    ap.add_argument("--hn-days", type=int, default=365)
    a = ap.parse_args()
    fns = {"yc": do_yc, "ph": do_ph, "gh": do_gh, "hn": lambda: do_hn(a.hn_days), "rd": do_rd}
    for k in a.only.split(","):
        t0 = time.time()
        try:
            status[k] = {"rows": fns[k](), "sec": round(time.time() - t0, 1)}
        except Exception as e:
            traceback.print_exc()
            status[k] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    p = os.path.join(RAW, "_collect_meta.json")
    old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    old.update({k: v for k, v in status.items()}); old["collected_at"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(old, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(C.j(status))


if __name__ == "__main__":
    main()
