# announce_bot.py
"""
Discord 排程公告 BOT 範例
功能：
- 管理員透過指令設定本伺服器的發訊頻道 (persist to channels.json)
- 背景任務：在 Asia/Taipei 時區，每日 01:55 起每 2 小時發送公告 (01:55,03:55,05:55,...)
使用方式：
- 設定環境變數 DISCORD_BOT_TOKEN，或在下方直接填入 token（不推薦）
"""

import discord
from discord.ext import commands, tasks
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo  # Python 3.9+
import os
from typing import Dict, Optional
from fish_notice import get_bait
from datetime import datetime

# ---------- 設定 ----------
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # 建議用環境變數儲存 token
CHANNELS_FILE = Path("channels.json")
TIMEZONE = ZoneInfo("Asia/Taipei")
SCHEDULE_HOURS = list(range(1, 24, 2))  # 1,3,5,...23 => 01:55,03:55,...
SCHEDULE_MINUTE = 55
# -------------------------

# Helper: 儲存 / 載入已註冊頻道（以 guild_id -> channel_id 映射）
def load_channels() -> Dict[str, int]:
    if CHANNELS_FILE.exists():
        try:
            with CHANNELS_FILE.open("r", encoding="utf-8") as f:
                return json.load(f).get("guilds", {})
        except Exception:
            return {}
    return {}

def save_channels(channels: Dict[str, int]):
    with CHANNELS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"guilds": channels}, f, ensure_ascii=False, indent=2)

class AnnounceBot(commands.Bot):
    def __init__(self, command_prefix: str = "!", **options):
        intents = discord.Intents.default()
        # 如果使用 prefix 命令，通常需要 message_content intent（在開發者後台同時打開）
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents, **options)

        # 載入頻道
        self.registered_channels: Dict[str, int] = load_channels()

        # 背景任務管理
        self._scheduler_task: Optional[asyncio.Task] = None
        self.bg_task_started = False

        # 註冊命令
        self.add_command(commands.Command(self.set_channel, name="set_announce_channel"))
        self.add_command(commands.Command(self.unset_channel, name="unset_announce_channel"))
        self.add_command(commands.Command(self.show_channel, name="show_announce_channel"))

    async def setup_hook(self):
        # Bot ready 之前呼叫（discord.py v2 支援）
        # 啟動背景任務
        if not self.bg_task_started:
            self._scheduler_task = self.loop.create_task(self._schedule_loop())
            self.bg_task_started = True

    async def on_ready(self):
        print(f"Logged in as {self.user} (id: {self.user.id})")
        print("------")

    # ---------------- 指令實作 ----------------
    async def set_channel(self, ctx: commands.Context):
        """設定本伺服器的公告頻道（在此頻道執行指令即設定為公告頻道）"""
        # 權限檢查：管理員或有 manage_guild
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
            await ctx.send("您需要具備 管理伺服器 或 管理員 權限才能設定公告頻道。")
            return

        guild_id = str(ctx.guild.id)
        channel_id = ctx.channel.id
        self.registered_channels[guild_id] = channel_id
        save_channels(self.registered_channels)
        await ctx.send(f"已將此頻道 <#{channel_id}> 設為本伺服器的公告頻道。")

    async def unset_channel(self, ctx: commands.Context):
        """取消本伺服器的公告頻道設定"""
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
            await ctx.send("您需要具備 管理伺服器 或 管理員 權限才能取消設定。")
            return

        guild_id = str(ctx.guild.id)
        if guild_id in self.registered_channels:
            del self.registered_channels[guild_id]
            save_channels(self.registered_channels)
            await ctx.send("已取消本伺服器的公告頻道設定。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")

    async def show_channel(self, ctx: commands.Context):
        """顯示本伺服器目前設定的公告頻道（若有的話）"""
        guild_id = str(ctx.guild.id)
        channel_id = self.registered_channels.get(guild_id)
        if channel_id:
            await ctx.send(f"目前本伺服器的公告頻道為 <#{channel_id}> 。")
        else:
            await ctx.send("本伺服器尚未設定公告頻道。")

    # ----------------- 排程與發送 -----------------
    async def _schedule_loop(self):
        """背景排程主迴圈：計算下一次執行時間並等待到時間，然後發送公告至所有註冊頻道。"""
        await self.wait_until_ready()  # 確保 bot ready
        while not self.is_closed():
            now = datetime.now(tz=TIMEZONE)
            next_run = self._next_schedule_after(now)
            wait_seconds = (next_run - now).total_seconds()
            # log
            print(f"[Scheduler] 現在時間 {now.isoformat()}，下一次執行 {next_run.isoformat()}（等待 {int(wait_seconds)} 秒）")
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                break

            # 到時間了：發送公告
            await self._send_announcement(next_run)

            # 小短暫休息，再進入下一循環（避免瞬間重入）
            await asyncio.sleep(1)

    def _next_schedule_after(self, now: datetime) -> datetime:
        """回傳下一個排程發生的 timezone-aware datetime（包含同日剩下的時段或隔日）"""
        # 檢查今天剩下的時間
        today = now.date()
        candidates = []
        for h in SCHEDULE_HOURS:
            cand = datetime.combine(today, time(hour=h, minute=SCHEDULE_MINUTE, second=0), tzinfo=TIMEZONE)
            if cand > now:
                candidates.append(cand)
        if candidates:
            return min(candidates)
        # 若今天沒有，找明天的第一個時段
        tomorrow = today + timedelta(days=1)
        first = datetime.combine(tomorrow, time(hour=SCHEDULE_HOURS[0], minute=SCHEDULE_MINUTE, second=0), tzinfo=TIMEZONE)
        return first

    async def _send_announcement(self, run_time: datetime):
        """對所有已註冊頻道發送公告（會檢查頻道是否仍有效）"""
        guilds_to_remove = []
        for guild_id_str, channel_id in list(self.registered_channels.items()):
            try:
                channel = self.get_channel(channel_id)
                if channel is None:
                    # 嘗試 fetch（提升容錯）
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception:
                        channel = None
                if channel is None:
                    # 頻道不存在或 BOT 無權限存取，將此 guild 的設定標為移除（稍後保存）
                    print(f"[Warning] 無法存取頻道 ID {channel_id}（guild {guild_id_str}），將取消註冊。")
                    guilds_to_remove.append(guild_id_str)
                    continue

                # 建立要發送的訊息（可以自訂）
                timestamp = run_time.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
                message = get_bait(datetime.now())

                await channel.send(message)
                print(f"[Info] 已在頻道 {channel_id} 發送公告。")
            except discord.Forbidden:
                print(f"[Error] BOT 在頻道 {channel_id} 被拒絕權限 (Forbidden)。 將移除此頻道設定。")
                guilds_to_remove.append(guild_id_str)
            except Exception as e:
                print(f"[Error] 在發送至頻道 {channel_id} 時發生錯誤: {e}")

        # 移除失效的 guild 設定並儲存
        if guilds_to_remove:
            for gid in guilds_to_remove:
                self.registered_channels.pop(gid, None)
            save_channels(self.registered_channels)

# ---------- 啟動 BOT ----------
def main():
    if TOKEN is None:
        print("請先透過環境變數 DISCORD_BOT_TOKEN 設定機器人 token，或在程式中修改 TOKEN 變數。")
        return

    bot = AnnounceBot(command_prefix="!")

    try:
        bot.run(TOKEN)
    except Exception as e:
        print("Bot 無法啟動:", e)

if __name__ == "__main__":
    main()
