"""
بوت تيليجرام لتحميل مقاطع تيك توك (بدون علامة مائية) ويوتيوب.

الفكرة:
- المستخدم يرسل رابط تيك توك أو يوتيوب للبوت.
- البوت يستخدم مكتبة yt-dlp لتحميل الفيديو (النسخة الأصلية بدون شعار تيك توك).
- البوت يرسل الفيديو للمستخدم مباشرة داخل تيليجرام.

قبل التشغيل:
1. ثبّت المتطلبات:
   pip install -r requirements.txt
2. تأكد إن ffmpeg مثبت على جهازك (مطلوب لدمج الصوت والفيديو أحيانًا).
   - ويندوز: حمّل من https://ffmpeg.org وأضفه للـ PATH
   - لينكس: sudo apt install ffmpeg
   - ماك: brew install ffmpeg
3. احصل على توكن البوت من @BotFather في تيليجرام.
4. ضع التوكن في متغير البيئة BOT_TOKEN أو عدّله مباشرة بالأسفل.
5. شغّل الملف: python bot.py
"""

import os
import re
import logging
import tempfile
import shutil

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------

# ضع التوكن هنا مباشرة أو استخدم متغير بيئة BOT_TOKEN (يفضل الأخير للأمان)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# الـ Chat ID الخاص بمالك البوت، تستخدم لتوصيل رسائل الدعم الفني إليه مباشرة
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "8675217264")

# الحد الأقصى لحجم الملف الذي يسمح تيليجرام برفعه عبر البوت (50 ميجا تقريبًا للبوتات العادية)
MAX_FILE_SIZE_MB = 50

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# نتتبع فيها المستخدمين اللي ضغطوا /support وننتظر رسالتهم التالية
users_awaiting_support = set()

TIKTOK_URL_REGEX = re.compile(
    r"(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/\S+", re.IGNORECASE
)

YOUTUBE_URL_REGEX = re.compile(
    r"(https?://)?(www\.|m\.)?(youtube\.com/\S+|youtu\.be/\S+)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# دوال المساعدة
# ---------------------------------------------------------------------------

def extract_supported_url(text: str) -> tuple[str, str] | tuple[None, None]:
    """
    يستخرج رابط تيك توك أو يوتيوب من نص الرسالة إن وُجد.
    يرجع (الرابط, اسم المنصة) أو (None, None) إن لم يوجد رابط مدعوم.
    """
    tiktok_match = TIKTOK_URL_REGEX.search(text)
    if tiktok_match:
        return tiktok_match.group(0), "tiktok"

    youtube_match = YOUTUBE_URL_REGEX.search(text)
    if youtube_match:
        return youtube_match.group(0), "youtube"

    return None, None


def download_video(url: str, download_dir: str) -> str:
    """
    يحمّل فيديو (تيك توك بدون علامة مائية، أو يوتيوب) باستخدام yt-dlp.
    يرجع مسار الملف المحمّل.
    """
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        # نحدد الجودة لأقصى 720p عشان نقلل احتمال تجاوز حد تيليجرام (50 ميجا)
        # خصوصًا لمقاطع يوتيوب اللي ممكن تكون طويلة أو عالية الجودة
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        return filepath


# ---------------------------------------------------------------------------
# معالجات البوت (Handlers)
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك. 👋\n\n"
        "أرسل رابط مقطع من تيك توك أو يوتيوب وسيتم تحميله لك بأعلى جودة متاحة.\n\n"
        "أمثلة:\n"
        "https://www.tiktok.com/@username/video/1234567890\n"
        "https://www.youtube.com/watch?v=xxxxxxxxxxx\n\n"
        "لمعرفة إمكانيات البوت: /about\n"
        "للدعم الفني: /support"
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 نبذة عن البوت\n\n"
        "هذا البوت مخصص لتحميل المقاطع من المنصات التالية:\n\n"
        "• تيك توك — بدون علامة مائية\n"
        "• يوتيوب\n\n"
        "المميزات:\n"
        "— جودة مطابقة للنسخة الأصلية دون أي ضغط أو تعديل إضافي\n"
        "— بدون علامات مائية إضافية من البوت نفسه\n"
        "— معالجة مباشرة وسريعة\n\n"
        "الأوامر المتاحة:\n"
        "/start — رسالة البداية\n"
        "/help — طريقة الاستخدام\n"
        "/about — هذه الرسالة\n"
        "/support — التواصل مع الدعم الفني"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔹 طريقة الاستخدام\n\n"
        "1. انسخ رابط مقطع من تيك توك أو يوتيوب\n"
        "2. أرسله في هذه المحادثة\n"
        "3. انتظر قليلاً وسيتم إرسال الفيديو بأعلى جودة متاحة\n\n"
        "الأوامر المتاحة:\n"
        "/start — رسالة البداية\n"
        "/about — إمكانيات البوت\n"
        "/help — هذه الرسالة\n"
        "/support — التواصل مع الدعم الفني"
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_awaiting_support.add(update.effective_user.id)
    await update.message.reply_text(
        "🛠️ الدعم الفني\n\n"
        "يرجى وصف المشكلة أو الاستفسار في رسالة واحدة، "
        "وستصل مباشرة إلى فريق الدعم للمتابعة."
    )


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    يلتقط ردود الأدمن على رسائل الدعم المُوجّهة (عبر خاصية Reply في تيليجرام)
    ويرسلها تلقائيًا للمستخدم الأصلي صاحب المشكلة.
    """
    replied_message = update.message.reply_to_message
    if not replied_message or not replied_message.text:
        return

    # نبحث عن سطر "معرف المستخدم: <رقم>" داخل الرسالة الأصلية المُوجّهة
    match = re.search(r"معرف المستخدم:\s*(\d+)", replied_message.text)
    if not match:
        return  # الرسالة المردود عليها مو رسالة دعم موجّهة من البوت

    target_user_id = int(match.group(1))
    reply_text = update.message.text or ""

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"💬 رد من فريق الدعم:\n\n{reply_text}",
        )
        await update.message.reply_text("✅ تم إرسال الرد للمستخدم.")
    except Exception:
        logger.exception("فشل إرسال رد الأدمن للمستخدم")
        await update.message.reply_text(
            "❌ تعذّر إرسال الرد. قد يكون المستخدم حظر البوت أو حذف المحادثة."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    user = update.effective_user

    # لو هذي رسالة من الأدمن نفسه، وهي رد (Reply) على رسالة دعم موجّهة، نعالجها بشكل منفصل
    if (
        str(user.id) == str(ADMIN_CHAT_ID)
        and update.message.reply_to_message is not None
    ):
        await handle_admin_reply(update, context)
        return

    # لو المستخدم بوضع "انتظار رسالة دعم"، نوجّه رسالته للأدمن بدل معالجتها كرابط
    if user.id in users_awaiting_support:
        users_awaiting_support.discard(user.id)

        username_display = f"@{user.username}" if user.username else "بدون يوزرنيم"
        forward_text = (
            f"📩 رسالة دعم جديدة\n\n"
            f"من: {user.full_name} ({username_display})\n"
            f"معرف المستخدم: {user.id}\n\n"
            f"الرسالة:\n{text}\n\n"
            f"↩️ للرد: اعمل Reply على هذه الرسالة واكتب ردك مباشرة"
        )

        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=forward_text)
            await update.message.reply_text(
                "✅ تم إرسال رسالتك لفريق الدعم، سيتم التواصل معك في أقرب وقت."
            )
        except Exception:
            logger.exception("فشل توجيه رسالة الدعم")
            await update.message.reply_text(
                "❌ حدث خطأ أثناء إرسال رسالتك، حاول مرة أخرى لاحقًا."
            )
        return

    url, platform = extract_supported_url(text)

    if not url:
        await update.message.reply_text(
            "ما لقيت رابط مدعوم في رسالتك. أرسل رابط من تيك توك أو يوتيوب."
        )
        return

    status_msg = await update.message.reply_text("⏳ جاري تحميل المقطع...")
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO
    )

    temp_dir = tempfile.mkdtemp()
    try:
        filepath = download_video(url, temp_dir)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"⚠️ حجم الفيديو ({size_mb:.1f} ميجا) أكبر من الحد المسموح "
                f"({MAX_FILE_SIZE_MB} ميجا) لإرساله عبر البوت."
            )
            return

        caption = (
            "✅ تفضل، بدون علامة مائية!"
            if platform == "tiktok"
            else "✅ تفضل، هذا المقطع من يوتيوب!"
        )
        with open(filepath, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
            )
        await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logger.error("خطأ تحميل: %s", e)
        await status_msg.edit_text(
            "❌ تعذّر تحميل المقطع. تأكد من صحة الرابط ومن أن المقطع غير خاص أو محذوف.\n\n"
            "إذا استمرت المشكلة، تواصل مع الدعم الفني عبر /support"
        )
    except Exception as e:
        logger.exception("خطأ غير متوقع")
        await status_msg.edit_text(f"❌ صار خطأ غير متوقع: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# نقطة التشغيل
# ---------------------------------------------------------------------------

async def setup_commands(app):
    """
    يسجّل قائمة الأوامر عند تيليجرام عشان تظهر بقائمة "/" أو "≡"
    جنب صندوق الكتابة داخل شات البوت.
    """
    from telegram import BotCommand

    await app.bot.set_my_commands(
        [
            BotCommand("start", "بدء استخدام البوت"),
            BotCommand("about", "إمكانيات البوت"),
            BotCommand("help", "طريقة الاستخدام"),
            BotCommand("support", "التواصل مع الدعم الفني"),
        ]
    )


def main():
    if not BOT_TOKEN or BOT_TOKEN == "ضع_توكن_البوت_هنا":
        raise SystemExit(
            "الرجاء ضبط توكن البوت أولاً (متغير BOT_TOKEN أو داخل الكود مباشرة)."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال...")
    app.run_polling()


if __name__ == "__main__":
    main()
