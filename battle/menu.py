import asyncio
import discord
from discord.ui import View, Button
from typing import TYPE_CHECKING, List, Optional

from ballsdex.packages.battle.battling_user import BattlingUser
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class BattleMenu:
    def __init__(
        self,
        cog: "Battle",
        interaction: discord.Interaction["BallsDexBot"],
        battler1: BattlingUser,
        battler2: BattlingUser,
    ):
        self.cog = cog
        self.bot = interaction.client
        self.channel: discord.TextChannel = interaction.channel
        self.battler1 = battler1
        self.battler2 = battler2
        self.embed = discord.Embed()
        self.task: Optional[asyncio.Task] = None
        self.current_view: BattleView = BattleView(self)
        self.message: Optional[discord.Message] = None

    def get_battler(self, user: discord.User) -> Optional[BattlingUser]:
        if user.id == self.battler1.user.id:
            return self.battler1
        elif user.id == self.battler2.user.id:
            return self.battler2
        return None

    def _generate_embed(self):
        self.embed.title = f"{settings.plural_collectible_name.title()} Battle"
        self.embed.color = discord.Colour.blurple()
        self.embed.description = (
            f"Add or remove {settings.plural_collectible_name} you want to use in the battle.\n"
            "Once you're finished, click the lock button below to confirm your proposal.\n"
            "You can also lock with nothing if you're receiving a gift.\n\n"
            "*This battle will timeout in 30 minutes.*"
        )
        self.embed.set_footer(
            text="This message is updated every 15 seconds, "
            "but you can keep on editing your proposal."
        )
        self.embed.clear_fields()

        def format_proposal(proposal):
            display_balls = proposal[:10]
            more_balls = len(proposal) - len(display_balls)
            display_message = "\n".join(
                f"- {self.bot.get_emoji(ball.countryball.emoji_id)} {ball.countryball.country} (#{ball.id})"
                for ball in display_balls
            )
            if more_balls > 0:
                display_message += f"\n...and {more_balls} more."
            return display_message or "No balls added."

        self.embed.add_field(
            name=f"{self.battler1.user.display_name}'s Proposal",
            value=format_proposal(self.battler1.proposal),
            inline=True,
        )
        self.embed.add_field(
            name=f"{self.battler2.user.display_name}'s Proposal",
            value=format_proposal(self.battler2.proposal),
            inline=True,
        )

    async def update_message(self):
        self._generate_embed()
        await self.message.edit(embed=self.embed)

    async def update_message_loop(self):
        """
        A loop task that updates each 15 seconds the menu with the new content.
        """
        assert self.task
        start_time = discord.utils.utcnow()

        while True:
            await asyncio.sleep(15)
            if discord.utils.utcnow() - start_time > discord.utils.timedelta(minutes=30):
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The battle timed out")
                return

            try:
                await self.update_message()
            except Exception:
                self.embed.colour = discord.Colour.dark_red()
                await self.cancel("The battle timed out")
                return

    async def start(self):
        """
        Start the battle by sending the initial message and opening up the proposals.
        """
        self._generate_embed()
        self.message = await self.channel.send(
            content=f"Hey {self.battler2.user.mention}, {self.battler1.user.name} "
            "is proposing a battle with you!",
            embed=self.embed,
            view=self.current_view,
            allowed_mentions=discord.AllowedMentions(users=[self.battler2.user]),
        )
        self.task = self.bot.loop.create_task(self.update_message_loop())

    async def cancel(self, reason: str = "The battle has been cancelled."):
        """
        Cancel the battle immediately.
        """
        if self.task:
            self.task.cancel()

        self.current_view.stop()
        for item in self.current_view.children:
            item.disabled = True  # type: ignore

        self.embed.description = f"**{reason}**"
        self.embed.color = discord.Colour.red()
        if self.message:
            await self.message.edit(content=None, embed=self.embed, view=self.current_view)
        self.cog.remove_battle(self.channel.guild.id)

    async def commence_battle(self):
        """
        Commence the battle between the two battlers.
        """
        results = []
        if not self.battler1.proposal and not self.battler2.proposal:
            winner = None
        elif not self.battler1.proposal:
            winner = self.battler2.user
        elif not self.battler2.proposal:
            winner = self.battler1.user
        else:
            rounds = min(len(self.battler1.proposal), len(self.battler2.proposal))

            for i in range(rounds):
                ball1 = self.battler1.proposal[i]
                ball2 = self.battler2.proposal[i]

                result = self._battle_round(ball1, ball2)
                results.append(result)

            winner = self._determine_winner(results)

        await self._display_battle_results(results, winner)
        self.cog.remove_battle(self.channel.guild.id)

    def _battle_round(self, ball1, ball2):
        """
        Simulate a single round of battle between two balls.
        """
        ball1_hp = ball1.health_bonus
        ball2_hp = ball2.health_bonus

        while ball1_hp > 0 and ball2_hp > 0:
            ball2_hp -= ball1.attack_bonus
            if ball2_hp <= 0:
                return self.battler1.user

            ball1_hp -= ball2.attack_bonus
            if ball1_hp <= 0:
                return self.battler2.user

        return None

    def _determine_winner(self, results):
        """
        Determine the overall winner based on the results of each round.
        """
        battler1_wins = results.count(self.battler1.user)
        battler2_wins = results.count(self.battler2.user)

        if battler1_wins > battler2_wins:
            return self.battler1.user
        elif battler2_wins > battler1_wins:
            return self.battler2.user
        else:
            return None

    async def _display_battle_results(self, results, winner):
        """
        Display the results of the battle.
        """
        description = ""
        for i, result in enumerate(results):
            if result:
                description += f"Round {i + 1}: {result.display_name} wins!\n"
            else:
                description += f"Round {i + 1}: Draw!\n"

        if winner:
            description += f"\nOverall Winner: {winner.display_name}!"
        else:
            description += "\nThe battle ended in a draw!"

        self.embed.description = description
        self.embed.color = discord.Colour.green() if winner else discord.Colour.orange()
        await self.message.edit(embed=self.embed, view=None)


class BattleView(View):
    def __init__(self, battle: BattleMenu):
        super().__init__(timeout=60 * 30)
        self.battle = battle

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        try:
            self.battle.get_battler(interaction.user)
        except RuntimeError:
            await interaction.response.send_message(
                "You are not allowed to interact with this battle.", ephemeral=True
            )
            return False
        else:
            return True

    @discord.ui.button(label="Lock proposal", emoji="\N{LOCK}", style=discord.ButtonStyle.success)
    async def lock(self, interaction: discord.Interaction, button: Button):
        battler = self.battle.get_battler(interaction.user)
        if not battler:
            await interaction.response.send_message(
                "You are not part of this battle.", ephemeral=True
            )
            return
        if battler.locked:
            await interaction.response.send_message(
                "You have already locked your proposal!", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        battler.locked = True
        await self.battle.update_message()
        if self.battle.battler1.locked and self.battle.battler2.locked:
            await interaction.followup.send(
                "Both proposals have been locked. The battle will now commence.",
                ephemeral=True,
            )
            await self.battle.commence_battle()
        else:
            await interaction.followup.send(
                "Your proposal has been locked. "
                "You can wait for the other user to lock their proposal.",
                ephemeral=True,
            )

    @discord.ui.button(label="Cancel battle", emoji="\N{HEAVY MULTIPLICATION X}", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self.battle.cancel("The battle has been cancelled by a user.")
        await interaction.response.send_message("Battle has been cancelled.", ephemeral=True)