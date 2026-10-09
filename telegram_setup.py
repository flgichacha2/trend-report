# -*- coding: utf-8 -*-
"""텔레그램 봇 설정 도우미.
python -I telegram_setup.py          : 봇이 들어가 있는 방 목록과 chat_id 출력
python -I telegram_setup.py --test   : .env의 TELEGRAM_CHAT_ID로 테스트 메시지 1건 발송
"""
import sys, pathlib
from dotenv import dotenv_values
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import requests

ROOT = pathlib.Path(__file__).resolve().parent
env = dotenv_values(ROOT / ".env")
token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
if not token:
    sys.exit(".env에 TELEGRAM_BOT_TOKEN을 먼저 넣으세요.")
api = f"https://api.telegram.org/bot{token}"

if "--test" in sys.argv:
    chat = (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if not chat:
        sys.exit(".env에 TELEGRAM_CHAT_ID를 먼저 넣으세요.")
    r = requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": "✅ 트렌드 리포트 봇 연결 테스트입니다."}, timeout=30).json()
    print("발송 성공" if r.get("ok") else f"실패: {r.get('description')}")
    sys.exit()

me = requests.get(f"{api}/getMe", timeout=30).json()
if not me.get("ok"):
    sys.exit(f"토큰 오류: {me.get('description')}")
print(f"봇: @{me['result']['username']}")
upd = requests.get(f"{api}/getUpdates", timeout=30).json().get("result", [])
chats = {}
for u in upd:
    for key in ("message", "my_chat_member", "channel_post", "edited_message"):
        c = (u.get(key) or {}).get("chat")
        if c:
            chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name")
if not chats:
    print("방을 찾지 못했습니다. 봇을 방에 초대한 뒤 방에 메시지를 하나 보내고 다시 실행하세요.\n"
          "(그룹이면 @BotFather → /setprivacy → Disable 도 필요할 수 있습니다)")
for cid, title in chats.items():
    print(f"chat_id={cid}\t{title}")
