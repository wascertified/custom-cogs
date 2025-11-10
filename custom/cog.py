import discord, random, json, os, asyncio, time
from discord import app_commands
from discord.ext import commands
from ballsdex.settings import settings
from collections import defaultdict
from tortoise.functions import Count
from ballsdex.core.models import Ball, BallInstance, Player, balls, Special
from ballsdex.core.utils.paginator import FieldPageSource, Pages, TextPageSource
from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

COOLDOWN_FILE = os.path.join(os.path.dirname(__file__), "cooldown.json")
COOLDOWN_SECONDS = 86400

def load_cooldowns():
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    with open(COOLDOWN_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f)

class Custom(commands.GroupCog, group_name="custom"):
    """
    Custom commands for the bot.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command()
    async def rarity(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        chunked: bool = True,
        include_disabled: bool = False,
    ):
        """
        Generate a list of countryballs ranked by rarity.

        Parameters
        ----------
        chunked: bool
            Group together countryballs with the same rarity.
        include_disabled: bool
            Include the countryballs that are disabled or with a rarity of 0.
        """
        await interaction.response.defer(ephemeral=True)
        text = ""
        balls_queryset = Ball.all().order_by("rarity")
        if not include_disabled:
            balls_queryset = balls_queryset.filter(rarity__gt=0, enabled=True)
        sorted_balls = await balls_queryset

        if chunked:
            indexes: dict[float, list[Ball]] = defaultdict(list)
            for ball in sorted_balls:
                indexes[ball.rarity].append(ball)
            i = 1
            for chunk in indexes.values():
                for ball in chunk:
                    text += f"{i}. {ball.country}\n"
                i += len(chunk)
        else:
            for i, ball in enumerate(sorted_balls, start=1):
                text += f"{i}. {ball.country}\n"

        source = TextPageSource(text, prefix="```md\n", suffix="```")
        pages = Pages(source=source, interaction=interaction, compact=True)
        await pages.start(ephemeral=True)
    
    @app_commands.command()
    async def claim(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Claim a random countryball once every day.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        cooldowns = await asyncio.to_thread(load_cooldowns)
        user_id = str(interaction.user.id)
        now = int(time.time())
        last_claim = int(cooldowns.get(user_id, 0))
        remaining = COOLDOWN_SECONDS - (now - last_claim)
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            await interaction.followup.send(
                f"You have already claimed your daily {settings.collectible_name}. Please try again in {hours}h {minutes}m {seconds}s.",
                ephemeral=True,
            )
            return

        player, _ = await Player.get_or_create(discord_id=interaction.user.id)

        available_balls = [ball for ball in balls.values() if ball.enabled and ball.rarity > 0]

        if not available_balls:
            await interaction.followup.send(
                f"There are no {settings.collectible_name} available to claim at the moment.", ephemeral=True
            )
            return

        specials = await Special.all()
        special_weights = [special.rarity for special in specials]
        total_weight = sum(special_weights) + len(available_balls)
        weights = special_weights + [1] * len(available_balls)

        claimed_ball = random.choices(specials + available_balls, weights=weights, k=1)[0]

        ball_instance = await BallInstance.create(
            ball=claimed_ball if isinstance(claimed_ball, Ball) else None,
            player=player,
            attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            special=claimed_ball if isinstance(claimed_ball, Special) else None,
        )

        cooldowns[user_id] = now
        await asyncio.to_thread(save_cooldowns, cooldowns)

        _, file, _ = await ball_instance.prepare_for_message(interaction)
        await interaction.followup.send(
            content=f"Congratulations! You have claimed a {claimed_ball.country if isinstance(claimed_ball, Ball) else claimed_ball.name} {settings.collectible_name}!",
            file=file,
            ephemeral=True,
        )
        file.close()

    @app_commands.command()
    async def leaderboard(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Show the leaderboard of users with the most caught countryballs.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        players = await Player.annotate(ball_count=Count("balls")).order_by("-ball_count").limit(10)
        
        if not players:
            await interaction.followup.send("No players found.", ephemeral=True)
            return

        entries = []
        for i, player in enumerate(players):
            user = self.bot.get_user(player.discord_id)
            if user is None:
                user = await self.bot.fetch_user(player.discord_id)

            entries.append((f"{i + 1}. {user.name}", f"{settings.collectible_name}: {getattr(player, 'ball_count', 0)}"))

        source = FieldPageSource(entries, per_page=5, inline=False)
        source.embed.title = "Top 10 players"
        source.embed.color = discord.Color.gold()
        source.embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        pages = Pages(source=source, interaction=interaction)
        await pages.start(ephemeral=True)