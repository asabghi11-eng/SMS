import os
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Update


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")

BASE_URL = (
    os.getenv("WEBHOOK_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "https://sms-4-mntp.onrender.com"
).rstrip("/")

WEBHOOK_URL = BASE_URL + "/webhook"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "👋 سلام!\n\n"
        "✅ ربات فعال است.\n"
        "برای تست /ping را بفرست."
    )


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):
    await message.answer("🏓 Pong!\n✅ ربات فعال است.")


async def webhook(request: web.Request):
    try:
        data = await request.json()

        update = Update.model_validate(data)

        logger.info(
            "Telegram update received: %s",
            update.update_id,
        )

        await dp.feed_update(bot, update)

        return web.json_response({"ok": True})

    except Exception:
        logger.exception("Webhook error")
        return web.json_response(
            {"ok": False},
            status=500,
        )


async def home(request):
    return web.Response(
        text="Telegram Bot is running!",
        status=200,
    )


async def health(request):
    return web.Response(
        text="OK",
        status=200,
    )


async def on_startup(app):
    logger.info("Initializing Telegram...")

    me = await bot.get_me()

    logger.info(
        "Bot: @%s",
        me.username,
    )

    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=False,
    )

    info = await bot.get_webhook_info()

    logger.info("========================================")
    logger.info("WEBHOOK CONFIGURED")
    logger.info("URL: %s", info.url)
    logger.info(
        "Pending: %s",
        info.pending_update_count,
    )
    logger.info(
        "Last error: %s",
        info.last_error_message,
    )
    logger.info("========================================")


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


app = web.Application()

app.router.add_get("/", home)
app.router.add_head("/", home)

app.router.add_get("/health", health)
app.router.add_head("/health", health)

app.router.add_post("/webhook", webhook)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))

    web.run_app(
        app,
        host="0.0.0.0",
        port=port,
    )
