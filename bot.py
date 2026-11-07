import os
import random
import threading
import time
import uuid
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent

# دریافت توکن از متغیرهای محیطی سرور رندر (برای امنیت در گیت‌هاب عمومی)
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_FALLBACK_TOKEN_IF_TESTING_LOCALLY')
bot = telebot.TeleBot(TOKEN)

# وب‌سرور سبک برای زنده نگه داشتن ربات روی Render
app = Flask(__name__)

# حافظه موقت برای نگهداری گزینه‌های هر گردونه
WHEELS_STORAGE = {}


@app.route('/')
def index():
  return '🎯 Spin Wheel Bot is Alive and Running!', 200


# ۱. مدیریت درخواست اینلاین در چت خصوصی (@BotName گزینه۱، گزینه۲)
@bot.inline_handler(lambda query: True)
def inline_wheel_builder(query):
  text = query.query.strip()

  # پشتیبانی از ویرگول فارسی (،) و انگلیسی (,) و خط تیره (-) برای جدا کردن گزینه‌ها
  normalized_text = text.replace('،', ',').replace('-', ',')
  options = [opt.strip() for opt in normalized_text.split(',') if opt.strip()]

  if len(options) < 2:
    help_item = InlineQueryResultArticle(
        id='help',
        title='🎡 ساخت گردونه شانس شخصی',
        description='حداقل ۲ گزینه بنویسید و با ویرگول جدا کنید (مثال: فیلم، بازی، کافه)',
        input_message_content=InputTextMessageContent(
            '❌ برای ساخت گردونه، آیدی ربات را تایپ کرده و حداقل ۲ گزینه با ویرگول وارد کنید.\n'
            'مثال:\n`@BotName پیتزا، برگر، سوخاری`',
            parse_mode='Markdown',
        ),
    )
    bot.answer_inline_query(query.id, [help_item], cache_time=1)
    return

  # ساخت شناسه کوتاه برای دور زدن محدودیت 64 بایتی تلگرام
  wheel_id = str(uuid.uuid4())[:8]
  WHEELS_STORAGE[wheel_id] = options

  # طراحی متن اولیه گردونه در چت
  options_formatted = '\n'.join([f'▫️ {opt}' for opt in options])
  msg_text = (
      f'🎡 **گردونه شانس آماده چرخش است!**\n\n'
      f'📋 **گزینه‌ها:**\n{options_formatted}\n\n'
      f'👇 یکی از شما دو نفر دکمه زیر رو بزنه تا بچرخه:'
  )

  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          '🎲 بچرخون!', callback_data=f'spin:{wheel_id}'
      )
  )

  result_item = InlineQueryResultArticle(
      id=wheel_id,
      title=f'✅ ارسال گردونه ({len(options)} گزینه)',
      description=' | '.join(options),
      input_message_content=InputTextMessageContent(
          msg_text, parse_mode='Markdown'
      ),
      reply_markup=markup,
  )

  bot.answer_inline_query(query.id, [result_item], cache_time=1)


# ۲. تابع کمکی برای بازیابی گزینه‌ها از روی متن پیام (اگر سرور ری‌استارت شده باشد)
def extract_options_from_message(wheel_id):
  return WHEELS_STORAGE.get(wheel_id, None)


# ۳. مدیریت کلیک روی دکمه چرخش و اجرای انیمیشن در چت خصوصی
@bot.callback_query_handler(func=lambda call: call.data.startswith('spin:'))
def handle_wheel_spin(call):
  wheel_id = call.data.split(':')[1]
  options = extract_options_from_message(wheel_id)

  # نام کاربری که دکمه را فشار داده
  spinner_name = call.from_user.first_name

  if not options:
    bot.answer_callback_query(
        call.id,
        '⚠️ این گردونه قدیمی شده! لطفاً یک گردونه جدید بسازید.',
        show_alert=True,
    )
    return

  # اعلام شروع چرخش در بالای صفحه
  bot.answer_callback_query(call.id, '🎡 گردونه در حال چرخش است...')

  # اجرای انیمیشن چرخش (۴ مرحله جابه‌جایی نشانگر روی گزینه‌ها)
  steps = 4
  current_pick = None

  for i in range(steps):
    current_pick = random.choice(options)
    anim_lines = []
    for opt in options:
      if opt == current_pick:
        anim_lines.append(f'👉 **{opt}** 👈')
      else:
        anim_lines.append(f'▫️ {opt}')

    anim_text = (
        f'🌀 **گردونه توسط {spinner_name} در حال چرخش است...**\n\n'
        + '\n'.join(anim_lines)
    )

    try:
      if call.inline_message_id:
        bot.edit_message_text(
            text=anim_text,
            inline_message_id=call.inline_message_id,
            parse_mode='Markdown',
        )
      elif call.message:
        bot.edit_message_text(
            text=anim_text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='Markdown',
        )
    except Exception:
      pass

    time.sleep(0.55)  # مکث کوتاه بین هر مرحله برای ایجاد حس چرخش

  # انتخاب برنده نهایی
  winner = random.choice(options)
  final_lines = []
  for opt in options:
    if opt == winner:
      final_lines.append(f'🎯 **{opt}** 👑')
    else:
      final_lines.append(f'▫️ {opt}')

  final_text = (
      f'🎉 **نتیجه گردونه شانس!**\n'
      f'👤 چرخاننده: {spinner_name}\n\n'
      + '\n'.join(final_lines)
      + f'\n\n✨ **برنده نهایی:** `{winner}`'
  )

  # اضافه کردن دکمه چرخش مجدد برای همان گردونه
  retry_markup = InlineKeyboardMarkup()
  retry_markup.add(
      InlineKeyboardButton(
          '🔄 چرخش دوباره همین گردونه', callback_data=f'spin:{wheel_id}'
      )
  )

  try:
    if call.inline_message_id:
      bot.edit_message_text(
          text=final_text,
          inline_message_id=call.inline_message_id,
          parse_mode='Markdown',
          reply_markup=retry_markup,
      )
    elif call.message:
      bot.edit_message_text(
          text=final_text,
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          parse_mode='Markdown',
          reply_markup=retry_markup,
      )
  except Exception:
    pass


# ۴. اجرای همزمان ربات تلگرام و وب‌سرور Flask
def run_telegram_bot():
  print('🤖 Starting Telegram Polling...')
  bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == '__main__':
  # اجرای ربات در یک ترد (Thread) پس‌زمینه
  bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
  bot_thread.start()

  # اجرای وب‌سرور Flask روی پورت مشخص‌شده توسط Render
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)
