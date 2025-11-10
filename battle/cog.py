import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, Optional, cast

from ballsdex.core.models import BallInstance, Player
from ballsdex.packages.battle.menu import BattleMenu
from ballsdex.packages.battle.battling_user import BattlingUser
from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallInstanceTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class Battle(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.battles = {}

    def get_battle(self, interaction: discord.Interaction) -> Optional[BattleMenu]:
        guild_id = interaction.guild_id
        if guild_id in self.battles:
            return self.battles[guild_id]
        return None

    def remove_battle(self, guild_id: int):
        if guild_id in self.battles:
            del self.battles[guild_id]

    @app_commands.command()
    async def begin(self, interaction: discord.Interaction["BallsDexBot"], user: discord.User):
        """
        Begin a battle with the chosen user.

        Parameters
        ----------
        user: discord.User
            The user you want to battle with
        """
        if user.bot:
            await interaction.response.send_message("You cannot battle with bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot battle with yourself.", ephemeral=True
            )
            return

        player1, _ = await Player.get_or_create(discord_id=interaction.user.id)
        player2, _ = await Player.get_or_create(discord_id=user.id)

        battle = self.get_battle(interaction)
        if battle:
            await interaction.response.send_message(
                "There is already an ongoing battle in this guild.", ephemeral=True
            )
            return

        battle_menu = BattleMenu(
            self, interaction, BattlingUser(interaction.user, player1), BattlingUser(user, player2)
        )
        self.battles[interaction.guild_id] = battle_menu
        await battle_menu.start()
        await interaction.response.send_message("Battle started!", ephemeral=True)

    @app_commands.command()
    async def add(
        self,
        interaction: discord.Interaction,
        ball: BallInstanceTransform,
    ):
        """
        Add a countryball to the ongoing battle.

        Parameters
        ----------
        ball: BallInstanceTransform
            The countryball you want to add to the battle
        """
        if not ball:
            return

        battle = self.get_battle(interaction)
        if not battle:
            await interaction.response.send_message("There is no ongoing battle.", ephemeral=True)
            return

        battler = battle.get_battler(interaction.user)
        if not battler:
            await interaction.response.send_message("You are not part of this battle.", ephemeral=True)
            return

        if ball.player.discord_id != interaction.user.id:
            await interaction.response.send_message(
                "You can only add your own countryballs to the battle.", ephemeral=True
            )
            return

        if ball in battler.proposal:
            await interaction.response.send_message(
                "This countryball is already in your proposal.", ephemeral=True
            )
            return

        battler.proposal.append(ball)
        await interaction.response.send_message(
            f"{ball.countryball.country} added to the battle.", ephemeral=True
        )
        await battle.update_message()

    @app_commands.command()
    async def remove(
        self,
        interaction: discord.Interaction,
        ball: BallInstanceTransform,
    ):
        """
        Remove a countryball from the ongoing battle.

        Parameters
        ----------
        ball: BallInstanceTransform
            The countryball you want to remove from the battle
        """
        if not ball_instance:
            return

        battle = self.get_battle(interaction)
        if not battle:
            await interaction.response.send_message("There is no ongoing battle.", ephemeral=True)
            return

        battler = battle.get_battler(interaction.user)
        if not battler:
            await interaction.response.send_message("You are not part of this battle.", ephemeral=True)
            return

        if ball not in battler.proposal:
            await interaction.response.send_message(
                "This countryball is not in your proposal.", ephemeral=True
            )
            return

        battler.proposal.remove(ball)
        await interaction.response.send_message(
            f"{ball.countryball.country} removed from the battle.", ephemeral=True
        )
        await battle.update_message()

    @app_commands.command()
    async def all(self, interaction: discord.Interaction):
        """
        Add all countryballs owned by the user to the ongoing battle.
        """
        battle = self.get_battle(interaction)
        if not battle:
            await interaction.response.send_message("There is no ongoing battle.", ephemeral=True)
            return

        battler = battle.get_battler(interaction.user)
        if not battler:
            await interaction.response.send_message("You are not part of this battle.", ephemeral=True)
            return

        player = await Player.get(discord_id=interaction.user.id)
        all_balls = await BallInstance.filter(player=player)

        if not all_balls:
            await interaction.response.send_message("You do not own any countryballs.", ephemeral=True)
            return

        added_balls = []
        for ball in all_balls:
            if ball not in battler.proposal:
                battler.proposal.append(ball)
                added_balls.append(ball)

        if not added_balls:
            await interaction.response.send_message("All your countryballs are already in the battle.", ephemeral=True)
            return

        display_balls = added_balls[:10]
        more_balls = len(added_balls) - len(display_balls)
        display_message = "\n".join(f"{ball.countryball.country}" for ball in display_balls)
        if more_balls > 0:
            display_message += f"\n...and {more_balls} more."

        await interaction.response.send_message(
            f"The following countryballs have been added to the battle:\n{display_message}", ephemeral=True
        )
        await battle.update_message()