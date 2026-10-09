"""저평점 리뷰 불만유형 키워드 사전(한국어+영어). 한 리뷰가 여러 유형에 걸릴 수 있음."""
import re

TAXONOMY = {
    "광고과다": ["광고", "ads", "advert", "팝업", "popup", "pop-up", "리워드 광고"],
    "결제·구독·환불": ["결제", "구독", "환불", "유료", "요금", "가격", "비싸", "돈 ", "과금", "자동결제", "해지", "프리미엄",
                   "subscription", "refund", "paywall", "charge", "price", "expensive", "billing", "pay "],
    "오류·버그·튕김": ["오류", "에러", "버그", "튕", "강제종료", "먹통", "안 열", "안열", "실행이 안", "안됨", "안돼", "안 돼", "안되",
                   "작동", "충돌", "crash", "bug", "error", "not working", "doesn't work", "broken", "freez", "glitch"],
    "느림·성능·배터리": ["느려", "느림", "느리", "버벅", "렉", "로딩", "배터리", "발열", "무거", "slow", "lag", "loading", "battery"],
    "로그인·인증": ["로그인", "인증", "본인확인", "비밀번호", "계정", "로그아웃", "아이디", "login", "log in", "sign in", "account", "verify", "otp"],
    "업데이트·UI 개악": ["업데이트", "업뎃", "개편", "바뀐", "바꿔", "바꾼", "디자인", "ui", "불편", "예전", "이전 버전", "원래대로", "되돌",
                     "update", "redesign", "new version", "interface"],
    "AI 품질·제한": ["답변", "거짓", "틀린", "헛소리", "환각", "제한", "한도", "메시지 수", "검열", "멍청", "기억", "맥락", "정확",
                  "limit", "hallucin", "wrong answer", "censor", "dumb", "context", "accuracy", "rate limit"],
    "개인정보·권한": ["개인정보", "권한", "프라이버시", "추적", "해킹", "보안", "privacy", "permission", "tracking", "data"],
    "고객센터·대응": ["고객센터", "상담", "문의", "답변이 없", "응대", "cs ", "support", "customer service", "no response"],
    "기능 부족·요청": ["기능", "추가해", "추가 해", "있었으면", "없어서", "지원 안", "지원하지", "안 돼서", "pc", "컴퓨터", "웹",
                   "feature", "please add", "wish", "missing", "desktop", "browser"],
    "콘텐츠·데이터 문제": ["콘텐츠", "에피소드", "번역 품질", "자막", "화질", "음질", "동기화", "sync", "백업", "저장이 안", "사라", "삭제",
                      "content", "episode", "quality", "lost", "deleted"],
    "배송·주문·판매자": ["배송", "주문", "판매자", "반품", "교환", "취소", "택배", "delivery", "order", "seller", "return"],
}

_PAT = {k: re.compile("|".join(re.escape(w) for w in v), re.I) for k, v in TAXONOMY.items()}


def classify(text: str):
    t = text or ""
    hits = [k for k, p in _PAT.items() if p.search(t)]
    return hits or ["기타·불명확"]
