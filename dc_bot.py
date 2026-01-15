# announce_bot.py（只貼關鍵改動部分與主結構）
import discord
from discord.ext import commands
import asyncio
from aiohttp import web
import json
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import os
from typing import Dict, Optional
from fish_notice import get_bait
import signal
import logging
import redis.asyncio as aioredis

REDIS_URL = os.environ["REDIS_URL"]  # 在 Render Web Service 的 env 設定
r = aioredis.from_url(REDIS_URL, decode_responses=True)  # decode_responses 方便取回 str

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dc_bot")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))  # Render 會提供 PORT
CHANNELS_FILE = Path("channels.json")
TIMEZONE = ZoneInfo("Asia/Taipei")
SCHEDULE_HOURS = list(range(1, 24, 2))
SCHEDULE_MINUTE = 55

async def load_channels() -> Dict[str, int]:
    keys = await r.keys("channel:*")
    channels = {}
    for k in keys:
        val = await r.get(k)
        guild_id = k.split(":",1)[1]
        channels[guild_id] = json.loads(val) if val else {}
    return channels

async def save_channels(guild_id, data):
    await r.set(f"channel:{guild_id}", json.dumps(data))

class AnnounceBot(commands.Bot):
    def __init__(self, command_prefix: str = "!", **options):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents, **options)

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
        logger.info(f"Logged in as {self.user} (id: {self.user.id})")
        logger.info("------")

    # schedule loop 與其它函式照原本實作（略過，保留你原先的 _schedule_loop/_next_schedule_after/_send_announcement）

    async def _schedule_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(tz=TIMEZONE)
            next_run = self._next_schedule_after(now)
            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"[Scheduler] now={now.isoformat()}, next={next_run.isoformat()}, wait={int(wait_seconds)}s")
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
        channels = await load_channels()
        for guild_id_str, channel_id in list(channels.items()):
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
                logger.info(f"[Info] sent announcement to {channel_id}")
            except discord.Forbidden:
                guilds_to_remove.append(guild_id_str)
            except Exception as e:
                logger.warning(f"[Error] sending to {channel_id}: {e}")
        if guilds_to_remove:
            for gid in guilds_to_remove:
                await save_channels(gid, None)


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
        channels = await load_channels()
        guild_id = str(ctx.guild.id)
        channel_id = ctx.channel.id
        await save_channels(guild_id, channel_id)
        await ctx.send(f"已將此頻道 <#{channel_id}> 設為本伺服器的公告頻道。")

    @commands.command(
        name="unset_announce_channel",
        help="取消本伺服器的公告頻道設定（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def unset_channel(self, ctx: commands.Context):
        channels = await load_channels()
        guild_id = str(ctx.guild.id)
        if guild_id in channels:
            await save_channels(guild_id, None)
            await ctx.send("已取消本伺服器的公告頻道設定。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")

    @commands.command(
        name="show_announce_channel",
        help="顯示本伺服器目前設定的公告頻道"
    )
    async def show_channel(self, ctx: commands.Context):
        channels = await load_channels()
        guild_id = str(ctx.guild.id)
        channel_id = channels.get(guild_id)
        if channel_id:
            await ctx.send(f"目前本伺服器的公告頻道為 <#{channel_id}> 。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")
    
    @commands.command(
        name="get_bait",
        help="取得目前時段/下個時段的釣場魚餌資訊"
    )
    async def get_bait(self, ctx: commands.Context):
        channels = await load_channels()
        guild_id = str(ctx.guild.id)
        channel_id = channels.get(guild_id)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        
        if channel:
            await channel.send(get_bait(datetime.now(tz=TIMEZONE)))

# ---------- 啟動 ----------
bot = AnnounceBot(command_prefix="!")

# 以下為 HTTP server（簡單 health check）
async def handle_ok(request):
    return web.Response(text="OK")

async def start_http_server(port: int):
    app = web.Application()
    app.add_routes([web.get("/", handle_ok), web.get("/health", handle_ok)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"HTTP server listening on 0.0.0.0:{port}")
    return runner

# 主流程：啟動 http server 與 discord bot 並處理 shutdown
async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    # Unix: 把 SIGINT/SIGTERM 與 event 連結
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, shutdown_event.set)
        except NotImplementedError:
            # Windows 或不支援 signal handler 的環境
            pass

    # 啟動 HTTP server（滿足 Render 的 port scan）
    runner = await start_http_server(PORT)

    # 啟動 discord bot（在 background task）
    bot_task = asyncio.create_task(bot.start(TOKEN))

    # 等待關機事件
    await shutdown_event.wait()
    logger.info("Shutdown signal received — beginning graceful shutdown...")

    # 先關閉 discord bot
    try:
        await bot.close()
        logger.info("Discord bot closed.")
    except Exception as e:
        logger.exception("Error closing bot: %s", e)

    # 再關掉 HTTP server
    try:
        await runner.cleanup()
        logger.info("HTTP runner cleaned up.")
    except Exception as e:
        logger.exception("Error cleaning up HTTP runner: %s", e)

    # 等待 bot_task 結束（若尚未）
    try:
        await asyncio.wait_for(bot_task, timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Bot task did not finish within timeout after close().")
    except Exception:
        logger.exception("bot_task raised exception after close()")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Fatal error in main loop")
