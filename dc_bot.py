# announce_bot.py（只貼關鍵改動部分與主結構）
import discord
from discord.ext import commands, tasks
import asyncio
from aiohttp import web, ClientSession, ClientTimeout, ClientSession
import json
from pathlib import Path
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
import os
from typing import Dict, Optional, Tuple, List, Any
from fish_notice import get_bait, get_source
from ore_notice import get_ore, convert_to_eorzea_time, EorzeaTime
import signal
import logging
import ntplib
import redis.asyncio as aioredis
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, ConnectionError as RedisConnectionError
import time as st

_retry = Retry(ExponentialBackoff(base=1, cap=10), 3)
REDIS_URL = os.getenv("REDIS_URL", "rediss://red-d5msqk56ubrc73aes19g:Kl0cDpmkEMnEaBqEI8peXG7fZtIe4xTB@oregon-keyvalue.render.com:6379")  # 在 Render Web Service 的 env 設定


class RedisWrapper:
    def __init__(
        self,
        url: str,
        decode_responses: bool = True,
        retry: Optional[Retry] = _retry,
        retry_on_error: Optional[list] = None,
        health_check_interval: int = 5,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        self.url = url
        self.decode_responses = decode_responses
        self.retry = retry
        self.retry_on_error = retry_on_error or [BusyLoadingError]
        self.health_check_interval = health_check_interval
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout

        self._client: Optional[aioredis.Redis] = None
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger("redis_wrapper")

    async def connect(self):
        """(re)create the redis async client. Protected by lock."""
        async with self._lock:
            if self._client is not None:
                # quick health check
                try:
                    await self._client.ping()
                    return
                except Exception:
                    try:
                        await self._client.close()
                        await self._client.connection_pool.disconnect()
                    except Exception:
                        pass
                    self._client = None

            # create new client
            # note: you can add ssl=True or other kwargs if needed
            self._logger.info("Creating new redis client")
            self._client = aioredis.from_url(
                self.url,
                decode_responses=self.decode_responses,
                retry=self.retry,
                retry_on_error=self.retry_on_error,
                health_check_interval=self.health_check_interval,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
            )

            # do an initial ping to ensure connection established
            try:
                await self._client.ping()
            except Exception as e:
                # close and raise upward
                try:
                    await self._client.close()
                    await self._client.connection_pool.disconnect()
                except Exception:
                    pass
                self._client = None
                raise

    async def _ensure_client(self):
        if self._client is None:
            await self.connect()

    async def execute(self, method: str, *args, retries: int = 3, **kwargs) -> Any:
        """Generic executor: does limited retries and will reconnect on connection errors."""
        backoff = 1.0
        for attempt in range(1, retries + 1):
            try:
                await self._ensure_client()
                func = getattr(self._client, method)
                return await func(*args, **kwargs)
            except RedisConnectionError as e:
                self._logger.warning("Redis connection error on %s attempt %s: %s", method, attempt, e, exc_info=True)
                # try reconnect
                try:
                    # force reconnect
                    async with self._lock:
                        if self._client:
                            try:
                                await self._client.close()
                                await self._client.connection_pool.disconnect()
                            except Exception:
                                pass
                        self._client = None
                        # small sleep before reconnect to avoid tight loop
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30)
                        # next loop will call connect()
                except Exception:
                    # ignore
                    pass
                # continue retry
                continue
            except Exception as e:
                # non-connection error -> rethrow
                self._logger.exception("Redis operation %s raised unexpected exception", method)
                raise
        # after attempts exhausted
        raise RedisConnectionError(f"Redis operation {method} failed after {retries} attempts")

    # convenience wrappers
    async def smembers(self, *args, **kwargs): return await self.execute("smembers", *args, **kwargs)
    async def sismember(self, *args, **kwargs): return await self.execute("sismember", *args, **kwargs)
    async def hgetall(self, *args, **kwargs): return await self.execute("hgetall", *args, **kwargs)
    async def keys(self, *args, **kwargs): return await self.execute("keys", *args, **kwargs)
    async def exists(self, *args, **kwargs): return await self.execute("exists", *args, **kwargs)
    async def delete(self, *args, **kwargs): return await self.execute("delete", *args, **kwargs)
    async def hset(self, *args, **kwargs): return await self.execute("hset", *args, **kwargs)
    async def sadd(self, *args, **kwargs): return await self.execute("sadd", *args, **kwargs)
    async def ping(self, *args, **kwargs): return await self.execute("ping", *args, **kwargs)
    # add other methods you use similarly...

# create wrapper instance once
redis_wrapper = RedisWrapper(REDIS_URL)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("dc_bot")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))  # Render 會提供 PORT
CHANNELS_FILE = Path("channels.json")
TIMEZONE = ZoneInfo("Asia/Taipei")
SCHEDULE_HOURS = list(range(1, 24, 2))
SCHEDULE_MINUTE = 55


async def remove_ore(name):
    if await redis_wrapper.exists(f'channel:ore:{name}'):
        await redis_wrapper.delete(f'channel:ore:{name}')


async def set_ore(name, time, place):
    await redis_wrapper.hset(f'channel:ore:{name}', mapping={'time': time, 'place': place})


async def get_ores():
    ore_names = await redis_wrapper.keys('channel:ore:*')
    ores = {}

    for name_key in ore_names:
        ore = name_key.split(':')[-1]
        ores[ore] = await redis_wrapper.hgetall(name_key)
    
    return ores


async def get_channels(guild_id) -> Dict[str, str]:
    if await redis_wrapper.sismember('channel:ids', guild_id):
        return await redis_wrapper.hgetall(f'channel:{guild_id}')
    else:
        return {}


async def load_channels() -> Tuple[List[str]]:
    guild_ids_key = 'channel:ids'
    try:
        guild_ids = await redis_wrapper.smembers(guild_ids_key)
    except Exception as e:
        logger.exception("Failed to fetch guild ids from redis. Attempt reconnect and return empty lists.")
        # 可選：嘗試再連一次
        try:
            await redis_wrapper.connect()
            guild_ids = await redis_wrapper.smembers(guild_ids_key)
        except Exception:
            logger.exception("Reconnect attempt failed")
            return [], []

    fishes = []
    ores = []

    for guild_id in guild_ids or []:
        try:
            channels = await redis_wrapper.hgetall(f'channel:{guild_id}')
            for channel_id, channel_type in channels.items():
                if channel_type == 'fish':
                    fishes.append(channel_id)
                else:
                    ores.append(channel_id)
        except Exception:
            logger.exception("Error reading channels for guild %s; skip", guild_id)
            continue

    return fishes, ores


async def save_channels(guild_id, channel_id, new_type):
    if await redis_wrapper.sismember('channel:ids', guild_id):
        old_channels = await redis_wrapper.hgetall(f'channel:{guild_id}')
        new_channels = {}

        for c_id, old_type in old_channels.items():
            if old_type != new_type:
                new_channels[c_id] = old_type
        new_channels[channel_id] = new_type
        await redis_wrapper.hset(f"channel:{guild_id}", mapping=new_channels)
    else:
        await redis_wrapper.hset(f"channel:{guild_id}", mapping={channel_id: new_type})
        await redis_wrapper.sadd('channel:ids', guild_id)


async def remove_channel(guild_id, channel_id):
    if await redis_wrapper.sismember('channel:ids', guild_id):
        old_channels = await redis_wrapper.hgetall(f'channel:{guild_id}')
        new_channels = {}

        for c_id in old_channels.keys():
            if c_id != channel_id:
                new_channels[c_id] = old_channels[c_id]
        await redis_wrapper.hset(f"channel:{guild_id}", mapping=new_channels)


async def get_authoritative_now(tz_name: str = "Asia/Taipei", http_session: ClientSession = None) -> datetime:
    """
    優先使用 worldtimeapi -> timeapi.io -> ntplib -> 系統時間 的順序取得現在時間
    返回 timezone-aware datetime。
    """
    close_session = False
    if http_session is None:
        http_session = ClientSession(timeout=ClientTimeout(total=5))
        close_session = True

    try:
        # 1) worldtimeapi
        try:
            url = f"https://worldtimeapi.org/api/timezone/{tz_name}"
            async with http_session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    dt_str = data.get("datetime")
                    if dt_str:
                        dt = datetime.fromisoformat(dt_str)
                        return dt
        except Exception:
            # swallow and try next
            pass

        # 2) timeapi.io
        try:
            url2 = f"https://timeapi.io/api/time/current/zone?timeZone={tz_name}"
            async with http_session.get(url2) as resp2:
                if resp2.status == 200:
                    j = await resp2.json()
                    dt_str = j.get("dateTime") or j.get("dateTimeRaw") or j.get("dateTimeUTC")
                    if dt_str:
                        dt = datetime.fromisoformat(dt_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                        return dt
        except Exception:
            pass

        # 3) NTP via executor (ntplib is blocking)
        try:
            loop = asyncio.get_running_loop()
            def ntp_query():
                c = ntplib.NTPClient()
                resp = c.request("pool.ntp.org", version=3, timeout=5)
                return datetime.fromtimestamp(resp.tx_time, tz=timezone.utc).astimezone(ZoneInfo(tz_name))
            dt_ntp = await loop.run_in_executor(None, ntp_query)
            return dt_ntp
        except Exception:
            pass

        # 4) fallback to system clock
        return datetime.now(tz=ZoneInfo(tz_name))
    finally:
        if close_session:
            await http_session.close()


class AnnounceBot(commands.Bot):
    _noticed = []
    _is_ore_run = False
    _is_fish_run = False

    def __init__(self, command_prefix: str = "!", **options):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = False
        super().__init__(command_prefix=command_prefix, intents=intents, **options)

        self.is_ready = False

    async def setup_hook(self):
        logger.info("SETUP HOOK")

        self.fish_background_task.start()
        self.ore_background_task.start()

        # 在 bot ready 之前把 Cog 加進來
        await self.add_cog(AnnounceCog(self))

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (id: {self.user.id})")
        logger.info("------")
        self.is_ready = True
    
    @tasks.loop(seconds=30)
    async def ore_background_task(self):
        try:
            # 每次進入這個 coroutine 都做一次完整檢查 -> tasks.loop 會在下一個 minute 再呼叫
            async with ClientSession() as session:
                now = await get_authoritative_now(tz_name="Asia/Taipei", http_session=session)
                eorz_now = convert_to_eorzea_time(now)
                eorz_5min = convert_to_eorzea_time(now + timedelta(minutes=5))
                _, ore_channels = await load_channels()

                logger.info(f"[Scheduler] [Ore] real now={now.isoformat()}, eor now={eorz_now}, check={eorz_5min}")
                logger.debug(f"noticed list: {self._noticed}")

                # 若還沒通知過此 eor 時段 -> 發送並記錄
                if eorz_5min.get_datehour() not in self._noticed:
                    if len(self._noticed) > 5:  # 多久的歷史要保留視需求調整
                        self._noticed.pop(0)
                    self._noticed.append(eorz_5min.get_datehour())
                    await self._send_ore_announcement(eorz_5min, ore_channels)

        except asyncio.CancelledError:
            # 被取消，向上丟出讓 tasks.loop 處理 (或在監護邏輯中重啟)
            raise
        except Exception:
            logger.exception("Exception in ore_background_task")

    @tasks.loop(minutes=5)
    async def fish_background_task(self):
        try:
            async with ClientSession() as session:
                if not self.is_closed():
                    now = await get_authoritative_now(tz_name="Asia/Taipei", http_session=session)
                    next_run = self._next_schedule_after(now)
                    wait_seconds = (next_run - now).total_seconds()

                    logger.info(f"[Scheduler] [Fish] now={now.isoformat()}, next={next_run.isoformat()}, wait={int(wait_seconds)}s")

                    fish_channels, _ = await load_channels()

                    if wait_seconds <= 300:
                        await asyncio.sleep(wait_seconds)
                        await self._send_sea_announcement(next_run, fish_channels)

        except Exception as ex:
            logger.exception(ex)

    @fish_background_task.before_loop
    async def before_fish_task(self):
        await self.wait_until_ready()  # wait until the bot logs in
    
    @ore_background_task.before_loop
    async def before_ore_task(self):
        await self.wait_until_ready()

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

    async def _send_sea_announcement(self, run_time: datetime, fish_channels):
        message = get_bait(run_time)
        for channel_id in fish_channels:
            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception:
                        channel = None
                if channel is None:
                    continue
                timestamp = run_time.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
                await channel.send(message)
                logger.info(f"[Info] sent fish announcement to {channel_id}")
            except Exception as e:
                logger.warning(f"[Error] sending to {channel_id}: {e}")
    
    async def _send_ore_announcement(self, fivemin_time: EorzeaTime, ore_channels):
        message = get_ore(fivemin_time, await get_ores())
        if len(message) == 0:
            return
        
        for channel_id in ore_channels:
            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception:
                        channel = None
                if channel is None:
                    continue
                await channel.send(message)
                logger.info(f"[Info] sent ore announcement to {channel_id}")
            except Exception as e:
                logger.warning(f"[Error] sending to {channel_id}: {e}")
    
    async def on_disconnect(self):
        logger.warning("on_disconnect called")

    async def on_resumed(self):
        logger.info("on_resumed called")

    async def on_error(self, event, *args, **kwargs):
        logger.exception("on_error: %s", event)


# ----- 將命令放在 Cog 裡 -----
class AnnounceCog(commands.Cog):
    def __init__(self, bot: AnnounceBot):
        self.bot = bot

    @commands.command(
        name="set_sea_announce_channel",
        help="將此頻道設為海釣公告頻道（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def set_fish_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channel_id = ctx.channel.id
        await save_channels(guild_id, channel_id, 'fish')
        await ctx.send(f"已將此頻道 <#{channel_id}> 設為本伺服器海釣的公告頻道。")
    
    @commands.command(
        name="set_ore_announce_channel",
        help="將此頻道設為採礦公告頻道（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def set_ore_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channel_id = ctx.channel.id
        await save_channels(guild_id, channel_id, 'ore')
        await ctx.send(f"已將此頻道 <#{channel_id}> 設為本伺服器採集的公告頻道。")

    @commands.command(
        name="unset_announce_channel",
        help="取消本伺服器的公告頻道設定（需具管理伺服器或管理員權限）"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def unset_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channels = await get_channels(guild_id)
        channel_id = ctx.channel.id
        if str(channel_id) in channels:
            await remove_channel(guild_id, channel_id)
            await ctx.send("已取消此頻道 <#{channel_id}> 的公告頻道設定。")
        else:
            await ctx.send("此頻道非本伺服器的公告頻道。")

    @commands.command(
        name="show_announce_channel",
        help="顯示本伺服器目前設定的公告頻道"
    )
    async def show_channel(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channels = await get_channels(guild_id)
        messages = []
        type_mapping = {'fish': '海釣', 'ore': '採集'}
        print(channels)
        for channel_id, notice_type in channels.items():
            messages.append(f"目前本伺服器的{type_mapping[notice_type]}公告頻道為 <#{channel_id}> 。")
        if channel_id:
            await ctx.send("\n".join(messages))
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")
    
    @commands.command(
        name="get_bait",
        help="取得目前時段/下個時段的釣場魚餌資訊"
    )
    async def get_bait(self, ctx: commands.Context):
        await ctx.send(get_bait(datetime.now(tz=TIMEZONE)))

    @commands.command(
        name="get_source",
        help="顯示特殊魚餌取得方式"
    )
    async def get_source(self, ctx: commands.Context):
        await ctx.send(get_source())
    
    @commands.command(name="set_ore", help="set_ore <name> <time:int> <place>  — 設定或更新一個監控礦物")
    async def set_ore(self, ctx: commands.Context, name: str, time: str, place: str):
        await set_ore(name, time, place)
        await ctx.send(f"已設定 `{name}` => {{'time': {time}, 'place': '{place}'}}。")

    @commands.command(name="remove_ore", help="remove_ore <name>  — 移除監控採集")
    async def remove_ore(self, ctx: commands.Context, name: str):
        await remove_ore(name)
        await ctx.send(f"已移除 `{name}` 的採集監控。")
    
    @commands.command(name="list_ore", help="檢視所有監控採集")
    async def list_ore(self, ctx: commands.Context):
        ores = await get_ores()
        messages = ["目前監控採集:"]
        for ore, ore_info in ores.items():
            messages.append(f"已設定 `{ore}` => 採集時間: `{ore_info['time']}` , 採集地區: `{ore_info['place']}`。")
        await ctx.send("\n".join(messages))


# ---------- 啟動 ----------

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


def _task_done_callback(task: asyncio.Task):
    """
    當 bot.start 的 background task 完成時呼叫（不論成功或失敗）。
    若有 exception，就記錄完整 traceback。
    """
    try:
        exc = task.exception()  # 這會把 exception 提取出來（若有的話）
    except asyncio.CancelledError:
        logger.info("Bot task was cancelled.")
        return

    if exc:
        # task.exception() 已包含堆疊訊息，這裡用 logger.exception 記錄
        logger.exception("Bot task raised an exception:", exc_info=exc)
        os.system('kill 1')
    else:
        logger.info("Bot task finished without exception (unexpected for long-running bot).")


# 主流程：啟動 http server 與 discord bot 並處理 shutdown
async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    bot = AnnounceBot(command_prefix="？")

    await redis_wrapper.connect()

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
    bot_task.add_done_callback(_task_done_callback)
    # await bot.start(TOKEN)

    # 等待關機事件
    await shutdown_event.wait()
    logger.info("Shutdown signal received — beginning graceful shutdown...")

    # 先關閉 discord bot
    try:
        await bot.close()
        logger.info("Discord bot closed.")
    except Exception as e:
        logger.exception("Error closing bot: %s", e)
        os.system('kill 1')

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
