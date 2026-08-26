import os
import asyncio
import logging

from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Update


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("telegram-bot")


# ============================================================
# Environment
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured")


RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not RENDER_EXTERNAL_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL is not configured")


WEBHOOK_URL = RENDER_EXTERNAL_URL.rstrip("/") + "/webhook"


logger.info("BOT_TOKEN configured")
logger.info("WEBHOOK_URL: %s", WEBHOOK_URL)


# ============================================================
# Flask
# ============================================================

app = Flask(__name__)


# ============================================================
# Telegram
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# Event loop
# ============================================================

loop = asyncio.new_event_loop()


def run_loop():
    asyncio.set_event_loop(loop)
    logger.info("Async event loop started")
    loop.run_forever()


import threading

threading.Thread(
    target=run_loop,
    daemon=True,
    name="telegram-loop",
).start()


# ============================================================
# Handlers
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):

    logger.info(
        "START received from user=%s",
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "👋 سلام!\n\n"
        "✅ ربات آنلاین است.\n"
        "🚀 Webhook روی Render فعال است.\n\n"
        "برای تست /ping را بفرست."
    )


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):

    logger.info(
        "PING received from user=%s",
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "🏓 Pong!\n"
        "✅ اتصال Telegram → Render → Bot سالم است."
    )


@dp.message()
async def any_message_handler(message: types.Message):

    logger.info(
        "MESSAGE received: %s",
        message.text,
    )

    await message.answer(
        "📩 پیام دریافت شد."
    )


# ============================================================
# Telegram initialization
# ============================================================

async def initialize_telegram():

    logger.info("----------------------------------------")
    logger.info("Initializing Telegram...")

    me = await bot.get_me()

    logger.info(
        "Bot: @%s",
        me.username,
    )

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=False,
    )

    info = await bot.get_webhook_info()

    logger.info("----------------------------------------")
    logger.info("WEBHOOK CONFIGURED")
    logger.info("Telegram URL: %s", info.url)
    logger.info(
        "Pending updates: %s",
        info.pending_update_count,
    )

    if info.last_error_message:
        logger.error(
            "Telegram webhook error: %s",
            info.last_error_message,
        )
    else:
        logger.info(
            "Telegram webhook has no reported errors"
        )

    logger.info("----------------------------------------")


future = asyncio.run_coroutine_threadsafe(
    initialize_telegram(),
    loop,
)


# ============================================================
# Routes
# ============================================================

@app.route("/", methods=["GET", "HEAD"])
def home():

    return jsonify({
        "ok": True,
        "service": "telegram-bot",
        "status": "running",
    })


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "status": "healthy",
    })


@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        data = request.get_json(silent=True)

        if not data:
            logger.warning("Webhook received empty JSON")

            return jsonify({
                "ok": False,
                "error": "empty json",
            }), 400

        logger.info(
            "Webhook received update_id=%s",
            data.get("update_id"),
        )

        update = Update.model_validate(data)

        asyncio.run_coroutine_threadsafe(
            dp.feed_update(bot, update),
            loop,
        )

        return jsonify({
            "ok": True,
        }), 200

    except Exception as exc:

        logger.exception(
            "Webhook error"
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@app.route("/bot-info", methods=["GET"])
def bot_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_me(),
            loop,
        )

        me = future.result(timeout=15)

        return jsonify({
            "ok": True,
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        })

    except Exception as exc:

        logger.exception(
            "bot-info failed"
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@app.route("/webhook-info", methods=["GET"])
def webhook_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_webhook_info(),
            loop,
        )

        info = future.result(timeout=15)

        return jsonify({
            "ok": True,
            "url": info.url,
            "pending_update_count": info.pending_update_count,
            "last_error_message": info.last_error_message,
            "last_error_date": info.last_error_date,
        })

    except Exception as exc:

        logger.exception(
            "webhook-info failed"
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ============================================================
# Local
# ============================================================

if __name__ == "__main__":

    port = int(os.getenv("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )
