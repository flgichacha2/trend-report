# -*- coding: utf-8 -*-
"""메일 발송만 시험 (텔레그램 발송 없음). 환경변수 EMAIL_TO / EMAIL_SMTP_USER / EMAIL_APP_PASSWORD 사용."""
import os, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_and_notify as R

env = {k: v for k, v in os.environ.items() if k.startswith("EMAIL_")}
print("설정:", {k: ("있음" if env.get(k) else "없음") for k in ("EMAIL_TO", "EMAIL_SMTP_USER", "EMAIL_APP_PASSWORD")})
R.send_email("[트렌드 리포트] GitHub 시험 메일",
             "GitHub Actions(해외 서버)에서 보낸 메일 발송 시험입니다.\n이 메일이 오면 GitHub 발송분(3·4·6·7·8·10·13번)도 메일로 함께 옵니다.",
             None, env, False)
log = (R.LOG_DIR / f"{R.TODAY:%Y%m%d}.log")
last = log.read_text(encoding="utf-8").strip().splitlines()[-1] if log.exists() else ""
print(last)
sys.exit(0 if "메일 발송 완료" in last else 1)
