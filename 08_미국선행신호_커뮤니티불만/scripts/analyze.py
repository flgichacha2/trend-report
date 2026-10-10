# -*- coding: utf-8 -*-
"""data/raw → data/processed (보고서용 표) + data/processed/findings.json
  python -I -X utf8 scripts\\analyze.py
"""
import datetime as dt, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import common as C

RAW = os.path.join(C.BASE, "data", "raw")
OUT = os.path.join(C.BASE, "data", "processed")
os.makedirs(OUT, exist_ok=True)
F = {}
YEARS = {"2024": ["Winter 2024", "Summer 2024", "Fall 2024"],
         "2025": ["Winter 2025", "Spring 2025", "Summer 2025", "Fall 2025"],
         "2026": ["Winter 2026", "Spring 2026", "Summer 2026", "Fall 2026"]}

# 크롬확장·자동화 아이디어 후보: 수요(HN/Reddit 요청글) 정규식, 경쟁(PH/YC 설명) 정규식, 난이도(수동 판단)
IDEAS = [
    ("민감정보 마스킹 후 AI 붙여넣기", r"\bpii\b|sensitive (data|info)|redact|confidential.*(chatgpt|ai|llm)|(chatgpt|llm|ai).*(confidential|leak|company data)|data leak",
     r"\bpii\b|redact|sensitive data|data loss prevention|\bdlp\b|ai (usage )?governance|shadow ai", "중"),
    ("탭·북마크 AI 정리/다시찾기", r"\btabs\b|bookmark|read later|saved (links|articles)", r"\btabs?\b|bookmark|read.?later", "하"),
    ("웹페이지 표·목록 → 시트 추출", r"scrap(e|ing)|extract (data|table)|copy.*(table|data).*(sheet|excel)|web data", r"scrap|extract data|web data|crawl", "중"),
    ("이메일 후속조치·요약 비서", r"\bgmail\b|inbox|follow.?up|email (overload|triage)|too many emails", r"\binbox|\bemail (assistant|triage|client)|follow.?up", "중"),
    ("유튜브·회의·웨비나 요약 노트", r"youtube|meeting (notes|summar)|transcri|webinar|podcast summar", r"meeting (notes|assistant)|note.?taker|transcri|youtube summar", "하"),
    ("반복 웹 업무 녹화→자동 실행", r"(fill|filling) (out )?(the same )?forms?|autofill|repetitive (task|work)|automate (my|this|a) .*(browser|web|task)|browser automation|rpa",
     r"browser (agent|automation|use)|computer use|\brpa\b|web agent|automate.*browser", "상"),
    ("가격·페이지 변경 모니터링 알림", r"monitor (a |the )?(website|page|price)|price (drop|track|alert)|change detection|notify me when", r"monitor|price track|change detection|alerts?\b", "하"),
    ("AI 대화·프롬프트 관리", r"prompt (library|manager|management)|(chatgpt|claude) (history|conversations?)|organi[sz]e (my )?(chats|prompts)|save prompts",
     r"prompt (library|manager)|chat history|ai conversations?", "하"),
    ("인보이스·영수증 자동 수집", r"invoice|receipt|expense report|bookkeep", r"invoice|receipt|expense|bookkeep", "중"),
    ("SNS·링크드인 게시/리드 수집", r"linkedin|schedul(e|ing) posts?|social media (posting|management)|cold outreach|lead (gen|list)",
     r"linkedin|social media|outreach|lead gen", "중"),
    ("엑셀 수식·정리 도우미", r"\bexcel\b|spreadsheet|vlookup|xlookup|formula|pivot|power query|google sheets", r"spreadsheet|excel|sheets", "하"),
    ("구직 지원서 자동 맞춤", r"job (search|application|hunt)|\bresumes?\b|\bcv\b|cover letter|applying (to|for) jobs", r"resume|job (search|application)|cover letter|career", "중"),
    ("집중·시간 기록(자동 타임시트)", r"focus (app|mode|tool)|distract|procrastinat|time.?track|timesheet|adhd", r"focus|time.?track|timesheet|distraction", "하"),
    ("고객 리뷰·피드백 모아보기", r"customer feedback|reviews? (from|on)|feature requests?|nps|user feedback", r"feedback|reviews|feature request", "중"),
]


def share_table(df, col_text, groups, table):
    rows = []
    for k, rx in table.items():
        r = {"분야": k}
        for g, mask in groups.items():
            x = df.loc[mask, col_text]
            r[g] = round(x.str.contains(rx).mean() * 100, 1) if len(x) else None
        rows.append(r)
    return pd.DataFrame(rows)


def yc():
    d = pd.read_csv(os.path.join(RAW, "yc_companies.csv"), dtype=str, keep_default_na=False)
    d["txt"] = d["one_liner"] + " " + d["tags"].str.replace("|", " ") + " " + d["subindustry"]
    g = {y: d["batch"].isin(b) for y, b in YEARS.items()}
    t = share_table(d, "txt", g, C.CATS_RE)
    t["2025→2026(%p)"] = (t["2026"] - t["2025"]).round(1)
    t = t.sort_values("2026", ascending=False)
    t.to_csv(os.path.join(OUT, "yc_category_share.csv"), index=False, encoding="utf-8-sig")
    # YC 공식 태그
    rows = []
    for y, b in YEARS.items():
        x = d[d["batch"].isin(b)]
        tags = x["tags"].str.split("|").explode()
        vc = tags[tags != ""].value_counts()
        for tg, n in vc.items():
            rows.append({"year": y, "tag": tg, "n": n, "share": round(n / len(x) * 100, 1)})
    tg = pd.DataFrame(rows).pivot_table(index="tag", columns="year", values="share", fill_value=0)
    tg["2025→2026(%p)"] = tg["2026"] - tg["2025"]
    tg = tg[(tg["2026"] >= 2) | (tg["2025"] >= 2)].sort_values("2025→2026(%p)", ascending=False)
    tg.round(1).to_csv(os.path.join(OUT, "yc_tag_share.csv"), encoding="utf-8-sig")
    bc = d["batch"].value_counts()
    F["yc"] = {"n": len(d), "by_year": {y: int(m.sum()) for y, m in g.items()},
               "batches": {b: int(bc.get(b, 0)) for bs in YEARS.values() for b in bs},
               "cat_share": t.head(21).to_dict("records"),
               "tag_up": tg.head(12).round(1).reset_index().to_dict("records"),
               "tag_down": tg.tail(8).round(1).reset_index().to_dict("records"),
               "hiring_2026": int(d.loc[g["2026"]].get("isHiring", pd.Series(dtype=str)).eq("True").sum()) if "isHiring" in d else None}
    latest = d[d["batch"].isin(["Summer 2026", "Fall 2026"])]
    F["yc"]["examples"] = {k: latest[latest["txt"].str.contains(rx)][["name", "batch", "one_liner"]].head(6).values.tolist()
                           for k, rx in C.CATS_RE.items()}
    return d


def ph():
    d = pd.read_csv(os.path.join(RAW, "ph_items.csv"), dtype=str, keep_default_na=False)
    d["pub"] = pd.to_datetime(d["published"].str[:10])
    d["txt"] = d["title"] + " " + d["tagline"]
    rec = d[d["pub"] >= pd.Timestamp(dt.date.today() - dt.timedelta(days=60))]
    t = share_table(d, "txt", {"전체": d["txt"] != "", "최근60일": d["pub"] >= rec["pub"].min() if len(rec) else d["txt"] == "x"}, C.CATS_RE)
    t["최근60일 개수"] = [int(rec["txt"].str.contains(rx).sum()) for rx in C.CATS_RE.values()]
    t = t.sort_values("최근60일", ascending=False)
    t.to_csv(os.path.join(OUT, "ph_category_share.csv"), index=False, encoding="utf-8-sig")
    F["ph"] = {"n": len(d), "recent60": len(rec), "cat_share": t.to_dict("records"),
               "chrome_ext_recent": rec[rec["ph_cat"].str.contains("chrome-extensions")][["title", "tagline", "published"]].head(15).values.tolist()}
    return d


def gh():
    d = pd.read_csv(os.path.join(RAW, "gh_trending.csv"), dtype=str, keep_default_na=False)
    d["txt"] = d["repo"].str.replace("[/_-]", " ", regex=True) + " " + d["desc"] + " " + d["topics"].str.replace("|", " ")
    u = d.drop_duplicates("repo")
    cat = {k: int(u["txt"].str.contains(rx).sum()) for k, rx in C.CATS_RE.items()}
    topics = d.drop_duplicates("repo")["topics"].str.split("|").explode()
    topics = topics[topics != ""].value_counts().head(25)
    kw = {"AI agent": r"\bagent", "MCP": r"\bmcp\b|model context protocol", "Claude/Claude Code": r"claude",
          "skills/plugins": r"\bskills?\b|plugin", "LLM/모델": r"\bllm|model", "브라우저/웹 자동화": r"browser|web agent|playwright|scrap"}
    kwc = {k: int(u["txt"].str.contains(v, case=False).sum()) for k, v in kw.items()}
    F["gh"] = {"n_rows": len(d), "n_repos": len(u), "since_counts": d["since"].value_counts().to_dict(), "cat": cat,
               "kw": kwc, "topics": topics.to_dict(), "lang": u["lang"].replace("", "(없음)").value_counts().head(8).to_dict(),
               "top": d.sort_values("gain", key=lambda s: pd.to_numeric(s, errors="coerce"), ascending=False)
                   [["repo", "since", "gain", "desc"]].head(12).values.tolist()}
    pd.DataFrame([{"분야": k, "저장소수": v} for k, v in cat.items()]).sort_values("저장소수", ascending=False).to_csv(
        os.path.join(OUT, "gh_category.csv"), index=False, encoding="utf-8-sig")


def demand():
    a = pd.read_csv(os.path.join(RAW, "hn_ask.csv"), dtype=str, keep_default_na=False)
    a["src"] = "HN Ask"
    s = pd.read_csv(os.path.join(RAW, "hn_show.csv"), dtype=str, keep_default_na=False)
    r = pd.read_csv(os.path.join(RAW, "reddit.csv"), dtype=str, keep_default_na=False) if os.path.exists(os.path.join(RAW, "reddit.csv")) else pd.DataFrame(columns=["id", "sub", "title", "text", "created", "url"])
    r["src"] = "Reddit r/" + r["sub"]
    for x in (a, r):
        x["full"] = x["title"] + " . " + x["text"].str[:300]
    a["req"] = a["full"].str.contains(C.REQ)
    r["req"] = r["full"].str.contains(C.REQ)
    a["month"] = a["created"].str[:7]
    m = a.groupby("month").agg(ask=("id", "size"), req=("req", "sum"))
    m["req_pct"] = (m["req"] / m["ask"] * 100).round(1)
    m.to_csv(os.path.join(OUT, "hn_ask_monthly.csv"), encoding="utf-8-sig")
    # 'is there a tool'류 엄격한 요청
    strict = re.compile(r"is there (a|an|any) (tool|app|service|software|extension|way|product|saas|website)|alternative(s)? to|i wish there (was|were)|looking for (a|an) (tool|app|service|software|extension)", re.I)
    a["strict"] = a["title"].str.contains(strict)
    R = pd.concat([a[a["req"]], r[r["req"]]], ignore_index=True)
    R["pains"] = R["full"].map(lambda t: "|".join(C.tag(t, C.PAIN_RE)))
    R["objs"] = R["full"].map(lambda t: "|".join(C.tag(t, C.OBJ_RE)))
    R["points"] = pd.to_numeric(R.get("points"), errors="coerce").fillna(0)
    R["comments"] = pd.to_numeric(R.get("comments"), errors="coerce").fillna(0)
    R[["src", "id", "created", "title", "points", "comments", "pains", "objs", "url"]].to_csv(
        os.path.join(OUT, "requests_tagged.csv"), index=False, encoding="utf-8-sig")
    def cnt(col, src_mask):
        x = R.loc[src_mask, col].str.split("|").explode()
        return x[x != ""].value_counts().to_dict()
    hnm, rdm = R["src"].eq("HN Ask"), R["src"].str.startswith("Reddit")
    pain = pd.DataFrame({"HN": pd.Series(cnt("pains", hnm)), "Reddit": pd.Series(cnt("pains", rdm))}).fillna(0).astype(int)
    pain["합계"] = pain.sum(axis=1)
    pain.sort_values("합계", ascending=False).to_csv(os.path.join(OUT, "pain_types.csv"), encoding="utf-8-sig")
    obj = pd.DataFrame({"HN": pd.Series(cnt("objs", hnm)), "Reddit": pd.Series(cnt("objs", rdm))}).fillna(0).astype(int)
    obj["합계"] = obj.sum(axis=1)
    obj.sort_values("합계", ascending=False).to_csv(os.path.join(OUT, "pain_objects.csv"), encoding="utf-8-sig")
    # 대상×유형 교차
    ex = R.assign(o=R["objs"].str.split("|")).explode("o").assign(p=lambda x: x["pains"].str.split("|")).explode("p")
    ex = ex[(ex["o"] != "") & (ex["p"] != "")]
    cross = pd.crosstab(ex["o"], ex["p"])
    cross.to_csv(os.path.join(OUT, "pain_cross.csv"), encoding="utf-8-sig")
    # 서브레딧별
    sub = r.groupby("sub").agg(posts=("id", "size"), req=("req", "sum"), oldest=("created", "min"), newest=("created", "max"))
    sub.to_csv(os.path.join(OUT, "reddit_subs.csv"), encoding="utf-8-sig")
    # Show HN 분야 (분기)
    s["txt"] = s["title"] + " " + s["text"].str[:300]
    s["q"] = pd.to_datetime(s["created"]).dt.to_period("Q").astype(str)
    s["points"] = pd.to_numeric(s["points"], errors="coerce")
    sh = share_table(s, "txt", {q: s["q"].eq(q) for q in sorted(s["q"].unique())}, C.CATS_RE)
    sh.to_csv(os.path.join(OUT, "hn_show_category.csv"), index=False, encoding="utf-8-sig")
    # 아이디어 점수
    ph_ = pd.read_csv(os.path.join(RAW, "ph_items.csv"), dtype=str, keep_default_na=False)
    ph_txt = ph_["title"] + " " + ph_["tagline"]
    yc_ = pd.read_csv(os.path.join(RAW, "yc_companies.csv"), dtype=str, keep_default_na=False)
    yc_txt = yc_["one_liner"] + " " + yc_["tags"]
    show_txt = s["txt"]
    rows = []
    for name, dem, comp, diff in IDEAS:
        dm = R["full"].str.contains(dem, case=False, regex=True)
        rows.append({"아이디어": name, "HN요청글": int((dm & hnm).sum()), "Reddit요청글": int((dm & rdm).sum()),
                     "요청글 댓글합": int(R.loc[dm, "comments"].sum()),
                     "PH유사(346중)": int(ph_txt.str.contains(comp, case=False).sum()),
                     "ShowHN유사": int(show_txt.str.contains(comp, case=False).sum()),
                     "YC유사(24~26)": int(yc_txt.str.contains(comp, case=False).sum()), "난이도": diff,
                     "대표글": R.loc[dm].sort_values("comments", ascending=False)["title"].head(2).tolist()})
    idea = pd.DataFrame(rows)
    idea["수요점수"] = (idea["HN요청글"] + idea["Reddit요청글"] * 2 + idea["요청글 댓글합"] / 50).round(1)
    idea = idea.sort_values("수요점수", ascending=False)
    idea.to_csv(os.path.join(OUT, "idea_scores.csv"), index=False, encoding="utf-8-sig")
    F["demand"] = {
        "hn_ask_n": len(a), "hn_ask_period": [a["created"].min(), a["created"].max()], "hn_req_n": int(a["req"].sum()),
        "hn_strict_n": int(a["strict"].sum()), "reddit_n": len(r), "reddit_req_n": int(r["req"].sum()),
        "reddit_period": [r["created"].min(), r["created"].max()] if len(r) else None,
        "monthly": m.reset_index().to_dict("records"), "pain": pain.sort_values("합계", ascending=False).reset_index().to_dict("records"),
        "obj": obj.sort_values("합계", ascending=False).reset_index().to_dict("records"),
        "subs": sub.reset_index().to_dict("records"),
        "top_hn_strict": a[a["strict"]].assign(c=lambda x: pd.to_numeric(x["comments"])).sort_values("c", ascending=False)[["created", "title", "comments", "url"]].head(20).values.tolist(),
        "top_reddit_req": r[r["req"]][["sub", "created", "title", "url"]].head(40).values.tolist(),
        "show_n": len(s), "show_cat": sh.to_dict("records"),
        "show_top": s.sort_values("points", ascending=False)[["created", "points", "title"]].head(15).values.tolist(),
        "ideas": idea.to_dict("records")}


def main():
    yc(); ph(); gh(); demand()
    F["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(F, open(os.path.join(OUT, "findings.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("ok", list(F))


if __name__ == "__main__":
    main()
