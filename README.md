# trend-report (비공개)

3·4·6·7번 트렌드(앱·크롬확장 순위, DART 사업목적, 관심지역 아파트·빌라, 인허가 개·폐업)를
매일 한국시간 20:30에 GitHub Actions로 갱신하고 텔레그램 가족방으로 보낸다.
발송 일정: 2026-10-09~10-15 매일, 이후 매주 금요일 (run_and_notify.py의 START_DATE/DAILY_DAYS).
1·2·5번(국내 채용·외주 사이트 크롤링)은 해외 IP 차단 우려로 PC 작업 스케줄러에서 20:30 실행.

필요한 Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MOLIT_API_KEY, LOCALDATA_API_KEY, DART_API_KEY
수동 실행: Actions → trend-report → Run workflow (force 체크 시 즉시 발송)
