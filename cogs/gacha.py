import random
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

# ==============================
# 定数
# ==============================
GACHA_PRICE_SINGLE = 500
GACHA_PRICE_TEN = 4500
PROVIDER_REWARD = 300

EMBED_COLOR = 0x9B59B6
GACHA_LOG_TC_ID = 1461102916181164143

# ==============================
# 永続View
# ==============================
class GachaView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="🎱 単発", style=discord.ButtonStyle.secondary, custom_id="gacha:single")
    async def single(self, interaction: discord.Interaction, button: Button):
        await self.cog.run_gacha(interaction, count=1)

    @discord.ui.button(label="🎉 10連", style=discord.ButtonStyle.secondary, custom_id="gacha:ten")
    async def ten(self, interaction: discord.Interaction, button: Button):
        await self.cog.run_gacha(interaction, count=10)

    @discord.ui.button(label="📈 コンプ率", style=discord.ButtonStyle.secondary, custom_id="gacha:completion")
    async def comp(self, interaction: discord.Interaction, button: Button):
        await self.cog.show_completion(interaction)

    @discord.ui.button(label="💰 提供者", style=discord.ButtonStyle.secondary, custom_id="gacha:provider")
    async def provider(self, interaction: discord.Interaction, button: Button):
        await self.cog.show_provider_income(interaction)

# ==============================
# COG
# ==============================
class GachaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pool = bot.db
    
        bot.add_view(GachaView(self))

    # ------------------------------
    # 安全DM
    # ------------------------------
    async def safe_dm(self, user: discord.User, *, content=None, embed=None):
        try:
            await user.send(content=content, embed=embed)
            return True
        except discord.Forbidden:
            return False

    # ------------------------------
    # /ガチャ
    # ------------------------------
    @app_commands.command(name="ガチャ", description="ボイメガチャを表示")
    @app_commands.default_permissions(administrator=True)
    async def gacha(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="ボイメガチャ🎙",
            color=EMBED_COLOR,
            description=(
                "ボタンを押すとDMで結果が届く。\n\n"
                "🎱 単発：500G\n"
                "🎉 10連：4,500G\n"
                "📈 コンプ率\n"
                "💰 提供者収益"
            )
        )

        await interaction.response.send_message("設置完了。", ephemeral=True)
        await interaction.channel.send(embed=embed, view=GachaView(self))

    # ------------------------------
    # ガチャ実行
    # ------------------------------
    async def run_gacha(self, interaction: discord.Interaction, count: int):
        user = interaction.user
        price = GACHA_PRICE_SINGLE if count == 1 else GACHA_PRICE_TEN

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    balance = await conn.fetchval(
                        "SELECT balance FROM wallet WHERE user_id=$1 FOR UPDATE",
                        user.id
                    )

                    if balance is None or balance < price:
                        await interaction.response.send_message(
                            "ゴールドが足りない。現実を直視しろ。",
                            ephemeral=True
                        )
                        return

                    before_balance = balance

                    owned_ids = {
                        r["gacha_list_id"]
                        for r in await conn.fetch(
                            "SELECT gacha_list_id FROM gacha_log WHERE user_id=$1",
                            user.id
                        )
                    }

                    all_list = await conn.fetch("SELECT * FROM gacha_list")
                    available = [r for r in all_list if r["id"] not in owned_ids]

                    if count == 10 and len(available) < 10:
                        await interaction.response.send_message(
                            "10連するほど残ってない。",
                            ephemeral=True
                        )
                        return

                    if len(available) < count:
                        await interaction.response.send_message(
                            "もう引けるものがない。",
                            ephemeral=True
                        )
                        return

                    results = random.sample(available, count)

                    await conn.execute(
                        "UPDATE wallet SET balance = balance - $1 WHERE user_id=$2",
                        price, user.id
                    )

                    for r in results:
                        await conn.execute(
                            "INSERT INTO wallet (user_id, balance) VALUES ($1,0) "
                            "ON CONFLICT (user_id) DO NOTHING",
                            r["user_id"]
                        )

                        await conn.execute(
                            "UPDATE wallet SET balance = balance + $1 WHERE user_id=$2",
                            PROVIDER_REWARD, r["user_id"]
                        )

                        await conn.execute(
                            "INSERT INTO gacha_log (user_id, gacha_list_id) VALUES ($1,$2)",
                            user.id, r["id"]
                        )

                    after_balance = await conn.fetchval(
                        "SELECT balance FROM wallet WHERE user_id=$1",
                        user.id
                    )

        except Exception:
            await interaction.response.send_message(
                "内部エラー。機嫌が悪いらしい。",
                ephemeral=True
            )
            return

        await interaction.response.send_message("結果はDMだ。", ephemeral=True)

        # ログ送信
        for r in results:
            await self.send_log(interaction.guild, user, r)

        # DMは1通
        await self.send_result_dm_bulk(
            guild=interaction.guild,
            user=user,
            results=results,
            before_balance=before_balance,
            after_balance=after_balance
        )

    # ------------------------------
    # 結果DM（まとめ）
    # ------------------------------
    async def send_result_dm_bulk(self, guild, user, results, before_balance, after_balance):
        embed = discord.Embed(
            title=f"🎰 ガチャ結果（{len(results)}件）",
            color=EMBED_COLOR
        )

        for gacha in results:
            member = guild.get_member(gacha["user_id"])
            name = gacha["name"] or "名称不明"
            url = gacha["url"] or "https://example.com"
            display = member.display_name if member else "退会済み"
            mention = member.mention if member else f"<@{gacha['user_id']}>"

            embed.add_field(
                name=f"🎙 ボイメNo.{gacha['id']}",
                value=f"[{name}]({url})\nvoiced by {mention}（{display}）",
                inline=False
            )

            if member and not embed.author.name:
                embed.set_author(
                    name=display,
                    icon_url=member.display_avatar.url
                )

        await self.safe_dm(
            user,
            content =  f"残高：{before_balance}G → {after_balance}G",
            embed=embed
        )
        

    # ------------------------------
    # ログ
    # ------------------------------
    async def send_log(self, guild, buyer, gacha):
        channel = guild.get_channel(GACHA_LOG_TC_ID)
        if not channel:
            return

        embed = discord.Embed(
            title="ボイメガチャ購入ログ",
            color=EMBED_COLOR,
            description=(
                f"購入者：{buyer.mention}\n"
                f"提供者：<@{gacha['user_id']}>\n"
                f"当選：[{gacha['name']}]({gacha['url']})"
            )
        )

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # ------------------------------
    # コンプ率
    # ------------------------------
    async def show_completion(self, interaction: discord.Interaction):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH totals AS (
                    SELECT
                        user_id AS owner_id,
                        COUNT(*) AS total_count
                    FROM gacha_list
                    GROUP BY user_id
                ),
                owned AS (
                    SELECT
                        gl.user_id AS owner_id,
                        COUNT(DISTINCT gl.id) AS owned_count
                    FROM gacha_log g
                    JOIN gacha_list gl ON gl.id = g.gacha_list_id
                    WHERE g.user_id = $1
                    GROUP BY gl.user_id
                )
                SELECT
                    t.owner_id,
                    COALESCE(o.owned_count, 0) AS owned_count,
                    t.total_count
                FROM totals t
                LEFT JOIN owned o ON o.owner_id = t.owner_id
                ORDER BY (COALESCE(o.owned_count, 0)::float / t.total_count) DESC
                """,
                interaction.user.id
            )

        # ===== 3) トータル所持率 =====
            total_all = await conn.fetchval(
                "SELECT COUNT(*) FROM gacha_list"
            )
            owned_all = await conn.fetchval(
                f"""
                SELECT COUNT(*)
                FROM gacha_log 
                WHERE user_id = $1;
                """,
                interaction.user.id
            )

        lines = []
        
        total_rate = (owned_all / total_all * 100) if total_all else 0
        lines.append(
            f"📊 **トータル所持率**：{owned_all}/{total_all}（{total_rate:.1f}%）"
        )
        lines.append("")

        for r in rows:
            owner_id = r["owner_id"]
            owned = r["owned_count"]
            total = r["total_count"]
            rate = (owned / total * 100) if total else 0

            member = interaction.guild.get_member(owner_id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(owner_id)
                except discord.NotFound:
                    member = None

            owner_name = member.display_name if member else str(owner_id)
            lines.append(f"{owner_name}：{owned}/{total}（{rate:.1f}%）")

        text = "\n".join(lines) if lines else "データがありません。"

        await interaction.response.send_message(
            text,
            ephemeral=True
        )


    # ------------------------------
    # 提供者収益
    # ------------------------------
    async def show_provider_income(self, interaction: discord.Interaction):
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM gacha_log gl "
                "JOIN gacha_list g ON gl.gacha_list_id = g.id "
                "WHERE g.user_id=$1",
                interaction.user.id
            )

        await interaction.response.send_message(
            f"あなたのボイメは **{count}回** 引かれた。\n"
            f"獲得ゴールド：**{count * PROVIDER_REWARD}G**",
            ephemeral=True
        )

# ==============================
# setup
# ==============================
async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCog(bot))
