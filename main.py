import discord
import os
from keep import keep_alive
import asyncio
import datetime
import pytz

# グローバル変数として時間指定を定義
TARGET_HOUR = 8
TARGET_MINUTE = 0
JST = pytz.timezone('Asia/Tokyo')


class MyClient(discord.Client):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_time = self.calculate_target_time()
        self.posted_today = False  # 今日投稿したかどうかのフラグ

    def calculate_target_time(self):
        now_jst = datetime.datetime.now(JST)
        target_time = now_jst.replace(hour=TARGET_HOUR,
                                    minute=TARGET_MINUTE,
                                    second=0,
                                    microsecond=0)
        if target_time < now_jst:
            target_time += datetime.timedelta(days=1)
        return target_time

    async def on_ready(self):
        print(f'ログインしました: {self.user}')

        # Botのステータスを設定
        custom_activity = discord.CustomActivity(name="今日も工場勤務")
        await self.change_presence(status=discord.Status.online,
                                    activity=custom_activity)

        self.loop.create_task(self.scheduled_post())

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

    async def scheduled_post(self):
        await self.wait_until_ready()

        while True:
            now_jst = datetime.datetime.now(JST)
            if now_jst >= self.target_time and not self.posted_today:
                channel = discord.utils.get(self.get_all_channels(),
                                            name="チャット")
                if channel:
                    message = await channel.send("本日ヴァロ募集")
                    await message.add_reaction("⭕")
                    await message.add_reaction("❌")
                    self.posted_today = True
                else:
                    print("チャットチャンネルが見つかりません。")

            if now_jst.day != self.target_time.day:
                self.posted_today = False
                self.target_time = self.calculate_target_time(
                )  #日付が変わったら、時刻を再計算

            await asyncio.sleep(60)


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
keep_alive()
try:
    client.run(os.getenv('TOKEN'))
except:
    os.system("kill 1")
