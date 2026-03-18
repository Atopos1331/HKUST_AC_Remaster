import asyncio
import threading
from asyncio import CancelledError as AsyncioCancelledError
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import discord
from discord import app_commands

from powers.command_registry import CommandSpec, iter_command_specs
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
                    for spec in iter_command_specs():
                        callback = self._build_slash_callback(spec)
                        command = app_commands.Command(
                            name=spec.name,
                            description=spec.description,
                            callback=callback,
                        )
                        self.tree.add_command(command, override=True)

                def _build_slash_callback(self, spec: CommandSpec):
                    parameters = ["interaction: discord.Interaction"]
                    body_lines = ["args = {}"]
                    for option in spec.options:
                        annotation = "app_commands.Choice[str]" if option.choices else option.value_type.__name__
                        default = ""
                        if not option.required:
                            default = f" = {option.default!r}"
                        parameters.append(f"{option.name}: {annotation}{default}")
                        value_expr = f"{option.name}.value" if option.choices else option.name
                        body_lines.append(f"args[{option.name!r}] = {value_expr}")
                    body_lines.append("await self._handle_slash_command(interaction, spec.build_message(args))")

                    source = "async def _callback(" + ", ".join(parameters) + "):\n"
                    for line in body_lines:
                        source += f"    {line}\n"

                    namespace = {
                        "app_commands": app_commands,
                        "discord": discord,
                        "self": self,
                        "spec": spec,
                    }
                    exec(source, namespace)
                    callback = namespace["_callback"]
                    callback.__name__ = f"command_{spec.name}"
                    callback.__qualname__ = callback.__name__

                    if spec.options:
                        callback = app_commands.describe(
                            **{option.name: option.description for option in spec.options}
                        )(callback)
                    for option in spec.options:
                        if option.choices:
                            callback = app_commands.choices(
                                **{
                                    option.name: [
                                        app_commands.Choice(name=choice, value=choice)
                                        for choice in option.choices
                                    ]
                                }
                            )(callback)
                    return callback

                async def _handle_slash_command(self, interaction: discord.Interaction, command_text: str) -> None:
                    if not interaction.response.is_done():
                        await interaction.response.defer(thinking=True)
                    try:
                        response = await asyncio.to_thread(
                            self.bot_instance.message_handler.deal_message,
                            command_text,
                            "discord-slash",
                        )
                    except Exception as exc:
                        log.error(f"Failed to handle Discord slash command {command_text}: {type(exc).__name__}: {exc}")
                        response = BotResponse(f"Failed to process command: {exc}")
                    await self._send_response_to_followup(interaction, response)

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
