import os
import random
import threading
import time
import uuid
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent

TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_FALLBACK_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ذخیره‌ساز وضعیت گردونه‌ها در حافظه
# ساختار: {wheel_id: {"options": [...], "slots": [...], "eliminated": [...], "scores": {...}}}
WHEELS = {}

# ایموجی‌های شماره‌دار برای ۱۰ خانه گردونه
NUM_EMOJIS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

# دسته‌بندی‌های آماده وقتی کاربر چیزی تایپ نمی‌کند
PRESET_CATEGORIES = [
    {
        'id': 'preset_food',
        'title': '🍕 گردونه شام و غذا',
        'desc': 'پیتزا، برگر، پاستا، سوخاری، کباب، ساندویچ',
        'options': ['پیتزا', 'برگر', 'پاستا', 'سوخاری', 'کباب', 'ساندویچ'],
    },
    {
        'id': 'preset_movie',
        'title': '🎬 گردونه ژانر فیلم و انیمه',
        'desc': 'اکشن، ترسناک، کمدی، علمی‌تخیلی، انیمه، معمایی',
        'options': ['اکشن', 'ترسناک', 'کمدی', 'علمی‌تخیلی', 'انیمه', 'معمایی'],
    },
    {
        'id': 'preset_date',
        'title': '💑 گردونه کارهای دونفره',
        'desc': 'فیلم دیدن، بازی کردن، موزیک گوش دادن، چت طولانی، کوییز',
        'options': [
            'فیلم دیدن',
            'گیم زدن',
            'موزیک و چت',
            'صندلی داغ',
            'پانتومیم/کوییز',
        ],
    },
    {
        'id': 'preset_yesno',
        'title': '⚖️ گردونه تصمیم‌گیری (آره یا نه؟)',
        'desc': '۱۰۰٪ آره، نه اصلاً، شاید، بنداز فردا، حتماً انجامش بده',
        'options': [
            '۱۰۰٪ آره',
            'نه اصلاً',
            'بنداز فردا',
            'حتماً انجام بده',
            'شانس دوباره',
        ],
    },
]


@app.route('/')
def index():
  return '🎡 Ultimate Spin Wheel Bot is Running!', 200


def fill_10_slots(options):
  """توزیع متوازن گزینه‌ها در ۱۰ خانه دایره"""
  slots = [options[i % len(options)] for i in range(10)]
  return slots


def render_circle_wheel(slots, offset=0, pointer_emoji='🔻'):
  """طراحی گرافیکی دایره ۱۰ خانه‌ای که با تغییر offset می‌چرخد"""
  # چرخاندن آرایه بر اساس offset
  s = [NUM_EMOJIS[(i + offset) % 10] for i in range(10)]

  # خانه شماره 0 همیشه زیر عقربه (بالای دایره) قرار دارد
  circle_art = (
      f'```text\n'
      f'          {pointer_emoji}\n'
      f'        [ {s[0]} ]\n'
      f'    {s[9]}          {s[1]}\n'
      f' {s[8]}                {s[2]}\n'
      f' {s[7]}       🎡       {s[3]}\n'
      f'    {s[6]}          {s[4]}\n'
      f'        {s[5]}\n'
      f'```'
  )
  return circle_art, (0 + offset) % 10


def build_legend(slots, active_idx=None, eliminated=None, scores=None):
  """ساخت راهنمای شماره‌های گردونه در پایین دایره"""
  if eliminated is None:
    eliminated = []
  if scores is None:
    scores = {}

  lines = []
  for i in range(10):
    opt = slots[i]
    num = NUM_EMOJIS[i]
    score_str = f' (⭐️{scores.get(opt, 0)})' if opt in scores else ''

    if opt in eliminated:
      lines.append(f'{num} : ~{opt}~ ❌')
    elif i == active_idx:
      lines.append(f'👉 {num} : **{opt}**{score_str} 👈')
    else:
      lines.append(f'{num} : {opt}{score_str}')

  # نمایش دو ستونی برای جمع‌وجور شدن پیام
  col1 = lines[:5]
  col2 = lines[5:]
  combined = [f'{col1[i]}   |   {col2[i]}' for i in range(5)]
  return '\n'.join(combined)


def get_wheel_keyboard(wheel_id):
  markup = InlineKeyboardMarkup(row_width=2)
  markup.add(
      InlineKeyboardButton(
          '🎡 چرخش کلاسیک!', callback_data=f'spin_norm:{wheel_id}'
      ),
      InlineKeyboardButton(
          '⚔️ دوئل (۳ امتیازی)', callback_data=f'spin_duel:{wheel_id}'
      ),
      InlineKeyboardButton(
          '💀 دور حذفی (حذف ۱ گزینه)', callback_data=f'spin_elim:{wheel_id}'
      ),
      InlineKeyboardButton(
          '🔀 بُر زدن خانه‌ها', callback_data=f'shuffle:{wheel_id}'
      ),
  )
  return markup


def create_wheel_entry(options):
  wheel_id = str(uuid.uuid4())[:8]
  slots = fill_10_slots(options)
  WHEELS[wheel_id] = {
      'options': options,
      'slots': slots,
      'eliminated': [],
      'scores': {opt: 0 for opt in options},
  }
  return wheel_id, slots


# پاسخ به دستور /start در پی‌وی ربات
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
  guide = (
      '🎡 **به ربات گردونه شانس پیشرفته خوش اومدی!**\n\n'
      'این ربات طوری طراحی شده که مستقیم داخل **چت خصوصی دو نفره** کار کنه.\n\n'
      '🔹 **روش اول (گزینه‌های دلخواه):**\n'
      'توی هر چتی هستی تایپ کن:\n'
      '`@Gardonebababot گزینه ۱، گزینه ۲، گزینه ۳`\n\n'
      '🔹 **روش دوم (کتگوری‌های آماده):**\n'
      'فقط آیدی `@Gardonebababot` رو تایپ کن و یک فاصله بزن تا گردونه‌های آماده (غذا، فیلم، بازی و...) برات باز بشه!\n\n'
      '✨ **قابلیت‌های گردونه:**\n'
      '• **چرخش دایره‌ای ۱۰ خانه‌ای:** تقسیم خودکار گزینه‌ها در دایره\n'
      '• **حالت دوئل (⚔️):** چرخش پیاپی تا وقتی یک گزینه به ۲ امتیاز برسه\n'
      '• **حالت حذفی (💀):** هر بار یک گزینه حذف میشه تا فقط یکی بمونه!'
  )
  bot.reply_to(message, guide, parse_mode='Markdown')


# مدیریت حالت اینلاین در چت‌ها
@bot.inline_handler(lambda query: True)
def inline_handler(query):
  text = query.query.strip()
  results = []

  # اگر کاربر چیزی تایپ نکرده بود، کتگوری‌های آماده رو نشون بده
  if not text:
    for preset in PRESET_CATEGORIES:
      w_id, slots = create_wheel_entry(preset['options'])
      circle, _ = render_circle_wheel(slots, 0)
      legend = build_legend(slots)
      msg_text = (
          f"🎡 **{preset['title']}**\n"
          f'{circle}\n'
          f'📋 **راهنمای خانه‌های گردونه:**\n{legend}\n\n'
          f'👇 حالت چرخش رو انتخاب کنید:'
      )
      results.append(
          InlineQueryResultArticle(
              id=w_id,
              title=preset['title'],
              description=preset['desc'],
              input_message_content=InputTextMessageContent(
                  msg_text, parse_mode='Markdown'
              ),
              reply_markup=get_wheel_keyboard(w_id),
          )
      )
    bot.answer_inline_query(query.id, results, cache_time=1)
    return

  # جدا کردن گزینه‌های تایپ‌شده توسط کاربر
  normalized = text.replace('،', ',').replace('-', ',')
  options = []
  for opt in normalized.split(','):
    clean_opt = opt.strip()
    if clean_opt and clean_opt not in options:
      options.append(clean_opt)

  if len(options) < 2:
    help_article = InlineQueryResultArticle(
        id='err_min',
        title='⚠️ حداقل ۲ گزینه متفاوت بنویسید!',
        description='گزینه‌ها را با ویرگول جدا کنید (یا خالی بگذارید تا منوی آماده باز شود)',
        input_message_content=InputTextMessageContent(
            '❌ لطفاً حداقل ۲ گزینه با ویرگول وارد کنید.\nمثال: `@Gardonebababot پیتزا، برگر`',
            parse_mode='Markdown',
        ),
    )
    bot.answer_inline_query(query.id, [help_article], cache_time=1)
    return

  # محدود کردن به حداکثر ۱۰ گزینه برای جا شدن در دایره
  options = options[:10]
  w_id, slots = create_wheel_entry(options)
  circle, _ = render_circle_wheel(slots, 0)
  legend = build_legend(slots)

  msg_text = (
      f'🎡 **گردونه شانس ۱۰ خانه‌ای آماده است!**\n'
      f'{circle}\n'
      f'📋 **راهنمای خانه‌ها (توزیع در ۱۰ اسلات):**\n{legend}\n\n'
      f'👇 یکی از حالت‌های زیر رو برای چرخش انتخاب کن:'
  )

  results.append(
      InlineQueryResultArticle(
          id=w_id,
          title=f'✅ ارسال گردونه دایره‌ای ({len(options)} گزینه در ۱۰ خانه)',
          description=' | '.join(options),
          input_message_content=InputTextMessageContent(
              msg_text, parse_mode='Markdown'
          ),
          reply_markup=get_wheel_keyboard(w_id),
      )
  )

  bot.answer_inline_query(query.id, results, cache_time=1)


def edit_inline_or_chat(call, text, markup=None):
  try:
    if call.inline_message_id:
      bot.edit_message_text(
          text=text,
          inline_message_id=call.inline_message_id,
          parse_mode='Markdown',
          reply_markup=markup,
      )
    elif call.message:
      bot.edit_message_text(
          text=text,
          chat_id=call.message.chat.id,
          message_id=call.message.message_id,
          parse_mode='Markdown',
          reply_markup=markup,
      )
  except Exception:
    pass


# مدیریت کلیک روی دکمه‌های گردونه
@bot.callback_query_handler(
    func=lambda call: ':' in call.data
    and call.data.split(':')[0]
    in ['spin_norm', 'spin_duel', 'spin_elim', 'shuffle']
)
def handle_callbacks(call):
  action, w_id = call.data.split(':')
  wheel = WHEELS.get(w_id)

  if not wheel:
    bot.answer_callback_query(
        call.id,
        '⚠️ حافظه این گردونه پاک شده! لطفاً یک گردونه جدید بفرستید.',
        show_alert=True,
    )
    return

  user_name = call.from_user.first_name
  slots = wheel['slots']

  # ۱. حالت بُر زدن خانه‌های دایره (Shuffle)
  if action == 'shuffle':
    random.shuffle(wheel['slots'])
    wheel['eliminated'] = []
    wheel['scores'] = {opt: 0 for opt in wheel['options']}
    circle, _ = render_circle_wheel(wheel['slots'], 0)
    legend = build_legend(wheel['slots'])
    new_text = (
        f'🔀 **خانه‌های گردونه توسط {user_name} بُر زده شد!**\n'
        f'{circle}\n'
        f'📋 **چیدمان جدید خانه‌ها:**\n{legend}\n\n'
        f'👇 آماده چرخش:'
    )
    edit_inline_or_chat(call, new_text, get_wheel_keyboard(w_id))
    bot.answer_callback_query(call.id, '🔀 چیدمان دایره عوض شد!')
    return

  # ۲. حالت چرخش کلاسیک دایره‌ای
  if action == 'spin_norm':
    bot.answer_callback_query(call.id, '🎡 گردونه در حال چرخش است...')
    start_offset = random.randint(0, 9)
    total_steps = 5  # ۵ فریم چرخش برای جلوگیری از محدودیت تلگرام

    for step in range(total_steps):
      current_offset = (start_offset + step * 2 + 1) % 10
      circle, top_idx = render_circle_wheel(
          slots, current_offset, pointer_emoji='🔻'
      )
      legend = build_legend(slots, active_idx=top_idx)
      anim_text = (
          f'🌀 **در حال چرخش توسط {user_name}... (گام {step+1} از {total_steps})**\n'
          f'{circle}\n'
          f'📋 **خانه‌ها:**\n{legend}'
      )
      edit_inline_or_chat(call, anim_text)
      time.sleep(0.6)

    # توقف نهایی
    final_offset = random.randint(0, 9)
    circle, win_idx = render_circle_wheel(
        slots, final_offset, pointer_emoji='🎯'
    )
    winner = slots[win_idx]
    legend = build_legend(slots, active_idx=win_idx)

    final_text = (
        f'🎉 **گردونه ایستاد! (چرخاننده: {user_name})**\n'
        f'{circle}\n'
        f'📋 **وضعیت خانه‌ها:**\n{legend}\n\n'
        f'👑 **برنده نهایی:** خانه {NUM_EMOJIS[win_idx]} یعنی **`{winner}`** ✨'
    )
    edit_inline_or_chat(call, final_text, get_wheel_keyboard(w_id))
    return

  # ۳. حالت حذفی (Battle Royale)
  if action == 'spin_elim':
    alive_options = [
        opt for opt in wheel['options'] if opt not in wheel['eliminated']
    ]
    if len(alive_options) <= 1:
      wheel['eliminated'] = []  # ریست کردن اگر قبلاً تموم شده
      alive_options = wheel['options'][:]

    bot.answer_callback_query(call.id, '💀 چرخش برای حذف یک گزینه...')

    # انتخاب یک خانه از بین گزینه‌های زنده
    alive_indices = [
        i for i, opt in enumerate(slots) if opt not in wheel['eliminated']
    ]
    elim_idx = random.choice(alive_indices)
    eliminated_opt = slots[elim_idx]
    wheel['eliminated'].append(eliminated_opt)

    remaining = [
        opt for opt in wheel['options'] if opt not in wheel['eliminated']
    ]
    circle, _ = render_circle_wheel(slots, elim_idx, pointer_emoji='💀')
    legend = build_legend(
        slots, active_idx=elim_idx, eliminated=wheel['eliminated']
    )

    if len(remaining) == 1:
      survivor = remaining[0]
      text = (
          f'🏆 **پایان نبرد حذفی! (توسط {user_name})**\n'
          f'{circle}\n'
          f'❌ گزینه `{eliminated_opt}` هم حذف شد!\n\n'
          f'📋 **وضعیت نهایی:**\n{legend}\n\n'
          f'👑 **تنها بازمانده و برنده مطلق:** **`{survivor}`** 🔥'
      )
    else:
      text = (
          f'💀 **دور حذفی (توسط {user_name})**\n'
          f'{circle}\n'
          f'❌ گزینه **`{eliminated_opt}`** از گردونه خارج شد!\n'
          f'🟢 گزینه‌های باقی‌مانده: `{len(remaining)}` گزینه\n\n'
          f'📋 **وضعیت خانه‌ها:**\n{legend}\n\n'
          f'👇 دوباره روی «دور حذفی» بزنید تا بعدی حذف بشه:'
      )
    edit_inline_or_chat(call, text, get_wheel_keyboard(w_id))
    return

  # ۴. حالت دوئل امتیازی (اولین گزینه‌ای که به ۲ امتیاز برسد)
  if action == 'spin_duel':
    bot.answer_callback_query(call.id, '⚔️ ماراتن دوئل شروع شد!')
    wheel['scores'] = {opt: 0 for opt in wheel['options']}
    champion = None
    round_num = 1

    while not champion and round_num <= 6:
      pick_idx = random.randint(0, 9)
      picked_opt = slots[pick_idx]
      wheel['scores'][picked_opt] += 1

      if wheel['scores'][picked_opt] >= 2:
        champion = picked_opt

      circle, _ = render_circle_wheel(slots, pick_idx, pointer_emoji='⚔️')
      legend = build_legend(slots, active_idx=pick_idx, scores=wheel['scores'])

      round_text = (
          f'⚔️ **دوئل گردونه - راند {round_num} (توسط {user_name})**\n'
          f'{circle}\n'
          f'🎯 این راند افتاد روی: **`{picked_opt}`** (+۱ امتیاز)\n\n'
          f'📋 **جدول امتیازات:**\n{legend}'
      )
      edit_inline_or_chat(call, round_text)
      round_num += 1
      if not champion:
        time.sleep(0.75)

    final_duel_text = (
        f'🏆 **پایان دوئل نفس‌گیر! (چرخاننده: {user_name})**\n'
        f'{circle}\n'
        f'📋 **امتیازات نهایی:**\n{legend}\n\n'
        f'👑 **قهرمان دوئل (با کسب ۲ ستاره):** **`{champion}`** 🎉'
    )
    edit_inline_or_chat(call, final_duel_text, get_wheel_keyboard(w_id))


def run_bot():
  bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == '__main__':
  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)
