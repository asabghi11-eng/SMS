import os
import asyncio
import logging
import threading

from flask import Flask, request, jsonify

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Update


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
BOT_TOKEN = os.getenv("8586016384:AAHsfIE6JdmzBpp650lbw_9w25FBt8Tfbdg")
WEBHOOK_URL = os.getenv("https://sms-4-mntp.onrender.com/webhook")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        WEBHOOK_URL = f"{render_url.rstrip('/')}/webhook"
    else:
        service_name = os.getenv(
            "RENDER_SERVICE_NAME",
            "sms-bomber-bot-dsxz"
        )
        WEBHOOK_URL = f"https://{service_name}.onrender.com/webhook"
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not WEBHOOK_URL:
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        WEBHOOK_URL = f"{render_url.rstrip('/')}/webhook"
    else:
        service_name = os.getenv(
            "RENDER_SERVICE_NAME",
            "sms-bomber-bot-dsxz"
        )
        WEBHOOK_URL = f"https://{service_name}.onrender.com/webhook"


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
# Dedicated asyncio event loop
# ============================================================

loop = asyncio.new_event_loop()


def start_loop():
    asyncio.set_event_loop(loop)

    logger.info("Async event loop started")

    loop.run_forever()


loop_thread = threading.Thread(
    target=start_loop,
    daemon=True
)

loop_thread.start()


# ============================================================
# Telegram Handlers
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    first_name = message.from_user.first_name or "دوست"

    await message.answer(
        f"👋 سلام {first_name}!\n\n"
        "✅ ربات با موفقیت روی Render اجرا شده است.\n\n"
        "برای تست اتصال، /ping را ارسال کنید."
    )


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):
    await message.answer(
        "🏓 Pong!\n"
        "✅ ربات فعال است."
    )


# ============================================================
# Async startup
# ============================================================

async def setup_webhook():
    try:
        logger.info("Setting Telegram webhook...")
        logger.info("Webhook URL: %s", WEBHOOK_URL)

        me = await bot.get_me()

        logger.info(
            "Telegram bot: @%s",
            me.username
        )

        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=dp.resolve_used_update_types()
        )

        webhook_info = await bot.get_webhook_info()

        logger.info(
            "Webhook successfully configured"
        )

        logger.info(
            "Telegram webhook URL: %s",
            webhook_info.url
        )

        if webhook_info.last_error_message:
            logger.warning(
                "Telegram webhook error: %s",
                webhook_info.last_error_message
            )

    except Exception:
        logger.exception(
            "Failed to configure Telegram webhook"
        )


# ============================================================
# Run setup after Flask/Gunicorn import
# ============================================================

setup_future = asyncio.run_coroutine_threadsafe(
    setup_webhook(),
    loop
)


# ============================================================
# Flask Routes
# ============================================================

@app.route("/", methods=["GET", "HEAD"])
def home():
    return "Telegram Bot is running!", 200


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/webhook", methods=["POST"])
def webhook():

    try:
        data = request.get_json(silent=True)

        if not data:
            logger.warning("Received empty webhook request")
            return jsonify({
                "ok": False,
                "error": "Empty JSON"
            }), 400

        update = Update.model_validate(data)

        future = asyncio.run_coroutine_threadsafe(
            dp.feed_update(
                bot,
                update
            ),
            loop
        )

        # Wait until aiogram processes the update.
        future.result(timeout=30)

        return jsonify({
            "ok": True
        }), 200

    except Exception as e:

        logger.exception(
            "Webhook processing error"
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============================================================
# Optional webhook information
# ============================================================

@app.route("/webhook-info", methods=["GET"])
def webhook_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_webhook_info(),
            loop
        )

        info = future.result(timeout=15)

        return jsonify({
            "url": info.url,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message
        })

    except Exception as e:

        logger.exception(
            "Could not get webhook information"
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============================================================
# Cleanup
# ============================================================

def cleanup():

    try:
        future = asyncio.run_coroutine_threadsafe(
            bot.session.close(),
            loop
        )

        future.result(timeout=10)

    except Exception:
        logger.exception(
            "Error while closing Telegram session"
        )


# ============================================================
# Local execution
# ============================================================

if __name__ == "__main__":

    logger.info(
        "Starting Flask development server..."
    )

    logger.info(
        "Webhook URL: %s",
        WEBHOOK_URL
    )

    port = int(
        os.getenv("PORT", "10000")
    )

    app.run(
        host="0.0.0.0",
        port=port
    )

