@echo off
REM 매일 1회 실행용 (Windows 작업 스케줄러에 등록)
REM 앱 순위 수집 -> 순위변화 리포트 -> (주 1회 권장) 크롬 확장 목록 수집
chcp 65001 >nul
set PYTHONIOENCODING=utf8
cd /d "%~dp0"
python daily_collect.py >> ..\data\daily_log.txt 2>&1
python diff_report.py >> ..\data\daily_log.txt 2>&1
REM 크롬 확장 목록은 하루 1회 가볍게(리뷰 제외). 리뷰까지는 주 1회: python chrome_collect.py
python chrome_collect.py --no-reviews >> ..\data\daily_log.txt 2>&1
