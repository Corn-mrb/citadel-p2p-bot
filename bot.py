import discord
from discord import app_commands
from discord.ui import Modal, TextInput, View
import json
import os
from datetime import datetime
from config import DISCORD_TOKEN, BOARD_CHANNEL_NAME, HELPER_ROLE_NAME, DATA_FILE

# Intents 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ============== 데이터 관리 ==============
def load_trades():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_trades(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

trades = load_trades()

# ============== 권한 체크 ==============
def is_admin_or_helper(user):
    has_helper = any(role.name == HELPER_ROLE_NAME for role in user.roles)
    return user.guild_permissions.administrator or has_helper

# ============== UI 컴포넌트 ==============
class UnitSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.button(label="🪙 sats로 거래", style=discord.ButtonStyle.primary)
    async def sats_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(TradeModal("sats"))
    
    @discord.ui.button(label="💵 원으로 거래", style=discord.ButtonStyle.success)
    async def won_button(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(TradeModal("원"))

class TradeModal(Modal):
    def __init__(self, unit: str):
        super().__init__(title=f"거래 등록 ({unit})")
        self.unit = unit
        
        self.trade_type_method = TextInput(label="유형 / 거래방식", placeholder="예: 판매 라이트닝 또는 구매 온체인", required=True, max_length=30)
        self.amount = TextInput(label=f"수량 ({unit})", placeholder="예: 1000000", required=True, max_length=20)
        self.premium = TextInput(label="프리미엄 (%)", placeholder="예: 1.5", required=True, max_length=10)
        self.note = TextInput(label="비고", placeholder="예: 월오사, 스피드 가능", required=False, max_length=100, style=discord.TextStyle.paragraph)
        
        for item in [self.trade_type_method, self.amount, self.premium, self.note]:
            self.add_item(item)
    
    async def on_submit(self, interaction: discord.Interaction):
        parts = self.trade_type_method.value.strip().split()
        
        if len(parts) < 2:
            return await interaction.response.send_message("❌ '유형 거래방식' 형식으로 입력해주세요.", ephemeral=True)
        
        trade_type, method = parts[0], parts[1]
        
        if trade_type not in ["판매", "구매"]:
            return await interaction.response.send_message("❌ 유형은 '판매' 또는 '구매'만 가능합니다.", ephemeral=True)
        if method not in ["라이트닝", "온체인"]:
            return await interaction.response.send_message("❌ 거래 방식은 '라이트닝' 또는 '온체인'만 가능합니다.", ephemeral=True)
        
        try:
            amount_num = int(self.amount.value.strip().replace(",", ""))
            premium = float(self.premium.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ 수량과 프리미엄은 숫자만 입력해주세요.", ephemeral=True)
        
        trade = {
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name,
            "trade_type": trade_type,
            "method": method,
            "unit": self.unit,
            "amount": amount_num,
            "amount_formatted": f"{amount_num:,} {self.unit}",
            "premium": premium,
            "note": self.note.value.strip() if self.note.value else "",
            "timestamp": datetime.now().isoformat()
        }
        
        trades.append(trade)
        save_trades(trades)
        await interaction.response.send_message(f"✅ 거래가 등록되었습니다!\n**{trade_type}** | {method} | {trade['amount_formatted']} | 프리미엄 {premium}%", ephemeral=True)

class EditModal(Modal):
    def __init__(self, trade_index: int, current_unit: str):
        super().__init__(title=f"거래 수정 ({current_unit})")
        self.trade_index = trade_index
        self.unit = current_unit
        
        self.method = TextInput(label="거래 방식", placeholder="라이트닝 또는 온체인", required=True, max_length=20)
        self.amount = TextInput(label=f"수량 ({current_unit})", placeholder="예: 1000000", required=True, max_length=20)
        self.premium = TextInput(label="프리미엄 (%)", placeholder="예: 1.5", required=True, max_length=10)
        self.note = TextInput(label="비고", placeholder="예: 월오사, 스피드 가능", required=False, max_length=100, style=discord.TextStyle.paragraph)
        
        for item in [self.method, self.amount, self.premium, self.note]:
            self.add_item(item)
    
    async def on_submit(self, interaction: discord.Interaction):
        method = self.method.value.strip()
        if method not in ["라이트닝", "온체인"]:
            return await interaction.response.send_message("❌ 거래 방식은 '라이트닝' 또는 '온체인'만 가능합니다.", ephemeral=True)
        
        try:
            amount_num = int(self.amount.value.strip().replace(",", ""))
            premium = float(self.premium.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ 수량과 프리미엄은 숫자만 입력해주세요.", ephemeral=True)
        
        if 0 <= self.trade_index < len(trades):
            trades[self.trade_index].update({
                "method": method,
                "amount": amount_num,
                "amount_formatted": f"{amount_num:,} {self.unit}",
                "premium": premium,
                "note": self.note.value.strip() if self.note.value else "",
                "timestamp": datetime.now().isoformat()
            })
            save_trades(trades)
            await interaction.response.send_message("✅ 거래 정보가 수정되었습니다!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 거래를 찾을 수 없습니다.", ephemeral=True)

# ============== 슬래시 명령어 ==============
@tree.command(name="등록", description="새로운 P2P 거래를 등록합니다")
async def register_trade(interaction: discord.Interaction):
    embed = discord.Embed(title="💱 거래 단위 선택", description="거래하실 단위를 선택해주세요:", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=UnitSelectView(), ephemeral=True)

@tree.command(name="전광판", description="등록된 P2P 거래 목록을 확인합니다")
async def show_board(interaction: discord.Interaction):
    if interaction.channel.name != BOARD_CHANNEL_NAME:
        return await interaction.response.send_message(f"❌ 이 명령어는 전광판 채널에서만 사용할 수 있습니다.", ephemeral=True)
    
    if not trades:
        return await interaction.response.send_message("📊 등록된 거래가 없습니다.", ephemeral=True)
    
    sell = sorted([t for t in trades if t["trade_type"] == "판매"], key=lambda x: x["premium"])
    buy = sorted([t for t in trades if t["trade_type"] == "구매"], key=lambda x: x["premium"])
    
    embed = discord.Embed(title="📊 비트코인 P2P 전광판", color=discord.Color.gold(), timestamp=datetime.now())
    
    for name, data, emoji in [("🔴 판매", sell, ""), ("🟢 구매", buy, "")]:
        if data:
            text = "\n".join([f"{'⚡' if t['method']=='라이트닝' else '🔗'} <@{t['user_id']}> | {t['amount_formatted']} | +{t['premium']}%{' | '+t['note'] if t['note'] else ''}" for t in data])
            embed.add_field(name=name, value=text, inline=False)
    
    embed.set_footer(text="판매자를 클릭하면 DM을 보낼 수 있습니다")
    await interaction.response.send_message(embed=embed)

@tree.command(name="내거래", description="내가 등록한 거래 목록을 확인합니다")
async def my_trades_cmd(interaction: discord.Interaction):
    user_trades = [t for t in trades if t["user_id"] == interaction.user.id]
    
    if not user_trades:
        return await interaction.response.send_message("📋 등록한 거래가 없습니다.", ephemeral=True)
    
    embed = discord.Embed(title="📋 내 거래 목록", color=discord.Color.blue())
    for idx, t in enumerate(user_trades):
        emoji = "⚡" if t["method"] == "라이트닝" else "🔗"
        note = f"\n비고: {t['note']}" if t['note'] else ""
        embed.add_field(name=f"{idx+1}. {t['trade_type']} {emoji}", value=f"수량: {t['amount_formatted']}\n프리미엄: {t['premium']}%{note}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="수정", description="내가 등록한 거래를 수정합니다")
@app_commands.describe(번호="수정할 거래 번호")
async def edit_trade(interaction: discord.Interaction, 번호: int):
    indices = [i for i, t in enumerate(trades) if t["user_id"] == interaction.user.id]
    
    if not indices:
        return await interaction.response.send_message("❌ 등록한 거래가 없습니다.", ephemeral=True)
    if 번호 < 1 or 번호 > len(indices):
        return await interaction.response.send_message(f"❌ 올바른 번호를 입력해주세요. (1-{len(indices)})", ephemeral=True)
    
    idx = indices[번호 - 1]
    await interaction.response.send_modal(EditModal(idx, trades[idx].get("unit", "sats")))

@tree.command(name="삭제", description="내가 등록한 거래를 삭제합니다")
@app_commands.describe(번호="삭제할 거래 번호")
async def delete_trade(interaction: discord.Interaction, 번호: int):
    indices = [i for i, t in enumerate(trades) if t["user_id"] == interaction.user.id]
    
    if not indices:
        return await interaction.response.send_message("❌ 등록한 거래가 없습니다.", ephemeral=True)
    if 번호 < 1 or 번호 > len(indices):
        return await interaction.response.send_message(f"❌ 올바른 번호를 입력해주세요. (1-{len(indices)})", ephemeral=True)
    
    deleted = trades.pop(indices[번호 - 1])
    save_trades(trades)
    await interaction.response.send_message(f"✅ 거래가 삭제되었습니다.\n**{deleted['trade_type']}** | {deleted['amount_formatted']} | {deleted['premium']}%", ephemeral=True)

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
