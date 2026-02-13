import discord
from discord import app_commands
from discord.app_commands import checks
from discord.ui import Modal, TextInput, View, Button
import json
import os
from datetime import datetime
from config import DISCORD_TOKEN, BOARD_CHANNEL_NAME, HELPER_ROLE_NAME, DATA_FILE
import re
import math
import tempfile
import shutil

# Intents 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ 너무 빠릅니다! **{error.retry_after:.1f}초** 후에 다시 시도해주세요.",
            ephemeral=True
        )
    else:
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ 명령어 처리 중 오류가 발생했습니다.",
                ephemeral=True
            )

# ============== 데이터 관리 ==============
def load_trades():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_trades(data):
    """Atomic write: 임시 파일에 쓴 후 rename으로 교체"""
    dir_name = os.path.dirname(DATA_FILE)
    os.makedirs(dir_name, exist_ok=True)
    
    # 같은 디렉토리에 임시 파일 생성
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp", prefix="trades_")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # 기존 파일 백업 (최근 3개 유지)
        if os.path.exists(DATA_FILE):
            backup_dir = os.path.join(dir_name, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup_name = f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_path = os.path.join(backup_dir, backup_name)
            shutil.copy2(DATA_FILE, backup_path)
            
            # 오래된 백업 정리 (최근 3개만 유지)
            backups = sorted(
                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith('.json')],
                key=os.path.getmtime
            )
            while len(backups) > 3:
                os.unlink(backups.pop(0))
        
        # Atomic rename
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

trades = load_trades()

# ============== 입력 검증 ==============
AMOUNT_LIMITS = {
    "sats": {"min": 1_000, "max": 100_000_000, "display": "1,000 ~ 100,000,000 sats"},
    "won": {"min": 1_000, "max": 100_000_000, "display": "1,000 ~ 100,000,000 원"}
}
PREMIUM_MIN = -50.0
PREMIUM_MAX = 100.0
NOTE_MAX_LENGTH = 200

def sanitize_note(raw: str) -> str:
    """메모 필드 정제: 마크다운/멘션 무효화"""
    if not raw or not raw.strip():
        return ""
    text = raw.strip()
    text = text.replace("@everyone", "@\u200beveryone")
    text = text.replace("@here", "@\u200bhere")
    text = re.sub(r'<(@[!&]?\d+|#\d+)>', r'`\1`', text)
    text = text.replace("```", "\\`\\`\\`")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def validate_trade_input(amount_raw: str, premium_raw: str, note_raw: str, unit: str):
    """거래 입력값 검증"""
    errors = []
    
    # 수량 검증
    amount_cleaned = amount_raw.strip().replace(",", "").replace(" ", "")
    try:
        amount_num = int(amount_cleaned)
    except (ValueError, OverflowError):
        errors.append("• **수량**: 숫자만 입력해주세요. (예: 100000 또는 100,000)")
        amount_num = None
    
    if amount_num is not None:
        limits = AMOUNT_LIMITS.get(unit)
        if limits is None:
            errors.append(f"• **단위**: 알 수 없는 단위입니다: {unit}")
        else:
            if amount_num <= 0:
                errors.append("• **수량**: 수량은 양수여야 합니다.")
            elif amount_num < limits["min"]:
                errors.append(f"• **수량**: 최소 수량은 {limits['display']}입니다.")
            elif amount_num > limits["max"]:
                errors.append(f"• **수량**: 최대 수량은 {limits['display']}입니다.")
    
    # 프리미엄 검증
    premium_cleaned = premium_raw.strip().replace("%", "").replace(" ", "")
    try:
        premium_num = float(premium_cleaned)
    except (ValueError, OverflowError):
        errors.append("• **프리미엄**: 숫자만 입력해주세요. (예: 5 또는 -3.5)")
        premium_num = None
    
    if premium_num is not None:
        if math.isinf(premium_num) or math.isnan(premium_num):
            errors.append("• **프리미엄**: 유효한 숫자를 입력해주세요.")
        elif premium_num < PREMIUM_MIN:
            errors.append(f"• **프리미엄**: 프리미엄은 {PREMIUM_MIN}% 이상이어야 합니다.")
        elif premium_num > PREMIUM_MAX:
            errors.append(f"• **프리미엄**: 프리미엄은 {PREMIUM_MAX}% 이하여야 합니다.")
    
    # 메모 정제
    note_clean = sanitize_note(note_raw)
    if len(note_clean) > NOTE_MAX_LENGTH:
        errors.append(f"• **메모**: 메모는 {NOTE_MAX_LENGTH}자 이하로 입력해주세요. (현재: {len(note_clean)}자)")
    
    if errors:
        return None, "❌ 입력값을 확인해주세요:\n" + "\n".join(errors)
    
    return (amount_num, round(premium_num, 2) if premium_num is not None else 0, note_clean), None

# ============== 권한 체크 ==============
def is_admin_or_helper(user):
    has_helper = any(role.name == HELPER_ROLE_NAME for role in user.roles)
    return user.guild_permissions.administrator or has_helper

# ============== 헬퍼 함수 ==============
def get_user_trades(user_id):
    return [(i, t) for i, t in enumerate(trades) if t["user_id"] == user_id]

def build_my_trades_embed(user_trades):
    embed = discord.Embed(title="📋 내 거래 목록", color=discord.Color.blue())
    for num, (idx, t) in enumerate(user_trades):
        emoji = "⚡" if t["method"] == "라이트닝" else "🔗"
        note = f"\n비고: {t['note']}" if t.get('note') else ""
        embed.add_field(
            name=f"{num+1}. {t['trade_type']} {emoji} {t['method']}",
            value=f"수량: {t['amount_formatted']}\n프리미엄: {t['premium']}%{note}",
            inline=False
        )
    return embed

# ============== 등록 UI ==============
class UnitSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🪙 sats로 거래", style=discord.ButtonStyle.primary)
    async def sats_button(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📋 거래 유형 선택", description="판매 / 구매를 선택해주세요:", color=discord.Color.blue()),
            view=TradeTypeView("sats")
        )

    @discord.ui.button(label="💵 원으로 거래", style=discord.ButtonStyle.success)
    async def won_button(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📋 거래 유형 선택", description="판매 / 구매를 선택해주세요:", color=discord.Color.blue()),
            view=TradeTypeView("원")
        )

class TradeTypeView(View):
    def __init__(self, unit: str):
        super().__init__(timeout=60)
        self.unit = unit

    @discord.ui.button(label="🔴 판매", style=discord.ButtonStyle.danger)
    async def sell_button(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="⚡ 거래 방식 선택", description="라이트닝 / 온체인을 선택해주세요:", color=discord.Color.blue()),
            view=MethodSelectView(self.unit, "판매")
        )

    @discord.ui.button(label="🟢 구매", style=discord.ButtonStyle.success)
    async def buy_button(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="⚡ 거래 방식 선택", description="라이트닝 / 온체인을 선택해주세요:", color=discord.Color.blue()),
            view=MethodSelectView(self.unit, "구매")
        )

class MethodSelectView(View):
    def __init__(self, unit: str, trade_type: str):
        super().__init__(timeout=60)
        self.unit = unit
        self.trade_type = trade_type

    @discord.ui.button(label="⚡ 라이트닝", style=discord.ButtonStyle.primary)
    async def lightning_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(TradeModal(self.unit, self.trade_type, "라이트닝"))

    @discord.ui.button(label="🔗 온체인", style=discord.ButtonStyle.secondary)
    async def onchain_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(TradeModal(self.unit, self.trade_type, "온체인"))

class TradeModal(Modal):
    def __init__(self, unit: str, trade_type: str, method: str):
        super().__init__(title=f"{trade_type} | {method} | {unit}")
        self.unit = unit
        self.trade_type = trade_type
        self.method = method

        self.amount = TextInput(label=f"수량 ({unit})", placeholder="예: 1000000", required=True, max_length=20)
        self.premium = TextInput(label="프리미엄 (%)", placeholder="예: 1.5", required=True, max_length=10)
        self.note = TextInput(label="비고", placeholder="예: 월오사, 스피드 가능", required=False, max_length=100, style=discord.TextStyle.paragraph)

        for item in [self.amount, self.premium, self.note]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        result, error_msg = validate_trade_input(
            self.amount.value,
            self.premium.value,
            self.note.value if self.note.value else "",
            self.unit
        )
        
        if error_msg or result is None:
            return await interaction.response.send_message(error_msg or "❌ 입력값 검증 실패", ephemeral=True)
        
        amount_num, premium, note_clean = result
        
        trade = {
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name,
            "trade_type": self.trade_type,
            "method": self.method,
            "unit": self.unit,
            "amount": amount_num,
            "amount_formatted": f"{amount_num:,} {self.unit}",
            "premium": premium,
            "note": note_clean,
            "timestamp": datetime.now().isoformat()
        }

        trades.append(trade)
        save_trades(trades)
        await interaction.response.send_message(
            f"✅ 거래가 등록되었습니다!\n**{self.trade_type}** | {self.method} | {trade['amount_formatted']} | 프리미엄 {premium:+.2f}%",
            ephemeral=True
        )

# ============== 내 거래 관리 UI ==============
class MyTradesView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        user_trades = get_user_trades(user_id)

        for num, (trade_idx, trade) in enumerate(user_trades[:5]):
            edit_btn = Button(label=f"수정 {num+1}", style=discord.ButtonStyle.primary, row=num)
            delete_btn = Button(label=f"삭제 {num+1}", style=discord.ButtonStyle.danger, row=num)
            edit_btn.callback = self._make_edit_callback(trade_idx)
            delete_btn.callback = self._make_delete_callback(trade_idx)
            self.add_item(edit_btn)
            self.add_item(delete_btn)

    def _make_edit_callback(self, trade_idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ 본인의 거래만 수정할 수 있습니다.", ephemeral=True)
            if trade_idx >= len(trades) or trades[trade_idx]["user_id"] != self.user_id:
                return await interaction.response.send_message("❌ 거래를 찾을 수 없습니다.", ephemeral=True)
            trade = trades[trade_idx]
            await interaction.response.send_message(
                embed=discord.Embed(title="⚡ 거래 방식 선택", description="변경할 거래 방식을 선택해주세요:", color=discord.Color.blue()),
                view=EditMethodView(trade_idx, trade.get("unit", "sats")),
                ephemeral=True
            )
        return callback

    def _make_delete_callback(self, trade_idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ 본인의 거래만 삭제할 수 있습니다.", ephemeral=True)
            if trade_idx >= len(trades) or trades[trade_idx]["user_id"] != self.user_id:
                return await interaction.response.send_message("❌ 거래를 찾을 수 없습니다.", ephemeral=True)
            deleted = trades.pop(trade_idx)
            save_trades(trades)

            user_trades = get_user_trades(self.user_id)
            if user_trades:
                embed = build_my_trades_embed(user_trades)
                await interaction.response.edit_message(embed=embed, view=MyTradesView(self.user_id))
            else:
                embed = discord.Embed(title="📋 내 거래 목록", description="등록된 거래가 없습니다.", color=discord.Color.blue())
                await interaction.response.edit_message(embed=embed, view=None)
        return callback

class EditMethodView(View):
    def __init__(self, trade_idx: int, unit: str):
        super().__init__(timeout=60)
        self.trade_idx = trade_idx
        self.unit = unit

    @discord.ui.button(label="⚡ 라이트닝", style=discord.ButtonStyle.primary)
    async def lightning_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(EditModal(self.trade_idx, self.unit, "라이트닝"))

    @discord.ui.button(label="🔗 온체인", style=discord.ButtonStyle.secondary)
    async def onchain_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(EditModal(self.trade_idx, self.unit, "온체인"))

class EditModal(Modal):
    def __init__(self, trade_index: int, current_unit: str, method: str):
        super().__init__(title=f"거래 수정 ({current_unit})")
        self.trade_index = trade_index
        self.unit = current_unit
        self.method = method

        self.amount = TextInput(label=f"수량 ({current_unit})", placeholder="예: 1000000", required=True, max_length=20)
        self.premium = TextInput(label="프리미엄 (%)", placeholder="예: 1.5", required=True, max_length=10)
        self.note = TextInput(label="비고", placeholder="예: 월오사, 스피드 가능", required=False, max_length=100, style=discord.TextStyle.paragraph)

        for item in [self.amount, self.premium, self.note]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        result, error_msg = validate_trade_input(
            self.amount.value,
            self.premium.value,
            self.note.value if self.note.value else "",
            self.unit
        )
        
        if error_msg or result is None:
            return await interaction.response.send_message(error_msg or "❌ 입력값 검증 실패", ephemeral=True)
        
        amount_num, premium, note_clean = result

        if 0 <= self.trade_index < len(trades):
            trades[self.trade_index].update({
                "method": self.method,
                "amount": amount_num,
                "amount_formatted": f"{amount_num:,} {self.unit}",
                "premium": premium,
                "note": note_clean,
                "timestamp": datetime.now().isoformat()
            })
            save_trades(trades)
            await interaction.response.send_message("✅ 거래 정보가 수정되었습니다!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 거래를 찾을 수 없습니다.", ephemeral=True)

# ============== 슬래시 명령어 ==============
@checks.cooldown(1, 30.0, key=lambda i: (i.guild_id, i.user.id))
@tree.command(name="등록", description="새로운 P2P 거래를 등록합니다")
async def register_trade(interaction: discord.Interaction):
    embed = discord.Embed(title="💱 거래 단위 선택", description="거래하실 단위를 선택해주세요:", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=UnitSelectView(), ephemeral=True)

@checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
@tree.command(name="전광판", description="등록된 P2P 거래 목록을 확인합니다")
async def show_board(interaction: discord.Interaction):
    if interaction.channel.name != BOARD_CHANNEL_NAME:
        return await interaction.response.send_message("❌ 이 명령어는 전광판 채널에서만 사용할 수 있습니다.", ephemeral=True)

    if not trades:
        return await interaction.response.send_message("📊 등록된 거래가 없습니다.", ephemeral=True)

    sell = sorted([t for t in trades if t["trade_type"] == "판매"], key=lambda x: x["premium"])
    buy = sorted([t for t in trades if t["trade_type"] == "구매"], key=lambda x: x["premium"])

    embed = discord.Embed(title="📊 비트코인 P2P 전광판", color=discord.Color.gold(), timestamp=datetime.now())

    for name, data in [("🔴 판매", sell), ("🟢 구매", buy)]:
        if data:
            text = "\n".join([
                f"{'⚡' if t['method']=='라이트닝' else '🔗'} <@{t['user_id']}> | {t['amount_formatted']} | +{t['premium']}%{' | '+t['note'] if t.get('note') else ''}"
                for t in data
            ])
            embed.add_field(name=name, value=text, inline=False)

    embed.set_footer(text="판매자를 클릭하면 DM을 보낼 수 있습니다")
    await interaction.response.send_message(embed=embed)

@checks.cooldown(1, 15.0, key=lambda i: (i.guild_id, i.user.id))
@tree.command(name="내거래", description="내가 등록한 거래를 확인/수정/삭제합니다")
async def my_trades_cmd(interaction: discord.Interaction):
    user_trades = get_user_trades(interaction.user.id)

    if not user_trades:
        return await interaction.response.send_message("📋 등록한 거래가 없습니다.", ephemeral=True)

    embed = build_my_trades_embed(user_trades)
    await interaction.response.send_message(embed=embed, view=MyTradesView(interaction.user.id), ephemeral=True)

# ============== 관리자 명령어 ==============
@tree.command(name="전체삭제", description="[관리자] 모든 거래를 삭제합니다")
async def delete_all(interaction: discord.Interaction):
    if not is_admin_or_helper(interaction.user):
        return await interaction.response.send_message("❌ 관리자 또는 Helper만 사용할 수 있습니다.", ephemeral=True)

    if not trades:
        return await interaction.response.send_message("📊 삭제할 거래가 없습니다.", ephemeral=True)

    count = len(trades)
    trades.clear()
    save_trades(trades)
    await interaction.response.send_message(f"✅ 총 {count}개의 거래가 삭제되었습니다.", ephemeral=True)

@tree.command(name="강제삭제", description="[관리자] 특정 거래를 강제로 삭제합니다")
@app_commands.describe(번호="전광판에 표시된 순서")
async def force_delete(interaction: discord.Interaction, 번호: int):
    if not is_admin_or_helper(interaction.user):
        return await interaction.response.send_message("❌ 관리자 또는 Helper만 사용할 수 있습니다.", ephemeral=True)

    if not trades:
        return await interaction.response.send_message("❌ 삭제할 거래가 없습니다.", ephemeral=True)

    sell = sorted([t for t in trades if t["trade_type"] == "판매"], key=lambda x: x["premium"])
    buy = sorted([t for t in trades if t["trade_type"] == "구매"], key=lambda x: x["premium"])
    all_sorted = sell + buy

    if 번호 < 1 or 번호 > len(all_sorted):
        return await interaction.response.send_message(f"❌ 올바른 번호를 입력해주세요. (1-{len(all_sorted)})", ephemeral=True)

    target = all_sorted[번호 - 1]
    trades.remove(target)
    save_trades(trades)
    await interaction.response.send_message(f"✅ 거래가 삭제되었습니다.\n**{target['trade_type']}** | <@{target['user_id']}> | {target['amount_formatted']} | {target['premium']}%", ephemeral=True)

@tree.command(name="유저삭제", description="[관리자] 특정 유저의 모든 거래를 삭제합니다")
@app_commands.describe(유저="삭제할 유저")
async def delete_user_trades(interaction: discord.Interaction, 유저: discord.User):
    if not is_admin_or_helper(interaction.user):
        return await interaction.response.send_message("❌ 관리자 또는 Helper만 사용할 수 있습니다.", ephemeral=True)

    user_trades = [t for t in trades if t["user_id"] == 유저.id]
    if not user_trades:
        return await interaction.response.send_message(f"❌ {유저.display_name}님의 거래가 없습니다.", ephemeral=True)

    count = len(user_trades)
    for t in user_trades:
        trades.remove(t)
    save_trades(trades)
    await interaction.response.send_message(f"✅ {유저.display_name}님의 거래 {count}개가 삭제되었습니다.", ephemeral=True)

# ============== 봇 시작 ==============
@client.event
async def on_ready():
    await tree.sync()
    print(f'{client.user} 봇이 준비되었습니다!')
    print(f'서버 수: {len(client.guilds)}')

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
        exit(1)
    client.run(DISCORD_TOKEN)
