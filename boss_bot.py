import os
import time
import sqlite3
import discord

from discord.ext import commands, tasks

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

db = sqlite3.connect("boss_times.db")

db.execute("""
CREATE TABLE IF NOT EXISTS bosses (
    guild_id INTEGER,
    channel_id INTEGER,
    boss TEXT,
    cut_at INTEGER,
    respawn_at INTEGER,
    notified INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, boss)
)
""")
db.commit()


@bot.event
async def on_ready():
    print(f"봇 로그인 성공: {bot.user}")
    guild = discord.Object(id=15580877995531936)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    
    if not boss_alert_loop.is_running():
        boss_alert_loop.start()

@bot.tree.command(name="컷삭제", description="등록된 보스 컷 시간을 삭제합니다.")
async def cut_delete(interaction: discord.Interaction, boss: str):
    import sqlite3
    conn = sqlite3.connect("boss.db")
    cursor = conn.cursor()
    
    # 테이블이 혹시 없어도 에러가 나지 않게 안전하게 먼저 생성해 줍니다.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boss (
            boss_name TEXT,
            respawn_time TEXT
        )
    """)
    
    # 보스 정보 삭제 실행
    cursor.execute("DELETE FROM boss WHERE boss_name = ?", (boss,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🗑️ **{boss}** 보스의 컷 정보가 삭제되었습니다!")

from discord import app_commands
from datetime import datetime, timedelta
import sqlite3

# 보스별 고정 젠 타임 사전 (시간 단위)
BOSS_HOURS = {
    "크리소파고스": 8,
    "아모르포스": 8,
    "트라손": 8,
    "이오칸토스": 12,
    "키니 러우리": 12,
    "알라스토르": 12,
    "베딕스": 12,
    "고트시스": 12,
    "트리포크": 12,
    "거인의 손": 12,
    "인터 아모르": 12,
    "인터일반": 24
}

@bot.tree.command(name="보스컷", description="목록에서 보스를 선택해 젠 시간을 자동으로 등록합니다.")
@app_commands.choices(boss_name=[
    app_commands.Choice(name="[35] 크리소파고스 (8시간)", value="크리소파고스"),
    app_commands.Choice(name="[35] 아모르포스 (8시간)", value="아모르포스"),
    app_commands.Choice(name="[40] 트라손 (8시간)", value="트라손"),
    app_commands.Choice(name="[45] 이오칸토스 (12시간)", value="이오칸토스"),
    app_commands.Choice(name="[45] 키니 러우리 (12시간)", value="키니 러우리"),
    app_commands.Choice(name="[55] 알라스토르 (12시간)", value="알라스토르"),
    app_commands.Choice(name="[60] 베딕스 (12시간)", value="베딕스"),
    app_commands.Choice(name="[60] 고트시스 (12시간)", value="고트시스"),
    app_commands.Choice(name="[65] 트리포크 (12시간)", value="트리포크"),
    app_commands.Choice(name="[70] 거인의 손 (12시간)", value="거인의 손"),
    app_commands.Choice(name="[40] 인터 아모르 (12시간)", value="인터 아모르"),
    app_commands.Choice(name="[40] 인터 일반 (8시간)", value="인터 일반"),
])
async def boss_cut(interaction: discord.Interaction, boss_name: str):
    if interaction.guild_id is None:
        await interaction.response.send_message("서버에서 사용해 주세요.", ephemeral=True)
        return

    # 선택한 보스의 리스폰 시간 가져오기 (기본값 8시간)
    hours = BOSS_HOURS.get(boss_name, 8)
    
    # 현재 시간 + 보스별 고정 시간 계산
    now = datetime.now()
    respawn_time = now + timedelta(hours=hours)
    respawn_time_str = respawn_time.strftime("%Y-%m-%d %H:%M:%S")

    # 데이터베이스 저장
    conn = sqlite3.connect("boss.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boss (
            boss_name TEXT,
            respawn_time TEXT
        )
    """)
    
    # 기존에 등록된 같은 보스가 있다면 지우고 새로 등록
    cursor.execute("DELETE FROM boss WHERE boss_name = ?", (boss_name,))
    cursor.execute("INSERT INTO boss (boss_name, respawn_time) VALUES (?, ?)", (boss_name, respawn_time_str))
    
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"⚔️ **{boss_name}** 컷 등록 완료! "
        f"약 **{hours}시간 뒤**인 **{respawn_time.strftime('%H시 %M분')}**에 알림이 울립니다."
    )

@bot.tree.command(name="컷현황", description="보스 컷 현황을 확인합니다.")
async def cut_status(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "서버에서 사용해 주세요.",
            ephemeral=True
        )
        return

    rows = db.execute("""
        SELECT boss, cut_at, respawn_at
        FROM bosses
        WHERE guild_id = ?
        ORDER BY respawn_at
    """, (interaction.guild_id,)).fetchall()

    if not rows:
        await interaction.response.send_message(
            "등록된 보스가 없습니다."
        )
        return

    result = []

    for boss, cut_at, respawn_at in rows:
        result.append(
            f"**{boss}**\n"
            f"컷: <t:{cut_at}:F>\n"
            f"리젠: <t:{respawn_at}:F> "
            f"(<t:{respawn_at}:R>)"
        )

    await interaction.response.send_message(
        "📋 **보스 컷 현황**\n\n" + "\n\n".join(result)
    )


@tasks.loop(seconds=15)
async def alert_loop():
    now = int(time.time())

    rows = db.execute("""
        SELECT guild_id, channel_id, boss, respawn_at
        FROM bosses
        WHERE notified = 0 AND respawn_at <= ?
    """, (now,)).fetchall()

    for guild_id, channel_id, boss, respawn_at in rows:
        channel = bot.get_channel(channel_id)

        if channel is None:
            continue

        try:
            await channel.send(
                f"🔔 **{boss} 리젠 시간입니다!**\n"
                f"예정 시간: <t:{respawn_at}:F>"
            )

            db.execute("""
                UPDATE bosses
                SET notified = 1
                WHERE guild_id = ? AND boss = ?
            """, (guild_id, boss))
            db.commit()

        except discord.HTTPException as error:
            print(f"알림 전송 실패: {error}")


@alert_loop.before_loop
async def before_alert_loop():
    await bot.wait_until_ready()



bot.run('MTU1ODA2MzE3NzU3OTg5MjczNg.Geclz9.Lg8apw05mgQUmmgX-4Wo0KGZMpYgW51l_b0vDE')


from discord.ext import tasks

# 🚨 알림 메시지가 전송될 디스코드 텍스트 채널의 ID를 입력하세요!
# (채널 우클릭 -> '채널 ID 복사'를 통해 얻을 수 있습니다)
ALERT_CHANNEL_ID = 1558087799553531936

@tasks.loop(minutes=1)
async def boss_alert_loop():
    await bot.wait_until_ready()
    
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect("boss.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boss (
            boss_name TEXT,
            respawn_time TEXT
        )
    """)
    
    # 현재 시간보다 부활 시간이 같거나 지난 보스들 조회
    cursor.execute("SELECT boss_name, respawn_time FROM boss WHERE respawn_time <= ?", (now_str,))
    expired_bosses = cursor.fetchall()
    
    if expired_bosses:
        channel = bot.get_channel(ALERT_CHANNEL_ID)
        if channel:
            for boss_name, respawn_time in expired_bosses:
                # @everyone을 붙여서 확실하게 알람 소리가 울리도록 전송
                await channel.send(
                    f"@everyone 🚨 **{boss_name}** 보스가 젠되었습니다! 레이드 준비하세요!"
                )
        
        # 알람을 보낸 보스는 데이터베이스에서 삭제하여 중복 알람 방지
        cursor.execute("DELETE FROM boss WHERE respawn_time <= ?", (now_str,))
        conn.commit()
        
    conn.close()
