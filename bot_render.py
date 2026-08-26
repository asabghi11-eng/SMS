import os
import asyncio
import logging
import threading

from flask import Flask, request, jsonify

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Update


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")


# ------------------------------------------------------------
# ساخت URL به شکل امن
#
# WEBHOOK_URL اگر وجود داشته باشد:
#   https://example.onrender.com
#   https://example.onrender.com/webhook
#
# هر دو حالت را قبول می‌کنیم و فقط یک /webhook می‌گذاریم.
# ------------------------------------------------------------

render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
manual_url = os.getenv("WEBHOOK_URL", "").strip()

if manual_url:
    base_url = manual_url.rstrip("/")
else:
    base_url = render_url.rstrip("/")

if not base_url:
    service_name = os.getenv(
        "RENDER_SERVICE_NAME",
        "sms-4-mntp",
    )

    base_url = f"https://{service_name}.onrender.com"

# جلوگیری از /webhook/webhook
if base_url.endswith("/webhook"):
    WEBHOOK_URL = base_url
else:
    WEBHOOK_URL = f"{base_url}/webhook"


# ------------------------------------------------------------
# اختیاری: Secret برای webhook
# ------------------------------------------------------------

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()


logger.info("BOT_TOKEN is configured")
logger.info("WEBHOOK_URL: %s", WEBHOOK_URL)

if WEBHOOK_SECRET:
    logger.info("WEBHOOK_SECRET is enabled")
else:
    logger.info("WEBHOOK_SECRET is disabled")


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# TELEGRAM
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# ASYNCIO EVENT LOOP
# ============================================================

loop = asyncio.new_event_loop()


def async_worker():
    asyncio.set_event_loop(loop)

    logger.info("Async event loop started")

    try:
        loop.run_forever()
    except Exception:
        logger.exception("Async event loop crashed")


loop_thread = threading.Thread(
    target=async_worker,
    name="telegram-event-loop",
    daemon=True,
)

loop_thread.start()


# ============================================================
# TELEGRAM HANDLERS
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):

    user_id = (
        message.from_user.id
        if message.from_user
        else "unknown"
    )

    first_name = (
        message.from_user.first_name
        if message.from_user
        else "دوست"
    )

    logger.info(
        "START received from user=%s",
        user_id,
    )

    try:
        await message.answer(
            f"👋 سلام {first_name}!\n\n"
            "✅ ربات با موفقیت اجرا شده.\n"
            "✅ اتصال Telegram → Render برقرار است.\n\n"
            "برای تست بیشتر /ping را بفرست."
        )

        logger.info(
            "START response sent to user=%s",
            user_id,
        )

    except Exception:
        logger.exception(
            "Failed to send START response"
        )


@dp.message(Command("ping"))
async def ping_handler(message: types.Message):

    user_id = (
        message.from_user.id
        if message.from_user
        else "unknown"
    )

    logger.info(
        "PING received from user=%s",
        user_id,
    )

    try:
        await message.answer(
            "🏓 Pong!\n\n"
            "✅ Bot is alive\n"
            "✅ Telegram connected\n"
            "✅ Render connected"
        )

        logger.info(
            "PING response sent to user=%s",
            user_id,
        )

    except Exception:
        logger.exception(
            "Failed to send PING response"
        )


# ============================================================
# PROCESS UPDATE
# ============================================================

async def process_update(update: Update):

    logger.info(
        "Processing Telegram update id=%s",
        update.update_id,
    )

    try:

        await dp.feed_update(
            bot,
            update,
        )

        logger.info(
            "Telegram update processed id=%s",
            update.update_id,
        )

    except Exception:
        logger.exception(
            "Error processing Telegram update id=%s",
            update.update_id,
        )


# ============================================================
# WEBHOOK SETUP
# ============================================================

async def setup_webhook():

    logger.info("----------------------------------------")
    logger.info("Setting Telegram webhook")
    logger.info("Webhook URL: %s", WEBHOOK_URL)

    try:

        # ----------------------------------------------------
        # تست BOT TOKEN
        # ----------------------------------------------------

        me = await bot.get_me()

        logger.info(
            "Telegram bot: @%s",
            me.username,
        )

        logger.info(
            "Telegram bot ID: %s",
            me.id,
        )

        # ----------------------------------------------------
        # تنظیم webhook
        # ----------------------------------------------------

        kwargs = {
            "url": WEBHOOK_URL,
            "allowed_updates": dp.resolve_used_update_types(),
            "drop_pending_updates": False,
        }

        if WEBHOOK_SECRET:
            kwargs["secret_token"] = WEBHOOK_SECRET

        await bot.set_webhook(**kwargs)

        # ----------------------------------------------------
        # بررسی واقعی webhook
        # ----------------------------------------------------

        info = await bot.get_webhook_info()

        logger.info("----------------------------------------")
        logger.info("WEBHOOK CONFIGURED")
        logger.info("Telegram URL: %s", info.url)
        logger.info(
            "Pending updates: %s",
            info.pending_update_count,
        )

        if info.last_error_date:
            logger.error(
                "Telegram last error date: %s",
                info.last_error_date,
            )

        if info.last_error_message:
            logger.error(
                "Telegram last error: %s",
                info.last_error_message,
            )
        else:
            logger.info(
                "Telegram webhook has no reported errors"
            )

        logger.info("----------------------------------------")

    except Exception:
        logger.exception(
            "FAILED TO CONFIGURE TELEGRAM WEBHOOK"
        )


# ============================================================
# START WEBHOOK SETUP
# ============================================================

setup_future = asyncio.run_coroutine_threadsafe(
    setup_webhook(),
    loop,
)


def setup_done_callback(future):

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
    setup_done_callback
)


# ============================================================
# ROOT
# ============================================================

@app.route("/", methods=["GET", "HEAD"])
def home():

    return jsonify({
        "ok": True,
        "service": "telegram-bot",
        "status": "running",
    }), 200


# ============================================================
# HEALTH
# ============================================================

@app.route("/health", methods=["GET", "HEAD"])
def health():

    return jsonify({
        "ok": True,
        "status": "healthy",
    }), 200


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.route("/webhook", methods=["POST"])
def telegram_webhook():

    # --------------------------------------------------------
    # Secret verification
    # --------------------------------------------------------

    if WEBHOOK_SECRET:

        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            "",
        )

        if received_secret != WEBHOOK_SECRET:

            logger.warning(
                "Rejected webhook: invalid secret"
            )

            return jsonify({
                "ok": False,
                "error": "Unauthorized",
            }), 401

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    data = request.get_json(silent=True)

    if not isinstance(data, dict):

        logger.warning(
            "Webhook received invalid JSON"
        )

        return jsonify({
            "ok": False,
            "error": "Invalid JSON",
        }), 400

    # --------------------------------------------------------
    # Convert Telegram JSON → Update
    # --------------------------------------------------------

    try:

        update = Update.model_validate(data)

    except Exception:

        logger.exception(
            "Could not parse Telegram update"
        )

        return jsonify({
            "ok": False,
            "error": "Invalid Telegram update",
        }), 400

    logger.info(
        "RECEIVED TELEGRAM UPDATE id=%s",
        update.update_id,
    )

    # --------------------------------------------------------
    # Send update to asyncio loop
    # --------------------------------------------------------

    try:

        future = asyncio.run_coroutine_threadsafe(
            process_update(update),
            loop,
        )

        # ----------------------------------------------------
        # فقط callback ثبت می‌کنیم.
        # Flask منتظر Telegram نمی‌ماند.
        # ----------------------------------------------------

        def update_done(done_future):

            try:
                done_future.result()

            except Exception:
                logger.exception(
                    "Telegram update task failed"
                )

        future.add_done_callback(
            update_done
        )

    except Exception:

        logger.exception(
            "Could not schedule Telegram update"
        )

        return jsonify({
            "ok": False,
            "error": "Could not schedule update",
        }), 500

    # --------------------------------------------------------
    # پاسخ سریع به Telegram
    # --------------------------------------------------------

    return jsonify({
        "ok": True,
    }), 200


# ============================================================
# WEBHOOK INFO
# ============================================================

@app.route("/webhook-info", methods=["GET"])
def webhook_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_webhook_info(),
            loop,
        )

        info = future.result(
            timeout=15,
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
            ),
            "max_connections": (
                info.max_connections
            ),
        }), 200

    except Exception as e:

        logger.exception(
            "Could not get webhook information"
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


# ============================================================
# BOT INFO
# ============================================================

@app.route("/bot-info", methods=["GET"])
def bot_info():

    try:

        future = asyncio.run_coroutine_threadsafe(
            bot.get_me(),
            loop,
        )

        me = future.result(
            timeout=15,
        )

        return jsonify({
            "ok": True,
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }), 200

    except Exception as e:

        logger.exception(
            "Could not get bot information"
        )

        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500


# ============================================================
# LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    logger.info(
        "Starting local Flask server"
    )

    logger.info(
        "Port: %s",
        port,
    )

    logger.info(
        "Webhook URL: %s",
        WEBHOOK_URL,
    )

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
    )
