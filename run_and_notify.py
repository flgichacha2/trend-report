# -*- coding: utf-8 -*-
"""7개 트렌드 과제를 갱신하고 요약을 텔레그램 방으로 보낸다.

발송 일정: START_DATE부터 DAILY_DAYS일 동안 매일, 그 이후에는 START_DATE와 같은 요일에 주 1회.
작업 스케줄러에는 '매일' 등록해 두면 발송일이 아닌 날은 바로 종료한다.

python -I run_and_notify.py                 일정에 따라 실행·발송
python -I run_and_notify.py --force         일정 무시하고 지금 실행·발송
python -I run_and_notify.py --dry-run       발송하지 않고 메시지만 화면 출력
python -I run_and_notify.py --only 3,6      일부 과제만
python -I run_and_notify.py --no-update     수집 생략(기존 스냅샷으로 요약만)
"""
import argparse, datetime as dt, os, subprocess, sys, time, pathlib
from dotenv import dotenv_values
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent
START_DATE = dt.date(2026, 10, 9)
DAILY_DAYS = 7
UPDATE_TIMEOUT = 45 * 60

TASKS = [
    ("1", "01_구인동향_잡코리아_사람인", "구인시장"),
    ("2", "02_크몽_숨고_의뢰분석", "크몽·숨고 의뢰"),
    ("3", "03_앱_크롬확장_순위분석", "인기 앱·크롬확장"),
    ("4", "04_DART_사업목적변경", "기업 신사업(DART)"),
    ("5", "05_IT기술스택_원티드_점핏", "IT 기술스택"),
    ("6", "06_아파트실거래가", "관심지역 아파트"),
    ("6+", "06_아파트실거래가", "관심지역 빌라", "villa_analysis.py", "villa_summary.py"),
    ("7", "07_인허가_개폐업_상권", "동네 가게 개·폐업"),
]

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
TODAY = dt.date.today()
LOG = LOG_DIR / f"{TODAY:%Y%m%d}.log"


def log(msg):
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_send_day(d):
    if d < START_DATE:
        return False
    if (d - START_DATE).days < DAILY_DAYS:
        return True
    return d.weekday() == START_DATE.weekday()


def send(text, token, chat, dry):
    if dry:
        print("-" * 40 + "\n" + text)
        return True
    for i in range(0, len(text), 4000):
        chunk = text[i:i + 4000]
        for attempt in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data={"chat_id": chat, "text": chunk, "disable_web_page_preview": True},
                                  timeout=30).json()
                if r.get("ok"):
                    break
                log(f"텔레그램 오류: {r.get('description')}")
            except Exception as e:
                log(f"텔레그램 예외: {type(e).__name__}")
            time.sleep(5)
        else:
            return False
        time.sleep(1)
    return True


HTML_CSS = """
:root{--bg:#f5f7f8;--surface:#fff;--fg:#16222b;--muted:#5b6b76;--line:#d9e1e6;--accent:#0e6e6b;--accent-soft:#e2f1ef}
@media (prefers-color-scheme:dark){:root{--bg:#0f1619;--surface:#162126;--fg:#e4ecef;--muted:#93a5ae;--line:#26363d;--accent:#5cc4bc;--accent-soft:#17312f;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 "IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:32px 18px 56px;display:grid;gap:28px}
h1{font-size:26px;margin:0;line-height:1.3}.sub{color:var(--muted);font-size:13px;margin:6px 0 0}
nav{display:flex;flex-wrap:wrap;gap:6px}nav a{font-size:13px;text-decoration:none;color:var(--fg);border:1px solid var(--line);background:var(--surface);padding:3px 10px;border-radius:999px}
section{display:grid;gap:12px}h2{font-size:19px;margin:0;padding-bottom:6px;border-bottom:2px solid var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.blk{padding:14px 16px;border-top:1px solid var(--line);margin-top:-1px;min-width:0}.blk+.blk{border-left:1px solid var(--line)}
.blk.todo{background:var(--accent-soft)}.k{font-size:12px;letter-spacing:.06em;color:var(--muted);font-weight:600;margin:0 0 6px}.todo .k{color:var(--accent)}
ul{margin:0;padding-left:18px;display:grid;gap:5px;font-size:14px}p.plain{margin:0;font-size:14px}.note{font-size:12px;color:var(--muted)}
.warn{border:1px solid var(--line);border-radius:10px;padding:12px 16px;background:var(--surface);font-size:14px}
"""
SECTION_KEYS = (("🔄", "무엇이 바뀌었나"), ("💡", "무슨 의미"), ("✅", "내가 할 일"), ("📊", "근거"))


def build_html(results, failed, header, label):
    import html as H
    esc = H.escape
    parts, nav = [], []
    for i, text in enumerate(results):
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        title = lines[0].lstrip("📌 ").strip() if lines else f"항목 {i + 1}"
        blocks, cur, notes = [], None, []
        for l in lines[1:]:
            head = next((k for k in SECTION_KEYS if l.startswith(k[0])), None)
            if head:
                rest = l[len(head[0]):].strip()
                cur = {"name": rest or head[1], "todo": head[0] == "✅", "items": []}
                blocks.append(cur)
                continue
            if l.startswith("※"):
                notes.append(l); continue
            item = l.lstrip("•·-– ").strip()
            if cur is None:
                cur = {"name": "요약", "todo": False, "items": []}; blocks.append(cur)
            cur["items"].append(item)
        sid = f"s{i}"
        nav.append(f'<a href="#{sid}">{esc(title.split(" (")[0])}</a>')
        body = "".join(
            f'<div class="blk{" todo" if b["todo"] else ""}"><p class="k">{esc(b["name"])}</p>'
            + ("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in b["items"]) + "</ul>" if b["items"] else "")
            + "</div>" for b in blocks)
        parts.append(f'<section id="{sid}"><h2>{esc(title)}</h2><div class="grid">{body}</div>'
                     + "".join(f'<p class="note">{esc(n)}</p>' for n in notes) + "</section>")
    if failed:
        parts.append('<div class="warn"><b>확인 필요</b><ul>' + "".join(f"<li>{esc(f)}</li>" for f in failed) + "</ul></div>")
    h1, *sub = header.splitlines()
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>트렌드 리포트 {TODAY:%Y-%m-%d}</title>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600;700&display=swap">'
            f'<style>{HTML_CSS}</style></head><body><div class="wrap"><header><h1>{esc(h1.lstrip("📊 "))}</h1>'
            f'<p class="sub">{esc(" ".join(sub))} · 투자·부동산 내용은 판단 재료이며 매수·매도 권유가 아님</p></header>'
            f'<nav>{"".join(nav)}</nav>{"".join(parts)}</div></body></html>')


def send_document(path, caption, token, chat, dry):
    if dry:
        print(f"[HTML 미리보기] {path}")
        return True
    for attempt in range(3):
        try:
            with open(path, "rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                                  data={"chat_id": chat, "caption": caption}, files={"document": f}, timeout=60).json()
            if r.get("ok"):
                return True
            log(f"텔레그램 파일 오류: {r.get('description')}")
        except Exception as e:
            log(f"텔레그램 파일 예외: {type(e).__name__}")
        time.sleep(5)
    return False


def run_py(folder, script, timeout):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, "-I", "-X", "utf8", f"scripts/{script}"], cwd=folder, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def prune_dart_cache(keep_runs=3):
    """DART 공시 원문 캐시: 받은 날짜(수정일) 기준 최근 keep_runs회 실행분만 남긴다.
    예) 1·2·3일차에 받았으면 4일차 실행 후 1일차에 받은 파일 삭제 (이번 + 직전 2회 보관)."""
    files = []
    for d in ("kind", "html", "api_xml"):
        folder = ROOT / "04_DART_사업목적변경" / "data" / d
        if folder.is_dir():
            files += [f for f in folder.iterdir() if f.is_file()]
    day = lambda f: dt.date.fromtimestamp(f.stat().st_mtime)
    days = sorted({day(f) for f in files}, reverse=True)
    if len(days) <= keep_runs:
        return
    cutoff = days[keep_runs - 1]
    n = 0
    for f in files:
        if day(f) < cutoff:
            f.unlink(); n += 1
    log(f"DART 원문 캐시 {n}개 삭제 ({cutoff} 이전에 받은 파일)")


def keep_awake():
    """Windows: 실행하는 동안 절전 진입 막기(작업 스케줄러가 절전에서 깨운 경우 다시 잠드는 것 방지)."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        except Exception:
            pass


def main():
    keep_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--no-update", action="store_true")
    ap.add_argument("--label", default="", help="머리말·발송기록 구분용 (예: PC, GitHub)")
    a = ap.parse_args()

    if not a.force and not is_send_day(TODAY):
        log(f"{TODAY} 발송일 아님 — 종료")
        return
    sent_flag = LOG_DIR / f"sent_{TODAY:%Y%m%d}{'_' + a.label if a.label else ''}.flag"
    if sent_flag.exists() and not a.force and not a.dry_run:
        log("오늘 이미 발송함 — 종료")
        return

    env = {**dotenv_values(ROOT / ".env"),
           **{k: v for k, v in os.environ.items() if k.startswith("TELEGRAM_") and v}}  # GitHub Secrets 지원
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if not a.dry_run and not (token and chat):
        sys.exit(".env에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 넣으세요.")

    only = set(a.only.split(",")) if a.only else None
    mode = "매일" if (TODAY - START_DATE).days < DAILY_DAYS else "주간"
    results, failed = [], []
    for no, name, title, *scr in TASKS:
        upd_py, sum_py = scr if scr else ("daily_update.py", "telegram_summary.py")
        if only and no not in only:
            continue
        folder = ROOT / name
        if not (folder / "scripts" / sum_py).exists():
            log(f"[{no}] 요약 스크립트 없음 — 건너뜀")
            failed.append(f"[{no}] {title}: 준비 중")
            continue
        if not a.no_update and (folder / "scripts" / upd_py).exists():
            t0 = time.time()
            try:
                p = run_py(folder, upd_py, UPDATE_TIMEOUT)
                log(f"[{no}] 갱신 종료코드 {p.returncode} ({time.time() - t0:.0f}초)")
                if p.returncode != 0:
                    log(p.stderr[-1500:])
                    failed.append(f"[{no}] {title}: 갱신 실패(이전 데이터로 요약)")
            except subprocess.TimeoutExpired:
                log(f"[{no}] 갱신 시간 초과")
                failed.append(f"[{no}] {title}: 갱신 시간 초과(이전 데이터로 요약)")
        try:
            p = run_py(folder, sum_py, 300)
            text = p.stdout.strip()
            if p.returncode == 0 and text:
                results.append(text)
            else:
                log(f"[{no}] 요약 실패: {p.stderr[-800:]}")
                failed.append(f"[{no}] {title}: 요약 실패")
        except subprocess.TimeoutExpired:
            failed.append(f"[{no}] {title}: 요약 시간 초과")

    header = f"📊 트렌드 리포트 {TODAY:%Y-%m-%d} ({mode}{' · ' + a.label if a.label else ''})\n총 {len(results)}개 항목"
    if mode == "매일":
        left = DAILY_DAYS - (TODAY - START_DATE).days - 1
        header += f" · 매일 발송 {left}일 남음, 이후 매주 {'월화수목금토일'[START_DATE.weekday()]}요일"
    ok = send(header, token, chat, a.dry_run)
    for text in results:
        ok = send(text, token, chat, a.dry_run) and ok
    if failed:
        ok = send("⚠️ 확인 필요\n" + "\n".join(failed), token, chat, a.dry_run) and ok
    if results:
        html_path = LOG_DIR / f"트렌드리포트_{TODAY:%Y%m%d}{'_' + a.label if a.label else ''}.html"
        html_path.write_text(build_html(results, failed, header, a.label), encoding="utf-8")
        ok = send_document(html_path, f"📎 {TODAY:%m/%d} 리포트 웹페이지 버전 (파일을 열면 브라우저에서 보여요)",
                           token, chat, a.dry_run) and ok
    try:
        prune_dart_cache()
    except Exception as e:
        log(f"DART 캐시 정리 실패: {type(e).__name__}")
    log(f"발송 {'완료' if ok else '일부 실패'}: 요약 {len(results)}건, 문제 {len(failed)}건")
    if ok and not a.dry_run:
        sent_flag.write_text(dt.datetime.now().isoformat(), encoding="utf-8")


if __name__ == "__main__":
    main()
