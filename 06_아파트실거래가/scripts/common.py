# -*- coding: utf-8 -*-
"""공통 설정: 관심지역 정의, 경로, 표준 컬럼."""
from pathlib import Path

try:  # 사내망/프록시 환경에서 Windows 인증서 저장소 사용
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
RAW = DATA / "raw"
CHARTS = BASE / "charts"
for p in (DATA, RAW, CHARTS):
    p.mkdir(parents=True, exist_ok=True)

# 시군구(LAWD_CD 5자리) 단위로 수집 후 읍면동으로 필터링
SGG = {
    "50130": {"sido": "50000", "name": "제주 서귀포시"},
    # 2026-07-01 인천 행정체제 개편으로 중구(28110) 폐지 -> 영종도는 영종구(28155). 공개시스템도 소급 재코드됨
    "28155": {"sido": "28000", "name": "인천 영종구(구 중구 영종지역)"},
    "41135": {"sido": "41000", "name": "성남 분당구"},
    "11680": {"sido": "11000", "name": "서울 강남구"},
}

# 관심지역: (이름, 시군구코드, 읍면동 필터(None이면 시군구 전체), 리 필터)
REGIONS = [
    # 구억·보성·신평리는 24개월간 '아파트' 매매 0건 -> 연립·다세대(타운하우스형) 거래로 대체 (jeju_edu_town.py)
    {"key": "jeju_edu", "name": "제주 영어교육도시 연립·다세대(대정읍 구억·보성·신평·안성리)", "sgg": "50130B",
     "emd": None, "ri": None},
    {"key": "jeju_daejeong", "name": "(참고) 서귀포 대정읍 아파트 전체", "sgg": "50130", "emd": ["대정읍"], "ri": None},
    {"key": "yeongjong", "name": "영종도(중산·운서·운남·운북동)", "sgg": "28155",
     "emd": ["중산동", "운서동", "운남동", "운북동"], "ri": None},
    {"key": "yatap", "name": "분당 야탑동", "sgg": "41135", "emd": ["야탑동"], "ri": None},
    {"key": "pangyo", "name": "판교(삼평·백현·판교·운중동)", "sgg": "41135",
     "emd": ["삼평동", "백현동", "판교동", "운중동"], "ri": None},
    {"key": "bundang", "name": "(참고) 분당구 전체", "sgg": "41135", "emd": None, "ri": None},
    {"key": "gangnam", "name": "서울 강남구", "sgg": "11680", "emd": None, "ri": None},
]

# 표준 컬럼 (공개시스템 CSV / 공공데이터 API 모두 이 스키마로 정규화)
STD_COLS = ["sgg_cd", "sigungu", "emd", "ri", "jibun", "apt", "area_m2", "ym", "day",
            "price_manwon", "dong", "floor", "build_year", "road", "cancel_date", "deal_type"]

PYEONG = 3.305785  # 1평 = 3.305785㎡
