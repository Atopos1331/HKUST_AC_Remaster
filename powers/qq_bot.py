import asyncio
import base64
import threading
from pathlib import Path

import botpy
from botpy.api import Route

from powers.message_handler import BotMessageHandler, BotResponse
from powers.utils.config import Bot
from powers.utils.logger import log, setup_botpy_logging


class QQBot:
    """Manage the QQ bot lifecycle in a background daemon thread."""

    def __init__(self) -> None:
        setup_botpy_logging()
        self.client = None
        self.running = False
        self.bot_thread = None
        self.message_handler = BotMessageHandler()

    def start(self) -> None:
        if self.running:
            log.warning("QQ bot is already running.")
            return
        if not Bot.APPID or not Bot.SECRET:
            log.warning("QQ bot credentials are empty; QQ bot will not start.")
            return
        try:
            self.running = True
            self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
            self.bot_thread.start()
            log.info("QQ bot thread started.")
        except Exception as exc:
            log.error(f"Failed to start QQ bot: {exc}")
            self.running = False

    def stop(self) -> None:
        if not self.running:
            return
        try:
            self.running = False
            log.info("Stopping QQ bot...")
            if self.bot_thread and self.bot_thread.is_alive():
                self.bot_thread.join(timeout=5)
            log.info("QQ bot stopped.")
        except Exception as exc:
            log.error(f"Failed to stop QQ bot: {exc}")

    def _run_bot(self) -> None:
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            class MyClient(botpy.Client):
                def __init__(self, bot_instance, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.bot_instance = bot_instance

                async def on_ready(self):
                    log.info("QQ bot connected and ready.")

                async def on_c2c_message_create(self, message):
                    try:
                        response = self.bot_instance.message_handler.deal_message(message.content, source="qq-dm")
                        log.detail(f"QQ DM received: {message.content}")
                        await self._send_c2c_response(message, response)
                    except Exception as exc:
                        log.error(f"Failed to handle QQ DM: {exc}")

                async def on_group_at_message_create(self, message):
                    try:
                        response = self.bot_instance.message_handler.deal_message(message.content.strip(), source="qq-group")
                        log.detail(f"QQ group message received: {message.content.strip()}")
                        await self._send_group_response(message, response)
                    except Exception as exc:
                        log.error(f"Failed to handle QQ group message: {exc}")

                async def _send_c2c_response(self, message, response: BotResponse) -> None:
                    if response.image_path is None:
                        await message._api.post_c2c_message(
                            openid=message.author.user_openid,
                            msg_type=0,
                            msg_id=message.id,
                            content=response.text,
                        )
                        return
                    media = await self._upload_local_image(message._api, message.author.user_openid, response.image_path, is_group=False)
                    await message._api.post_c2c_message(
                        openid=message.author.user_openid,
                        msg_type=7,
                        msg_id=message.id,
                        content=response.text,
                        media=media,
                    )

                async def _send_group_response(self, message, response: BotResponse) -> None:
                    if response.image_path is None:
                        await message._api.post_group_message(
                            group_openid=message.group_openid,
                            msg_type=0,
                            msg_id=message.id,
                            content=f"\n{response.text}",
                        )
                        return
                    media = await self._upload_local_image(message._api, message.group_openid, response.image_path, is_group=True)
                    await message._api.post_group_message(
                        group_openid=message.group_openid,
                        msg_type=7,
                        msg_id=message.id,
                        content=response.text,
                        media=media,
                    )

                async def _upload_local_image(self, api, target: str, figure_path: Path, is_group: bool):
                    file_data = base64.b64encode(figure_path.read_bytes()).decode("ascii")
                    payload = {"file_type": 1, "file_data": file_data, "srv_send_msg": False}
                    route = (
                        Route("POST", "/v2/groups/{group_openid}/files", group_openid=target)
                        if is_group
                        else Route("POST", "/v2/users/{openid}/files", openid=target)
                    )
                    return await api._http.request(route, json=payload)

            intents = botpy.Intents(public_messages=True, direct_message=True)
            self.client = MyClient(self, intents=intents, ext_handlers=False)
            loop.run_until_complete(self.client.start(appid=Bot.APPID, secret=Bot.SECRET))
        except Exception as exc:
            log.error(f"QQ bot runtime error: {exc}")
        finally:
            self.running = False
            try:
                (loop or asyncio.get_event_loop()).close()
            except Exception:
                pass


ACBot = QQBot
