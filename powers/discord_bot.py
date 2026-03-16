import asyncio
import threading
from asyncio import CancelledError as AsyncioCancelledError
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import discord
from discord import app_commands

from powers.message_handler import BotMessageHandler, BotResponse
from powers.utils.config import Bot
from powers.utils.logger import log


class DiscordBot:
    """Manage the Discord bot lifecycle in a background daemon thread."""

    def __init__(self) -> None:
        self.client = None
        self.loop = None
        self.running = False
        self.bot_thread = None
        self.last_error = None
        self.message_handler = BotMessageHandler()

    def start(self) -> None:
        if self.running:
            log.warning("Discord bot is already running.")
            return
        if not getattr(Bot, "DISCORD_TOKEN", ""):
            log.warning("Discord token is empty; Discord bot will not start.")
            return
        try:
            self.running = True
            self.last_error = None
            self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
            self.bot_thread.start()
            log.info("Discord bot thread started.")
        except Exception as exc:
            log.error(f"Failed to start Discord bot: {exc}")
            self.running = False

    def stop(self) -> None:
        if self.client is None and (self.bot_thread is None or not self.bot_thread.is_alive()):
            return
        try:
            self.running = False
            log.info("Stopping Discord bot...")
            if self.client is not None and self.loop is not None and self.loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)
                future.result(timeout=10)
            if self.bot_thread and self.bot_thread.is_alive():
                self.bot_thread.join(timeout=10)
            if self.bot_thread and self.bot_thread.is_alive():
                log.warning("Discord bot thread did not exit within 10 seconds.")
            log.info("Discord bot stopped.")
        except (AsyncioCancelledError, FutureCancelledError):
            log.info("Discord bot shutdown was already in progress.")
        except FutureTimeoutError:
            log.error("Failed to stop Discord bot: closing the Discord client timed out.")
        except Exception as exc:
            log.error(f"Failed to stop Discord bot: {type(exc).__name__}: {exc!r}")

    def _run_bot(self) -> None:
        loop = None
        try:
            loop = asyncio.new_event_loop()
            self.loop = loop
            asyncio.set_event_loop(loop)

            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            intents.messages = True
            intents.dm_messages = True

            class DiscordClient(discord.Client):
                def __init__(self, bot_instance, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.bot_instance = bot_instance
                    self.tree = app_commands.CommandTree(self)
                    self._commands_synced = False
                    self._register_commands()

                async def on_ready(self):
                    if not self._commands_synced:
                        synced = await self.tree.sync()
                        self._commands_synced = True
                        log.info(f"Discord slash commands synced: {len(synced)}")
                    log.info(f"Discord bot connected as {self.user}.")

                async def on_message(self, message: discord.Message):
                    if message.author.bot:
                        return
                    text = message.content.strip()
                    if not text.startswith("/"):
                        return
                    try:
                        response = self.bot_instance.message_handler.deal_message(text, source="discord-message")
                        log.detail(f"Discord message received: {text}")
                        await self._send_response_to_channel(message.channel, response)
                    except Exception as exc:
                        log.error(f"Failed to handle Discord message: {exc}")

                def _register_commands(self) -> None:
                    specs = {spec["name"]: spec for spec in self.bot_instance.message_handler.get_discord_command_specs()}

                    @self.tree.command(name="state", description=specs["state"]["description"])
                    async def state(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/state", source="discord-slash"))

                    @self.tree.command(name="settemp", description=specs["settemp"]["description"])
                    @app_commands.describe(temperature=specs["settemp"]["options"]["temperature"])
                    async def settemp(interaction: discord.Interaction, temperature: float) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/settemp {temperature}", source="discord-slash"))

                    @self.tree.command(name="setbasis", description=specs["setbasis"]["description"])
                    @app_commands.describe(basis=specs["setbasis"]["options"]["basis"])
                    @app_commands.choices(
                        basis=[
                            app_commands.Choice(name="temperature", value="temperature"),
                            app_commands.Choice(name="heatindex", value="heatindex"),
                        ]
                    )
                    async def setbasis(interaction: discord.Interaction, basis: app_commands.Choice[str]) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/setbasis {basis.value}", source="discord-slash"))

                    @self.tree.command(name="settime", description=specs["settime"]["description"])
                    @app_commands.describe(
                        on_seconds=specs["settime"]["options"]["on_seconds"],
                        off_seconds=specs["settime"]["options"]["off_seconds"],
                    )
                    async def settime(interaction: discord.Interaction, on_seconds: int, off_seconds: int) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/settime {on_seconds} {off_seconds}", source="discord-slash"))

                    @self.tree.command(name="setmode", description=specs["setmode"]["description"])
                    @app_commands.describe(mode=specs["setmode"]["options"]["mode"])
                    @app_commands.choices(
                        mode=[
                            app_commands.Choice(name="temperature", value="temperature"),
                            app_commands.Choice(name="scheduler", value="scheduler"),
                        ]
                    )
                    async def setmode(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/setmode {mode.value}", source="discord-slash"))

                    @self.tree.command(name="timer", description=specs["timer"]["description"])
                    async def timer(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/timer", source="discord-slash"))

                    @self.tree.command(name="scheduler", description=specs["scheduler"]["description"])
                    async def scheduler(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/scheduler", source="discord-slash"))

                    @self.tree.command(name="lock", description=specs["lock"]["description"])
                    async def lock(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/lock", source="discord-slash"))

                    @self.tree.command(name="setlock", description=specs["setlock"]["description"])
                    @app_commands.describe(
                        state=specs["setlock"]["options"]["state"],
                        duration=specs["setlock"]["options"]["duration"],
                    )
                    @app_commands.choices(
                        state=[
                            app_commands.Choice(name="ON", value="ON"),
                            app_commands.Choice(name="OFF", value="OFF"),
                        ]
                    )
                    async def setlock(interaction: discord.Interaction, state: app_commands.Choice[str], duration: int) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/lock {state.value} {duration}", source="discord-slash"))

                    @self.tree.command(name="clearlock", description=specs["clearlock"]["description"])
                    async def clearlock(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/lock clear", source="discord-slash"))

                    @self.tree.command(name="log", description=specs["log"]["description"])
                    async def botlog(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/log", source="discord-slash"))

                    @self.tree.command(name="switchon", description=specs["switchon"]["description"])
                    async def switchon(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/switchOn", source="discord-slash"))

                    @self.tree.command(name="switchoff", description=specs["switchoff"]["description"])
                    async def switchoff(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/switchOff", source="discord-slash"))

                    @self.tree.command(name="stats", description=specs["stats"]["description"])
                    @app_commands.describe(range_text=specs["stats"]["options"]["range_text"])
                    async def stats(interaction: discord.Interaction, range_text: str = "24h") -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/stats {range_text}", source="discord-slash"))

                    @self.tree.command(name="plot", description=specs["plot"]["description"])
                    @app_commands.describe(range_text=specs["plot"]["options"]["range_text"])
                    async def plot(interaction: discord.Interaction, range_text: str) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message(f"/plot {range_text}", source="discord-slash"))

                    @self.tree.command(name="help", description=specs["help"]["description"])
                    async def help_command(interaction: discord.Interaction) -> None:
                        await self._respond(interaction, self.bot_instance.message_handler.deal_message("/help", source="discord-slash"))

                async def _respond(self, interaction: discord.Interaction, response: BotResponse) -> None:
                    if interaction.response.is_done():
                        await self._send_response_to_followup(interaction, response)
                        return
                    if response.image_path is None:
                        await interaction.response.send_message(response.text)
                        return
                    await interaction.response.send_message(
                        content=response.text,
                        file=discord.File(str(response.image_path), filename=Path(response.image_path).name),
                    )

                async def _send_response_to_followup(self, interaction: discord.Interaction, response: BotResponse) -> None:
                    if response.image_path is None:
                        await interaction.followup.send(response.text)
                        return
                    await interaction.followup.send(
                        content=response.text,
                        file=discord.File(str(response.image_path), filename=Path(response.image_path).name),
                    )

                async def _send_response_to_channel(self, channel, response: BotResponse) -> None:
                    if response.image_path is None:
                        await channel.send(response.text)
                        return
                    await channel.send(
                        content=response.text,
                        file=discord.File(str(response.image_path), filename=Path(response.image_path).name),
                    )

            self.client = DiscordClient(self, intents=intents)
            loop.run_until_complete(self.client.start(Bot.DISCORD_TOKEN))
        except Exception as exc:
            self.last_error = exc
            log.error(f"Discord bot runtime error: {exc}")
        finally:
            self.running = False
            try:
                current_loop = loop or self.loop
                if current_loop is not None and not current_loop.is_closed():
                    pending = [task for task in asyncio.all_tasks(current_loop) if not task.done()]
                    for task in pending:
                        task.cancel()
                    if pending:
                        current_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    current_loop.run_until_complete(current_loop.shutdown_asyncgens())
                    current_loop.close()
            except Exception:
                pass
            finally:
                self.client = None
                self.loop = None


if __name__ == "__main__":
    import time

    bot = DiscordBot()
    bot.start()
    try:
        while True:
            if bot.bot_thread is not None and not bot.bot_thread.is_alive():
                if bot.last_error is not None:
                    log.error(f"Discord bot exited with error: {type(bot.last_error).__name__}: {bot.last_error!r}")
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        bot.stop()
