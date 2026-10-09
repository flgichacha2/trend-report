# -*- coding: utf-8 -*-
"""villa_analysis.py가 만든 텔레그램용 빌라 요약(data/villa_message.txt)을 출력. 네트워크 없음."""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
p = Path(__file__).resolve().parents[1] / "data" / "villa_message.txt"
if not p.exists():
    sys.exit("villa_message.txt 없음 — villa_analysis.py 먼저 실행")
print(p.read_text(encoding="utf-8").strip())
