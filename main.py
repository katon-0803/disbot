import discord
import os
import asyncio
import datetime
import pytz
import aiohttp
import json
from discord import app_commands
from keep import keep_alive

JST = pytz.timezone('Asia/Tokyo')
TOKEN = os.getenv('TOKEN')

class MyClient(discord.Client):
    TARGET_HOUR = 8
    TARGET_MINUTE = 30
    poll_channel_name = "募集"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = discord.app_commands.CommandTree(self)
        self.target_time = self.calculate_target_time()
        self.posted_today = False  # 今日投稿したかどうかのフラグ
        self.session = None  # aiohttp sessionを初期化
        self.poll_message_id = None  # poll message id を初期化
        self.text = "！募集告知！\n本日20時半ヴァロ募集"

    def calculate_target_time(self):
        now_jst = datetime.datetime.now(JST)
        target_time = now_jst.replace(
            hour=self.TARGET_HOUR, minute=self.TARGET_MINUTE, second=0, microsecond=0
        )
        if target_time < now_jst:
            target_time += datetime.timedelta(days=1)
        return target_time

    async def on_ready(self):
        print(f'ログインしました: {self.user}')

        # Botのステータスを設定
        custom_activity = discord.CustomActivity(name="今日も工場勤務")
        await self.change_presence(status=discord.Status.online, activity=custom_activity)
        self.session = aiohttp.ClientSession()
        await self.tree.sync()
        print(f"Command tree: {self.tree.get_commands()}")
        self.loop.create_task(self.scheduled_post())

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_message(self, message):
        print(f'送信: {message.author}: {message.content}')
        if message.author == self.user:
            return

        if message.content == 'よう':
            await message.channel.send('こんにちは')

        if message.content == '今日やった？':
            if self.posted_today:
                await message.channel.send('今日はもうやったよ！')
            else:
                await message.channel.send('まだやってないよ！')

        if message.content == '投票結果':
            if not hasattr(self, 'poll_message_id') or self.poll_message_id is None:
                await message.channel.send("投票がまだ開始されていません。")
                return
            await self.get_poll_results(message.channel, self.poll_message_id)


    async def create_poll(self, channel):
        url = f"https://discord.com/api/v9/channels/{channel.id}/messages"
        headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

        payload = {
            "poll": {
                "question": {"text": self.text},
                "answers": [
                    {
                        "poll_media": {
                            "text": "参加する",
                            "emoji": {"name": "⭕"},
                        }
                    },
                    {
                        "poll_media": {
                            "text": "不参加",
                            "emoji": {"name": "❌"},
                        }
                    },
                ],
                "duration": 12,
            }
        }

        async with self.session.post(
            url, headers=headers, data=json.dumps(payload)
        ) as response:
            if response.status == 200:
                data = await response.json()
                self.poll_message_id = data["id"]
                print(f"Poll created successfully! Message ID: {self.poll_message_id}")
                return data
            else:
                error_data = await response.text()
                print(f"Error creating poll: {response.status} - {error_data}")
                return None

    async def get_poll_results(self, channel, message_id):
        url = f"https://discord.com/api/v9/channels/{channel.id}/messages/{message_id}"
        headers = {"Authorization": f"Bot {TOKEN}"}
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                poll = data.get("poll")
                if poll and poll.get("results"):
                    results = poll["results"]
                    if results.get("answer_counts"):
                        message_text = "投票結果:\n"
                        for answer_count in results["answer_counts"]:
                            answer_id = answer_count["id"]
                            count = answer_count["count"]
                            answer_text = poll["answers"][answer_id - 1]["poll_media"]["text"]
                            message_text += f"- {answer_text}: {count} 票\n"
                        await channel.send(message_text)
                    else:
                        await channel.send("投票結果が見つかりません。")
                else:
                    await channel.send("投票結果が見つかりません。")

            else:
                print(f"Error getting poll results: {response.status}")
                await channel.send("投票結果の取得に失敗しました。")

    @app_commands.command(name="time_set", description="投稿時間を設定します。")
    @app_commands.describe(hour="時間", minute="分")
    async def time_setting(self, interaction: discord.Interaction, hour: int, minute: int):
        print(f"command {interaction.command.name} is called")
        if 0 <= hour <= 23 and 0 <= minute <= 59:
                self.TARGET_HOUR = hour
                self.TARGET_MINUTE = minute
                self.target_time = self.calculate_target_time()
                await interaction.response.send_message(f"投稿時間を{hour}時{minute}分に設定しました。",ephemeral=True)
        else:
                await interaction.response.send_message("無効な時間です。",ephemeral=True)

    @app_commands.command(name="debug_poll", description="デバッグ用の投票を開始します。")
    async def debug_poll(self, interaction: discord.Interaction):
        print(f"command {interaction.command.name} is called")
        channel = interaction.channel
        poll_data = await self.create_poll(channel)
        if poll_data:
            await interaction.response.send_message("デバッグ用投票を開始しました。", ephemeral=True)

    @app_commands.command(name="channel_set", description="投票機能を行うテキストチャンネルを設定します。")
    @app_commands.describe(channel_name="チャンネル名")
    async def set_poll_channel(self, interaction: discord.Interaction, channel_name: str):
        print(f"command {interaction.command.name} is called")
        self.poll_channel_name = channel_name
        await interaction.response.send_message(f"投票チャンネルを {channel_name} に設定しました。", ephemeral=True)

    async def scheduled_post(self):
        await self.wait_until_ready()

        while True:
            now_jst = datetime.datetime.now(JST)
            if now_jst >= self.target_time and not self.posted_today:
                channel = discord.utils.get(self.get_all_channels(), name=self.poll_channel_name)
                if channel:
                    poll_data = await self.create_poll(channel)
                    if poll_data:
                        self.posted_today = True
                else:
                    print(f"{self.poll_channel_name}チャンネルが見つかりません。")

            if now_jst.day != self.target_time.day:
                self.posted_today = False
                self.target_time = self.calculate_target_time()

            await asyncio.sleep(60)

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
keep_alive()
try:
    client.run(os.getenv('TOKEN'))
except:
    os.system("kill")