# -*- coding: utf-8 -*-
"""GitHub Actions 조회·실행 도우미 (gh CLI 대신, 사내 SSL 환경용).
토큰은 git 자격 증명 관리자(flgichacha2)에서 읽고 출력하지 않는다.

python -I -X utf8 tools/gh_actions.py status            최근 실행 5개 + 마지막 실행의 단계별 결과
python -I -X utf8 tools/gh_actions.py log [run_id]      실패 단계 로그(없으면 run 단계) 끝부분
python -I -X utf8 tools/gh_actions.py run [--send]      수동 실행 (기본: 미리보기, --send면 일정 무시 발송)
"""
import io, subprocess, sys, zipfile
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests

REPO = "flgichacha2/trend-report"
API = f"https://api.github.com/repos/{REPO}"


def token():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\nusername=flgichacha2\n\n",
                         capture_output=True, text=True, timeout=60).stdout
    t = dict(l.split("=", 1) for l in out.splitlines() if "=" in l).get("password")
    if not t:
        sys.exit("flgichacha2 자격 증명을 찾지 못했습니다.")
    return t


S = requests.Session()
S.headers.update({"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json"})


def get(path, **kw):
    r = S.get(API + path, timeout=60, **kw); r.raise_for_status(); return r


def status():
    runs = get("/actions/runs", params={"per_page": 5}).json()["workflow_runs"]
    for r in runs:
        print(f"#{r['run_number']} id={r['id']} {r['event']:<17} {r['status']:<11} {r['conclusion'] or '-':<9} {r['created_at']} {r['head_sha'][:7]}")
    if runs:
        jobs = get(f"/actions/runs/{runs[0]['id']}/jobs").json()["jobs"]
        for j in jobs:
            print(f"\n[job] {j['name']} {j['status']} {j['conclusion']}")
            for s in j["steps"]:
                print(f"   {s['number']:>2}. {s['conclusion'] or s['status']:<10} {s['name']}")
    return runs


def log(run_id=None):
    if not run_id:
        run_id = get("/actions/runs", params={"per_page": 1}).json()["workflow_runs"][0]["id"]
    z = zipfile.ZipFile(io.BytesIO(get(f"/actions/runs/{run_id}/logs").content))
    jobs = get(f"/actions/runs/{run_id}/jobs").json()["jobs"]
    failed = [s["name"] for j in jobs for s in j["steps"] if s["conclusion"] == "failure"]
    names = z.namelist()
    want = failed or ["갱신 + 텔레그램 발송"]
    for n in names:
        if any(w in n for w in want) or (not any(w in x for x in names for w in want) and n.count("/") == 0):
            txt = z.read(n).decode("utf-8", "replace").splitlines()
            print(f"===== {n} (끝 120줄)")
            print("\n".join(l[29:] if len(l) > 29 and l[4] == "-" else l for l in txt[-120:]))


def run(send=False, only=""):
    inputs = {"dry_run": not send, "force": send}
    if only:
        inputs["only"] = only
    r = S.post(API + "/actions/workflows/trend-report.yml/dispatches", timeout=60,
               json={"ref": "main", "inputs": inputs})
    print("실행 요청:", "성공" if r.status_code == 204 else f"실패 {r.status_code} {r.text[:200]}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status()
    elif cmd == "log":
        log(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "run":
        only = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--only=")), "")
        run("--send" in sys.argv, only)
