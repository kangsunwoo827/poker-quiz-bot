# 🃏 SunPokerQuizBot

GTO 기반 포커 퀴즈 텔레그램 봇

## Features

- 📝 GTO solver 기반 50+ 포커 문제
- ⏰ 2시간마다 자동 출제
- 🎯 버튼 클릭으로 간편 답변
- 💬 즉시 정답 DM + 5분 후 상세 해설
- 📊 점수 기록 & 리더보드
- 🔥 스트릭 시스템

## Commands

- `/start` - 봇 시작
- `/quiz` - 새 퀴즈 출제
- `/score` - 내 점수 확인
- `/leaderboard` - 순위표
- `/help` - 도움말

## Setup

1. Copy config:
```bash
cp config.example .config
```

2. Edit `.config` with your bot token:
```
TELEGRAM_BOT_TOKEN=your_token_here
BOT_NAME=YourBotName
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run:
```bash
python bot/main.py
```

## Question Format

```json
{
  "id": 1,
  "type": "postflop",
  "situation": "Cash 6-max, 100bb effective...",
  "hand": "A♠A♣",
  "options": ["Check", "Bet 33%", "Bet 75%"],
  "answer": 2,
  "explanation": "왜 75% bet인가?...",
  "terms": {
    "dry board": "드로우가 없는 보드"
  }
}
```

## License

MIT
