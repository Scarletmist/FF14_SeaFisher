# announce_bot.py（只貼關鍵改動部分與主結構）
import discord
from discord.ext import commands
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import os
from typing import Dict, Optional
from fish_notice import get_bait
import signal

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNELS_FILE = Path("channels.json")
TIMEZONE = ZoneInfo("Asia/Taipei")
SCHEDULE_HOURS = list(range(1, 24, 2))
SCHEDULE_MINUTE = 55

def load_channels() -> Dict[str, int]:
    if CHANNELS_FILE.exists():
        with CHANNELS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f).get("guilds", {})
    return {}

def save_channels(channels: Dict[str, int]):
    with CHANNELS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"guilds": channels}, f, ensure_ascii=False, indent=2)

class AnnounceBot(commands.Bot):
    def __init__(self, command_prefix: str = "!", **options):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents, **options)

        # 載入頻道
        self.registered_channels: Dict[str, int] = load_channels()

        # background task
        self._scheduler_task: Optional[asyncio.Task] = None
        self.bg_task_started = False

    async def setup_hook(self):
        # 在 bot ready 之前把 Cog 加進來
        await self.add_cog(AnnounceCog(self))

        # 啟動排程
        if not self.bg_task_started:
            self._scheduler_task = self.loop.create_task(self._schedule_loop())
            self.bg_task_started = True

    async def on_ready(self):
        print(f"Logged in as {self.user} (id: {self.user.id})")
        print("------")

    # schedule loop 與其它函式照原本實作（略過，保留你原先的 _schedule_loop/_next_schedule_after/_send_announcement）

    async def _schedule_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(tz=TIMEZONE)
            next_run = self._next_schedule_after(now)
            wait_seconds = (next_run - now).total_seconds()
            print(f"[Scheduler] now={now.isoformat()}, next={next_run.isoformat()}, wait={int(wait_seconds)}s")
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                break
            await self._send_announcement(next_run)
            await asyncio.sleep(1)

    def _next_schedule_after(self, now: datetime) -> datetime:
        today = now.date()
        candidates = []
        for h in SCHEDULE_HOURS:
            cand = datetime.combine(today, time(hour=h, minute=SCHEDULE_MINUTE, second=0), tzinfo=TIMEZONE)
            if cand > now:
                candidates.append(cand)
        if candidates:
            return min(candidates)
        tomorrow = today + timedelta(days=1)
        return datetime.combine(tomorrow, time(hour=SCHEDULE_HOURS[0], minute=SCHEDULE_MINUTE, second=0), tzinfo=TIMEZONE)

    async def _send_announcement(self, run_time: datetime):
        guilds_to_remove = []
        for guild_id_str, channel_id in list(self.registered_channels.items()):
            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception:
                        channel = None
                if channel is None:
                    guilds_to_remove.append(guild_id_str)
                    continue
                timestamp = run_time.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
                message = get_bait(datetime.now(tz=TIMEZONE))
                await channel.send(message)
                print(f"[Info] sent announcement to {channel_id}")
            except discord.Forbidden:
                guilds_to_remove.append(guild_id_str)
            except Exception as e:
                print(f"[Error] sending to {channel_id}: {e}")
        if guilds_to_remove:
            for gid in guilds_to_remove:
                self.registered_channels.pop(gid, None)
            save_channels(self.registered_channels)


# ----- 將命令放在 Cog 裡 -----
class AnnounceCog(commands.Cog):
    def __init__(self, bot: AnnounceBot):
        self.bot = bot

    @commands.command(
        name="set_announce_channel",
        help="將此頻道設為公告頻道（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def set_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channel_id = ctx.channel.id
        self.bot.registered_channels[guild_id] = channel_id
        save_channels(self.bot.registered_channels)
        await ctx.send(f"已將此頻道 <#{channel_id}> 設為本伺服器的公告頻道。")

    @commands.command(
        name="unset_announce_channel",
        help="取消本伺服器的公告頻道設定（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def unset_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        if guild_id in self.bot.registered_channels:
            del self.bot.registered_channels[guild_id]
            save_channels(self.bot.registered_channels)
            await ctx.send("已取消本伺服器的公告頻道設定。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")

    @commands.command(
        name="show_announce_channel",
        help="顯示本伺服器目前設定的公告頻道"
    )
    async def show_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channel_id = self.bot.registered_channels.get(guild_id)
        if channel_id:
            await ctx.send(f"目前本伺服器的公告頻道為 <#{channel_id}> 。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")
    
    @commands.command(
        name="get_bait",
        help="取得目前時段/下個時段的釣場魚餌資訊"
    )
    async def get_bait(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channel_id = self.bot.registered_channels.get(guild_id)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        
        if channel:
            await channel.send(get_bait(datetime.now(tz=TIMEZONE)))

# ---------- 啟動 ----------
bot = commands.Bot(command_prefix="!")

async def main():
    loop = asyncio.get_running_loop()

    # 當接收到系統訊號時，建立一個任務去關閉 bot
    def _on_exit():
        # create_task 可以在 signal handler 裡安全呼叫
        asyncio.create_task(shutdown())

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, _on_exit)

    # 直接啟動 bot，當 bot 被 close() 後這裡會返回
    await bot.start(TOKEN)

async def shutdown():
    print("收到關機訊號，嘗試關閉 bot...")
    # 若你有其他 cleanup（例如關 DB 連線），也放這裡
    try:
        await bot.close()
    except Exception as e:
        print("關閉 bot 時發生錯誤：", e)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("主程式例外：", e)
