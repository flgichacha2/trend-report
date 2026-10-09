# -*- coding: utf-8 -*-
"""
전체 파이프라인 (키 없이 DART 웹 공개페이지 사용)
  1) 목록 수집  2) 안건(소형 노드) 수집  3) 안건에 '사업목적' 언급 있는 회사만 대형 노드(정관 대비표) 수집
  4) 파싱  5) 집계
사용 예:
  python run_pipeline.py --tag 2026H1reg --start 20260101 --end 20260331
  python run_pipeline.py --tag 2025H1reg --start 20250101 --end 20250331
  python aggregate.py --tags 2026H1reg 2025H1reg 2026post 2025post
옵션 --skip-list : 이미 받은 목록 재사용
주의: 3)의 안건 문구 필터는 재현율이 낮음(표본에서 사업목적 변경 회사의 절반가량이 안건명에 '사업목적'을 쓰지 않음).
      전수 분석은 kind_collect.py(정관 섹션 전수 수집) 또는 opendart_api_collect.py 사용 권장.
"""
import argparse, os, subprocess, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
PY = sys.executable


def run(*args):
    print(">>", " ".join(args), flush=True)
    subprocess.run([PY, *args], cwd=HERE, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True); ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--report", default="주주총회소집공고")
    ap.add_argument("--workers", default="1")
    ap.add_argument("--skip-list", action="store_true")
    a = ap.parse_args()
    if not a.skip_list:
        run("dart_web_collect.py", "list", "--report", a.report, "--start", a.start, "--end", a.end, "--tag", a.tag)
    run("dart_web_collect.py", "fetch", "--tag", a.tag, "--workers", a.workers)
    run("parse_purposes.py", "--tag", a.tag, "--source", "dart")
    df = pd.read_csv(os.path.join(DATA, f"purposes_{a.tag}.csv"), dtype={"rcept_no": str})
    tgt = df[df.agenda_flag == True].rcept_no.tolist()  # noqa: E712
    tf = os.path.join(DATA, f"big_targets_{a.tag}.txt")
    open(tf, "w", encoding="utf-8").write("\n".join(tgt))
    print("big targets", len(tgt))
    run("dart_web_collect.py", "fetch", "--tag", a.tag, "--big", "--rcpfile", tf, "--workers", a.workers)
    run("parse_purposes.py", "--tag", a.tag, "--source", "dart")


if __name__ == "__main__":
    main()
