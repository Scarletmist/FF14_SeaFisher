# bot_2hour_cron.py
import os
from dotenv import load_dotenv
import zoneinfo
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # 改成你的頻道 ID
MESSAGE_TEXT = os.getenv("MESSAGE_TEXT", "自動排程訊息：時間到！")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 使用台北時區
tz = zoneinfo.ZoneInfo("Asia/Taipei")
scheduler = AsyncIOScheduler(timezone=tz)

async def safe_send(channel_id: int, text: str):
    try:
        # 先用快取，如果快取沒有，再 fetch
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        await channel.send(text)
    except Exception as e:
        # 日誌或其他處理，避免例外讓排程停止
        print(f"[{__name__}] 發送失敗：{e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    if not scheduler.running:
        # CronTrigger: 從 01:50 開始，每 2 小時 => 小時欄位使用 '1-23/2' (1,3,5,...,23)
        trigger = CronTrigger(hour="1-23/2", minute=50)  # Asia/Taipei 時區已由 scheduler 指定
        scheduler.add_job(
            lambda: asyncio.create_task(safe_send(CHANNEL_ID, MESSAGE_TEXT)),
            trigger=trigger,
            id="every_2_hours_from_01_50",
            replace_existing=True
        )
        scheduler.start()
        print("Scheduler started: messages scheduled at 01:50, 03:50, 05:50, ... (Asia/Taipei)")

if __name__ == "__main__":
    if TOKEN is None or CHANNEL_ID == 0:
        raise SystemExit("請在 .env 設定 DISCORD_TOKEN 與 CHANNEL_ID")
    bot.run(TOKEN)
