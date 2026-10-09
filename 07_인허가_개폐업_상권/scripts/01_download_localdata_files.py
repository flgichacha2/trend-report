# -*- coding: utf-8 -*-
"""
LOCALDATA(행정안전부 지방행정 인허가) 업종별 '전체 파일' 다운로드 + 경량화 저장.

- 출처: https://file.localdata.go.kr/file/{slug}/info  (공공데이터포털 파일데이터 '기관자체 다운로드' URL)
  로그인 불필요. 단, 브라우저 User-Agent가 없으면 403.
- 원본 CSV(cp949)는 스트리밍으로 임시 저장 -> 필요한 컬럼/행만 남겨 data/raw/localdata_file/{slug}.csv.gz 로 저장.
  행 필터: (현재 영업/휴업 중) OR (인허가일자 >= KEEP_FROM) OR (폐업일자 >= KEEP_FROM)
  -> 오래전에 폐업한 업소만 제외(최근 개·폐업 분석과 현재 재고 계산에는 영향 없음).
- 실행: python -I scripts/01_download_localdata_files.py [slug ...]
"""
import csv, gzip, io, json, os, sys, tempfile, time
from datetime import datetime

try:
    import truststore; truststore.inject_into_ssl()   # 사내 SSL 인증서 환경 대응
except Exception:
    pass
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "raw", "localdata_file")
os.makedirs(OUT, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
KEEP_FROM = "2019-01-01"

# slug -> 보고서용 업종명
TARGETS = {
    "general_restaurants": "일반음식점",
    "rest_cafes": "휴게음식점(카페 등)",
    "bakeries": "제과점영업",
    "karaoke_rooms": "노래연습장업",
    "fitness_centers": "체력단련장업",
    "pc_bangs": "인터넷컴퓨터게임시설제공업(PC방)",
    "lodgings": "숙박업",
    "beauty_salons": "미용업",
    "laundries": "세탁업",
    "animal_hospitals": "동물병원",
    "pet_grooming": "동물미용업",
    "animal_boarding": "동물위탁관리업",
    "food_vending_machines": "식품자동판매기업",
    "martial_arts_dojo": "체육도장업",
}

KEEP_COLS_EXACT = ["개방자치단체코드", "관리번호", "인허가일자", "인허가취소일자", "영업상태명",
                   "상세영업상태명", "폐업일자", "휴업시작일자", "휴업종료일자", "재개업일자",
                   "사업장명", "도로명주소", "지번주소", "소재지면적", "시설면적", "시설총규모",
                   "데이터갱신시점", "최종수정시점"]
KEEP_SUBSTR = ["업태구분명", "위생업태명", "업종명", "업종구분명"]


def keep_col(c):
    return c in KEEP_COLS_EXACT or any(s in c for s in KEEP_SUBSTR)


def download(slug):
    s = requests.Session()
    s.headers.update({"User-Agent": UA,
                      "Referer": f"https://file.localdata.go.kr/file/{slug}/info"})
    s.get(f"https://file.localdata.go.kr/file/{slug}/info", timeout=60)
    for attempt in range(5):
        r = s.get("https://file.localdata.go.kr/file/validate/download-count", timeout=60)
        if r.status_code == 429:
            print("  429 rate-limit, wait 60s", r.text[:80]); time.sleep(60); continue
        break
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    with s.get(f"https://file.localdata.go.kr/file/download/{slug}/info",
                stream=True, timeout=600) as r:
        r.raise_for_status()
        n = 0
        for chunk in r.iter_content(1 << 20):
            tmp.write(chunk); n += len(chunk)
    tmp.close()
    return tmp.name, n


def reduce(slug, path):
    stats = {"slug": slug, "name": TARGETS.get(slug, slug), "rows_total": 0, "rows_kept": 0,
             "downloaded_at": datetime.now().isoformat(timespec="seconds"),
             "source": f"https://file.localdata.go.kr/file/{slug}/info"}
    out = os.path.join(OUT, f"{slug}.csv.gz")
    max_lic = ""
    with open(path, encoding="cp949", errors="replace", newline="") as f, \
            gzip.open(out, "wt", encoding="utf-8", newline="") as g:
        rd = csv.reader(f)
        hdr = next(rd)
        idx = [i for i, c in enumerate(hdr) if keep_col(c)]
        cols = [hdr[i] for i in idx]
        stats["columns_all"] = hdr; stats["columns_kept"] = cols
        h = {c: i for i, c in enumerate(hdr)}
        w = csv.writer(g); w.writerow(cols)
        for row in rd:
            if len(row) < len(hdr):
                row += [""] * (len(hdr) - len(row))
            stats["rows_total"] += 1
            st = row[h["영업상태명"]] if "영업상태명" in h else ""
            lic = row[h["인허가일자"]] if "인허가일자" in h else ""
            clo = row[h["폐업일자"]] if "폐업일자" in h else ""
            if lic > max_lic and lic[:4] <= "2026":
                max_lic = lic
            alive = st not in ("폐업", "취소/말소/만료/정지/중지")
            if alive or lic >= KEEP_FROM or clo >= KEEP_FROM:
                w.writerow([row[i] for i in idx]); stats["rows_kept"] += 1
    stats["max_license_date"] = max_lic
    return stats


def main():
    slugs = sys.argv[1:] or list(TARGETS)
    meta_path = os.path.join(OUT, "_download_meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    for slug in slugs:
        print(f"[{slug}] downloading ...", flush=True)
        t0 = time.time()
        path, n = download(slug)
        print(f"  {n/1e6:.1f} MB in {time.time()-t0:.0f}s; reducing ...", flush=True)
        st = reduce(slug, path); st["bytes_original"] = n
        os.remove(path)
        meta[slug] = st
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  rows {st['rows_total']:,} -> kept {st['rows_kept']:,}; max 인허가일자 {st['max_license_date']}")
        time.sleep(5)


if __name__ == "__main__":
    main()
