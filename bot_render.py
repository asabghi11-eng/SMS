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
# Environment
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set"
    )


# Render خودش این مقدار را در اختیار سرویس قرار می‌دهد.
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# اگر WEBHOOK_URL را دستی در Render تنظیم کرده باشی، آن را هم قبول می‌کنیم.
MANUAL_WEBHOOK_URL = os.getenv("WEBHOOK_URL")


if MANUAL_WEBHOOK_URL:
    WEBHOOK_URL = MANUAL_WEBHOOK_URL.rstrip("/") + "/webhook"

elif RENDER_EXTERNAL_URL:
    WEBHOOK_URL = (
        RENDER_EXTERNAL_URL.rstrip("/")
        + "/webhook"
    )

else:
    service_name = os.getenv(
        "RENDER_SERVICE_NAME",
        "sms-4-mntp"
    )

    WEBHOOK_URL = (
        f"https://{service_name}.onrender.com/webhook"
    )


logger.info("BOT_TOKEN is configured")
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
# Dedicated asyncio event loop
# ============================================================

loop = asyncio.new_event_loop()


def start_async_loop():
    """
    اجرای دائمی event loop در یک thread جدا.
    """

    asyncio.set_event_loop(loop)

    logger.info("Async event loop started")

    try:
        loop.run_forever()

    except Exception:
        logger.exception(
            "Async event loop crashed"
        )


loop_thread = threading.Thread(
    target=start_async_loop,
    name="telegram-async-loop",
    daemon=True
)

loop_thread.start()


# ============================================================
# Telegram Handlers
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):

    try:

        first_name = (
            message.from_user.first_name
            if message.from_user
            else "دوست"
        )

        await message.answer(
            f"👋 سلام {first_name}!\n\n"
            "✅ ربات با موفقیت روی Render اجرا شده است.\n\n"
            "برای تست اتصال، /ping را ارسال کنید."
        )

        logger.info(
            "Processed /start from user %s",
            message.from_user.id if message.from_user else "unknown"
        )

    except Exception:
        logger.exception(
            "Error in start handler"
        )


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):

    try:

        await message.answer(
            "🏓 Pong!\n"
            "✅ ربات فعال است."
        )

        logger.info(
            "Processed /ping from user %s",
            message.from_user.id if message.from_user else "unknown"
        )

    except Exception:
        logger.exception(
            "Error in ping handler"
        )


# ============================================================
# Process Telegram Update
# ============================================================

async def process_update(update: Update):
    """
    پردازش Update در event loop اصلی asyncio.
    """

    try:

        logger.info(
            "Processing Telegram update: %s",
            update.update_id
        )

        await dp.feed_update(
            bot,
            update
        )

        logger.info(
            "Telegram update processed: %s",
            update.update_id
        )

    except Exception:
        logger.exception(
            "Error while processing Telegram update"
        )


# ============================================================
# Webhook Setup
# ============================================================

async def setup_webhook():

    try:

        logger.info(
            "Setting Telegram webhook..."
        )

        logger.info(
            "Webhook URL: %s",
            WEBHOOK_URL
        )

        # تست Token
        me = await bot.get_me()

        logger.info(
            "Telegram bot: @%s",
            me.username
        )

        # تنظیم webhook
        await bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False
        )

        # بررسی webhook
        webhook_info = await bot.get_webhook_info()

        logger.info(
            "Webhook successfully configured"
        )

        logger.info(
            "Telegram webhook URL: %s",
            webhook_info.url
        )

        logger.info(
            "Pending updates: %s",
            webhook_info.pending_update_count
        )

        if webhook_info.last_error_message:

            logger.warning(
                "Telegram webhook error: %s",
                webhook_info.last_error_message
            )

        else:

            logger.info(
                "Telegram webhook has no reported errors"
            )

    except Exception:

        logger.exception(
            "Failed to configure Telegram webhook"
        )


# ============================================================
# Start webhook setup
# ============================================================

setup_future = asyncio.run_coroutine_threadsafe(
    setup_webhook(),
    loop
)


def log_setup_result(future):

    try:

        future.result()

        logger.info(
            "Webhook setup task completed"
        )

    except Exception:

        logger.exception(
            "Webhook setup task failed"
        )


setup_future.add_done_callback(
    log_setup_result
)


# ============================================================
# Flask Routes
# ============================================================

@app.route("/", methods=["GET", "HEAD"])
def home():

    return (
        "Telegram Bot is running!",
        200
    )


@app.route("/health", methods=["GET", "HEAD"])
def health():

    return (
        "OK",
        200
    )


# ============================================================
# Telegram Webhook
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        # دریافت JSON
        data = request.get_json(
            silent=True
        )

        if not data:

            logger.warning(
                "Received empty webhook request"
            )

            return jsonify({
                "ok": False,
                "error": "Empty JSON"
            }), 400


        # تبدیل JSON به Telegram Update
        update = Update.model_validate(
            data
        )


        logger.info(
            "Received Telegram update: %s",
            update.update_id
        )


        # ----------------------------------------------------
        # مهم:
        #
        # اینجا دیگر future.result() نداریم.
        #
        # Flask نباید منتظر پاسخ Telegram بماند.
        # ----------------------------------------------------

        future = asyncio.run_coroutine_threadsafe(
            process_update(update),
            loop
        )


        # اگر پردازش async خطا بدهد، در لاگ ثبت می‌شود.
        def update_done_callback(done_future):

            try:

                done_future.result()

            except Exception:

                logger.exception(
                    "Telegram update task failed"
                )


        future.add_done_callback(
            update_done_callback
        )


        # Telegram باید سریع 200 دریافت کند.
        return jsonify({
            "ok": True
        }), 200


    except Exception as e:

        logger.exception(
            "Webhook parsing/processing error"
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============================================================
# Webhook Information
# ============================================================

@app.route("/webhook-info", methods=["GET"])
def webhook_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_webhook_info(),
            loop
        )

        info = future.result(
            timeout=15
        )

        return jsonify({
            "ok": True,
            "url": info.url,
            "pending_update_count": (
                info.pending_update_count
            ),
            "last_error_date": (
                info.last_error_date
            ),
            "last_error_message": (
                info.last_error_message
            )
        }), 200


    except Exception as e:

        logger.exception(
            "Could not get webhook information"
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============================================================
# Telegram Info
# ============================================================

@app.route("/bot-info", methods=["GET"])
def bot_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_me(),
            loop
        )

        me = future.result(
            timeout=15
        )

        return jsonify({
            "ok": True,
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name
        }), 200


    except Exception as e:

        logger.exception(
            "Could not get bot information"
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

        if loop.is_running():

            future = asyncio.run_coroutine_threadsafe(
                bot.session.close(),
                loop
            )

            future.result(
                timeout=10
            )

            loop.call_soon_threadsafe(
                loop.stop
            )

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
        port=port,
        threaded=True
    )
