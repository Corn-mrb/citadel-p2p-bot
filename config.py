import os
from dotenv import load_dotenv

load_dotenv()

# Discord 설정
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOARD_CHANNEL_NAME = os.getenv("BOARD_CHANNEL_NAME", "┆🌽ㅣcorn-전광판∶board")
HELPER_ROLE_NAME = os.getenv("HELPER_ROLE_NAME", "Helper")

# 데이터 파일 경로
DATA_FILE = "data/trades.json"
