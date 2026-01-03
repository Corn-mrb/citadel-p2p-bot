# Citadel P2P Bot

비트코인 P2P 거래 전광판 디스코드 봇

## 기능

- `/등록` - 새로운 P2P 거래 등록 (sats/원 단위 선택)
- `/전광판` - 등록된 거래 목록 확인
- `/내거래` - 내 거래 목록 확인
- `/수정` - 거래 수정
- `/삭제` - 거래 삭제
- `/전체삭제` - [관리자] 모든 거래 삭제
- `/강제삭제` - [관리자] 특정 거래 강제 삭제
- `/유저삭제` - [관리자] 특정 유저 거래 삭제

## 설치

### 1. 저장소 클론
```bash
git clone https://github.com/YOUR_USERNAME/citadel-p2p-bot.git
cd citadel-p2p-bot
```

### 2. 환경 변수 설정
```bash
cp .env.example .env
nano .env
```

`.env` 파일에 Discord Bot Token 입력:
```
DISCORD_TOKEN=your_bot_token_here
BOARD_CHANNEL_NAME=┆🌽ㅣcorn-전광판∶board
HELPER_ROLE_NAME=Helper
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 실행
```bash
python bot.py
```

## PM2로 실행 (권장)

```bash
# PM2 설치
npm install -g pm2

# 봇 시작
pm2 start bot.py --name citadel-p2p --interpreter python3

# 상태 확인
pm2 status

# 로그 확인
pm2 logs citadel-p2p

# 재시작
pm2 restart citadel-p2p

# 서버 재부팅 시 자동 시작
pm2 startup
pm2 save
```

## Discord Bot 설정

1. [Discord Developer Portal](https://discord.com/developers/applications) 접속
2. Bot 메뉴에서 다음 Intents 활성화:
   - MESSAGE CONTENT INTENT
   - SERVER MEMBERS INTENT
   - PRESENCE INTENT
3. OAuth2 → URL Generator에서:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: Send Messages, Embed Links, Read Message History

## 라이센스

MIT
