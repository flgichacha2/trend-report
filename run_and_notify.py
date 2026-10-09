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


def run_py(folder, script, timeout):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, "-I", "-X", "utf8", f"scripts/{script}"], cwd=folder, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def main():
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
    log(f"발송 {'완료' if ok else '일부 실패'}: 요약 {len(results)}건, 문제 {len(failed)}건")
    if ok and not a.dry_run:
        sent_flag.write_text(dt.datetime.now().isoformat(), encoding="utf-8")


if __name__ == "__main__":
    main()
