# -*- coding: utf-8 -*-
"""
제주 영어교육도시 보완: 대정읍(법정동 5013025000)의 아파트(A)+연립/다세대(B) 단지 중
구억리·보성리·신평리·안성리 소재 단지의 2024~2026 매매 거래를 단지별 조회로 수집.
(영어교육도시 주변 주거는 5층 미만 연립·다세대/타운하우스가 많아 아파트만으로는 거래가 잡히지 않음)
결과: data/jeju_edu_town_trades.csv
"""
import time, pandas as pd
from fetch_rt_danji import session, danji_list, danji_trades
from common import DATA, PYEONG

LED = "5013025000"
RI = ("구억리", "보성리", "신평리", "안성리")
s = session(); rows = []; seen = set()
for thing, label in (("A", "아파트"), ("B", "연립다세대")):
    for y in ("2024", "2025", "2026"):
        for dj in danji_list(s, LED, y, thing):
            if not dj["ledNm"].endswith(RI):
                continue
            key = (thing, dj["aprpnHsmpCode"], y)
            if key in seen: continue
            seen.add(key)
            for t in danji_trades(s, dj["aprpnHsmpCode"], y, thing):
                rows.append({"유형": label, "리": dj["ledNm"].split()[-1], "단지": dj["aprpnHsmpNm"], "번지": dj["mnnm"],
                             "계약일": t["cntrctDe"], "ym": t["cntrctDe"][:6], "전용㎡": float(t["prvuseAr"]),
                             "거래가(만원)": int(t["thingAmount"].replace(",", "")), "층": t.get("floorCo"),
                             "해제": t.get("relisDe"), "거래유형": t.get("brkrAt")})
            time.sleep(0.4)
df = pd.DataFrame(rows).drop_duplicates()
df = df[df["ym"] >= "202410"]
df["평당(만원)"] = (df["거래가(만원)"] / df["전용㎡"] * PYEONG).round(0)
df.to_csv(DATA / "jeju_edu_town_trades.csv", index=False, encoding="utf-8-sig")
print(len(df)); print(df.groupby(["유형", "리"]).size())
