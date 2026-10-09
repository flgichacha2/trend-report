# -*- coding: utf-8 -*-
"""공통 로더: data/raw/localdata_file/{slug}.csv.gz -> 정제 DataFrame"""
import os, re
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw", "localdata_file")

NAMES = {
    "general_restaurants": "일반음식점",
    "rest_cafes": "휴게음식점",
    "bakeries": "제과점",
    "karaoke_rooms": "노래연습장",
    "fitness_centers": "체력단련장",
    "pc_bangs": "PC방",
    "lodgings": "숙박업",
    "beauty_salons": "미용업",
    "laundries": "세탁업",
    "animal_hospitals": "동물병원",
    "pet_grooming": "동물미용업",
    "animal_boarding": "동물위탁관리업",
    "food_vending_machines": "식품자동판매기업",
    "martial_arts_dojo": "체육도장업",
}

SIDO_NORM = {
    "서울특별시": "서울", "서울시": "서울", "서울": "서울",
    "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "전남광주", "전라남도": "전남광주", "전남광주통합특별시": "전남광주",
    "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}
CODE_SIDO = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
             "전남광주통합특별시": "전남광주", "대전광역시": "대전", "울산광역시": "울산",
             "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "충청북도": "충북",
             "충청남도": "충남", "전북특별자치도": "전북", "경상북도": "경북", "경상남도": "경남",
             "제주특별자치도": "제주"}
# 옛 인천 중구 중 영종도 지역 법정동
YEONGJONG_DONG = ["운서동", "중산동", "운남동", "운북동", "을왕동", "남북동", "덕교동", "무의동", "영종동"]


def _orgmap():
    p = os.path.join(RAW, "_orgcodes.csv")
    if not os.path.exists(p):
        return {}, {}
    o = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
    return dict(zip(o["개방자치단체코드"], o["시도"].map(CODE_SIDO))), dict(zip(o["개방자치단체코드"], o["기관명"]))


def load(slug):
    df = pd.read_csv(os.path.join(RAW, f"{slug}.csv.gz"), dtype=str, keep_default_na=False)
    df["업종"] = NAMES.get(slug, slug)
    df["lic"] = pd.to_datetime(df["인허가일자"].str[:10], errors="coerce")
    df["clo"] = pd.to_datetime(df["폐업일자"].str[:10], errors="coerce")
    df["is_closed"] = df["영업상태명"].eq("폐업")
    df["is_alive"] = df["영업상태명"].isin(["영업/정상", "휴업"])
    addr = df["도로명주소"].where(df["도로명주소"].str.strip() != "", df["지번주소"]).fillna("")
    df["addr"] = addr
    tok = addr.str.split()
    t0 = tok.str[0].fillna(""); t1 = tok.str[1].fillna(""); t2 = tok.str[2].fillna("")
    code_sido, code_nm = _orgmap()
    sido = t0.map(SIDO_NORM)
    sido = sido.fillna(df["개방자치단체코드"].map(code_sido))
    df["시도"] = sido.fillna("미상")
    sgg = t1.where(~(t1.str.endswith("시") & t2.str.endswith("구")), t1 + " " + t2)
    df["시군구"] = sgg
    df["기관명"] = df["개방자치단체코드"].map(code_nm).fillna("")
    # 관심지역
    area = pd.Series("", index=df.index)
    area[(df["시도"] == "서울") & (t1 == "강남구")] = "서울 강남구"
    area[addr.str.contains("성남시 분당구", regex=False)] = "성남 분당구"
    yj = (df["시도"] == "인천") & ((t1 == "영종구") |
                                  ((t1 == "중구") & addr.str.contains("|".join(YEONGJONG_DONG))) |
                                  (df["개방자치단체코드"] == "3491000"))
    area[yj] = "인천 영종(옛 중구)"
    area[addr.str.contains("서귀포시", regex=False)] = "제주 서귀포시"
    df["관심지역"] = area
    # 업태 컬럼 통일
    for c in ["업태구분명", "위생업태명", "문화체육업종명", "업종구분명"]:
        if c in df.columns:
            df["업태"] = df[c]; break
    else:
        df["업태"] = ""
    df["영업년수"] = (df["clo"] - df["lic"]).dt.days / 365.25
    # 인허가 후 60일 이내 폐업 = 팝업·행사·'(한시적)' 등 단기 영업으로 간주
    df["short"] = df["is_closed"] & ((df["clo"] - df["lic"]).dt.days <= 60)
    return df
