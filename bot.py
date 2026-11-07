import math
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

# حافظه نگهداری گردونه‌ها
WHEELS = {}

# پالت رنگ‌های گردونه (همگی دقیقاً هم‌عرض هستند تا دایره صاف بماند)
COLORS = ['🟥', '🟦', '🟩', '🟨', '🟪', '🟧', '🟫', '⬛']
BG_PIXEL = '⬜'
CENTER_PIXEL = '🎡'


@app.route('/')
def index():
  return '🎨 Pixel Art Spin Wheel Bot is Live!', 200


def render_pie_wheel(items, rotation_deg=0, pointer='🔻'):
  """ساخت دایره پیکسلی کاملاً صاف و گرد که بر اساس وزن (شانس) هر گزینه

  به نیم‌دایره، ۳ قاچ یا چند قاچ رنگی تقسیم می‌شود.
  """
  active_items = [item for item in items if item['weight'] > 0]
  total_weight = sum(item['weight'] for item in active_items)

  if total_weight == 0:
    active_items = items
    total_weight = len(items)

  # محاسبه بازه زاویه‌ای هر گزینه از 0 تا 360 درجه
  slices = []
  current_angle = 0.0
  for item in active_items:
    w = item['weight'] if item['weight'] > 0 else 1
    span = (w / total_weight) * 360.0
    slices.append((current_angle, current_angle + span, item))
    current_angle += span

  # پیدا کردن گزینه‌ای که الان در نقطه 0 درجه (زیر عقربه 🔻) قرار دارد
  top_angle = (0 - rotation_deg) % 360
  current_top_item = active_items[0]
  for start_a, end_a, item in slices:
    if start_a <= top_angle <= end_a:
      current_top_item = item
      break

  # رسم شبکه دایره (شعاع ۴ واحد = قطر ۹ بلوک هم‌اندازه)
  radius = 4
  rows = []

  # ردیف عقربه بالای دایره
  pointer_row = [BG_PIXEL] * (2 * radius + 1)
  pointer_row[radius] = pointer
  rows.append(''.join(pointer_row))

  for y in range(-radius, radius + 1):
    row_str = ''
    for x in range(-radius, radius + 1):
      dist = math.sqrt(x * x + y * y)
      if x == 0 and y == 0:
        row_str += CENTER_PIXEL
      elif dist <= radius + 0.35:  # فرمول گرد شدن کامل لبه‌های دایره
        # محاسبه زاویه هر پیکسل نسبت به مرکز (بالای دایره = 0 درجه، ساعت‌گرد)
        angle = (math.degrees(math.atan2(x, -y)) + 360) % 360
        shifted_angle = (angle - rotation_deg) % 360

        pixel_color = active_items[-1]['color']
        for start_a, end_a, item in slices:
          if start_a <= shifted_angle <= end_a:
            pixel_color = item['color']
            break
        row_str += pixel_color
      else:
        row_str += BG_PIXEL
    rows.append(row_str)

  return '\n'.join(rows), current_top_item


def render_wheel_message(wheel, status_title='🎡 **گردونه شانس آماده است!**', winner=None):
  items = wheel['items']
  rot = wheel.get('rotation', 0)
  pointer = '🎯' if winner else '🔻'

  pie_art, top_item = render_pie_wheel(items, rotation_deg=rot, pointer=pointer)

  active_items = [i for i in items if i['weight'] > 0]
  total_weight = sum(i['weight'] for i in active_items) or 1

  legend_lines = []
  for item in items:
    w = item['weight']
    if w == 0:
      legend_lines.append(f"❌ ~{item['name']}~ *(حذف شده)*")
    else:
      pct = int(round((w / total_weight) * 100))
      mult = f'🔥`{w}x`' if w > 1 else '`1x`'
      if winner and winner['name'] == item['name']:
        legend_lines.append(
            f"👉 {item['color']} **{item['name']}** ({mult} | شانس: {pct}%) 👑"
        )
      elif not winner and top_item['name'] == item['name']:
        legend_lines.append(
            f"🔸 {item['color']} **{item['name']}** ({mult} | {pct}%) 👈"
        )
      else:
        legend_lines.append(
            f"▫️ {item['color']} {item['name']} ({mult} | {pct}%)"
        )

  legend_text = '\n'.join(legend_lines)

  msg = (
      f'{status_title}\n\n'
      f'{pie_art}\n\n'
      f'🎨 **راهنمای رنگ‌ها و ضریب شانس:**\n'
      f'{legend_text}'
  )
  if winner:
    msg += f"\n\n🎉 **برنده نهایی:** {winner['color']} **`{winner['name']}`** ✨"

  return msg


def get_main_keyboard(w_id):
  markup = InlineKeyboardMarkup(row_width=2)
  markup.add(
      InlineKeyboardButton('🎲 بچرخون!', callback_data=f'spin:{w_id}'),
      InlineKeyboardButton(
          '💀 چرخش حذفی', callback_data=f'elim:{w_id}'
      ),
  )
  markup.add(
      InlineKeyboardButton(
          '⚙️ کاستوم و تغییر شانس (1x/2x/3x)',
          callback_data=f'menu_cust:{w_id}',
      )
  )
  return markup


def get_custom_keyboard(w_id, wheel):
  markup = InlineKeyboardMarkup(row_width=2)
  buttons = []
  for idx, item in enumerate(wheel['items']):
    w = item['weight']
    status = f'{w}x' if w > 0 else '❌'
    btn_text = f"{item['color']} {item['name']} [{status}]"
    buttons.append(
        InlineKeyboardButton(btn_text, callback_data=f'wgt:{w_id}:{idx}')
    )

  markup.add(*buttons)

  # دکمه‌های کمکی کاستومایز
  markup.row(
      InlineKeyboardButton(
          '➕ افزودن گزینه جدید', callback_data=f'add_opt:{w_id}'
      ),
      InlineKeyboardButton(
          '🔄 ریست همه به 1x', callback_data=f'rst:{w_id}'
      ),
  )
  markup.row(
      InlineKeyboardButton(
          '✅ ذخیره و بازگشت به گردونه', callback_data=f'back:{w_id}'
      )
  )
  return markup


def create_wheel(option_names):
  w_id = str(uuid.uuid4())[:8]
  items = []
  for i, name in enumerate(option_names[:8]):
    items.append({
        'name': name,
        'color': COLORS[i % len(COLORS)],
        'weight': 1,  # شانس پیش‌فرض: ۱ برابر
    })
  WHEELS[w_id] = {'items': items, 'rotation': 0}
  return w_id, WHEELS[w_id]


@bot.inline_handler(lambda query: True)
def inline_query_handler(query):
  text = query.query.strip()

  # اگر کاربر چیزی ننوشت، پنل گردونه آماده کاستوم با ۲ گزینه پیش‌فرض بساز
  if not text:
    default_opts = ['گزینه ۱', 'گزینه ۲']
    w_id, wheel = create_wheel(default_opts)
    msg_text = render_wheel_message(
        wheel,
        '🎡 **پنل گردونه ساخته شد!**\n*(برای نوشتن گزینه‌های خودت، بعد از آیدی بات با کاما بنویس یا از دکمه کاستوم استفاده کن)*',
    )
    item = InlineQueryResultArticle(
        id=w_id,
        title='🎡 ارسال گردونه به چت (قابل کاستومایز)',
        description='یا همین الان بفرست تو چت، یا گزینه‌هاتو با ویرگول تایپ کن: گزینه۱، گزینه۲',
        input_message_content=InputTextMessageContent(
            msg_text, parse_mode='Markdown'
        ),
        reply_markup=get_main_keyboard(w_id),
    )
    bot.answer_inline_query(query.id, [item], cache_time=1)
    return

  # جدا کردن گزینه‌های کاربر (پشتیبانی از ضریب مستقیم مثل: پیتزا*2، برگر)
  normalized = text.replace('،', ',').replace('-', ',')
  raw_parts = [p.strip() for p in normalized.split(',') if p.strip()]

  if len(raw_parts) < 2:
    raw_parts.append('گزینه ۲')

  w_id = str(uuid.uuid4())[:8]
  items = []
  for i, part in enumerate(raw_parts[:8]):
    weight = 1
    name = part
    # اگر کاربر نوشت مثلا: پیتزا*3 یا پیتزا 2x
    if '*' in part:
      sp = part.split('*')
      name = sp[0].strip()
      if sp[1].strip().isdigit():
        weight = max(1, min(5, int(sp[1].strip())))

    items.append({
        'name': name,
        'color': COLORS[i % len(COLORS)],
        'weight': weight,
    })

  WHEELS[w_id] = {'items': items, 'rotation': 0}
  wheel = WHEELS[w_id]

  msg_text = render_wheel_message(wheel)
  result = InlineQueryResultArticle(
      id=w_id,
      title=f'🎨 ساخت گردونه دایره‌ای ({len(items)} گزینه)',
      description=' | '.join([f"{it['color']} {it['name']}" for it in items]),
      input_message_content=InputTextMessageContent(
          msg_text, parse_mode='Markdown'
      ),
      reply_markup=get_main_keyboard(w_id),
  )
  bot.answer_inline_query(query.id, [result], cache_time=1)


def edit_msg(call, text, markup=None):
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


@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
  data = call.data.split(':')
  action = data[0]
  w_id = data[1] if len(data) > 1 else None

  wheel = WHEELS.get(w_id)
  if not wheel:
    bot.answer_callback_query(
        call.id,
        '⚠️ این گردونه منقضی شده! دوباره با @ آیدی بات بفرستید.',
        show_alert=True,
    )
    return

  user = call.from_user.first_name

  # ۱. باز کردن منوی شیشه‌ای کاستومایز
  if action == 'menu_cust':
    text = render_wheel_message(
        wheel,
        '⚙️ **منوی کاستومایز گردونه**\n💡 *روی هر گزینه بزن تا شانسش توی دایره ۲ برابر (2x)، ۳ برابر (3x) یا ۴ برابر بشه!*',
    )
    edit_msg(call, text, get_custom_keyboard(w_id, wheel))
    bot.answer_callback_query(call.id, '⚙️ وارد بخش کاستوم شدی!')
    return

  # ۲. تغییر ضریب شانس هر گزینه (1x -> 2x -> 3x -> 4x -> خاموش -> 1x)
  if action == 'wgt':
    idx = int(data[2])
    item = wheel['items'][idx]
    cycle = {1: 2, 2: 3, 3: 4, 4: 0, 0: 1}
    new_w = cycle.get(item['weight'], 1)

    # جلوگیری از خاموش شدن همه گزینه‌ها
    active_count = sum(1 for it in wheel['items'] if it['weight'] > 0)
    if new_w == 0 and active_count <= 1:
      new_w = 1

    item['weight'] = new_w
    text = render_wheel_message(
        wheel,
        f"⚙️ **شانس «{item['name']}» تغییر کرد!**\n*(ببین قاچ {item['color']} توی دایره چطور تغییر سایز داد!)*",
    )
    edit_msg(call, text, get_custom_keyboard(w_id, wheel))
    bot.answer_callback_query(
        call.id,
        f"شانس {item['name']}: {new_w} برابر شد"
        if new_w > 0
        else f"{item['name']} غیرفعال شد",
    )
    return

  # ۳. افزودن گزینه جدید از داخل چت
  if action == 'add_opt':
    if len(wheel['items']) >= 8:
      bot.answer_callback_query(
          call.id, '⚠️ حداکثر ۸ رنگ در دایره جا می‌شود!', show_alert=True
      )
      return
    new_idx = len(wheel['items']) + 1
    wheel['items'].append({
        'name': f'گزینه {new_idx}',
        'color': COLORS[(new_idx - 1) % len(COLORS)],
        'weight': 1,
    })
    text = render_wheel_message(
        wheel, f'➕ **گزینه {new_idx} به دایره اضافه شد!**'
    )
    edit_msg(call, text, get_custom_keyboard(w_id, wheel))
    bot.answer_callback_query(call.id, 'گزینه جدید اضافه شد!')
    return

  # ۴. ریست کردن تمام ضرایب به حالت مساوی (1x)
  if action == 'rst':
    for it in wheel['items']:
      it['weight'] = 1
    text = render_wheel_message(
        wheel, '🔄 **تمام قاچ‌های دایره دوباره مساوی (1x) شدند!**'
    )
    edit_msg(call, text, get_custom_keyboard(w_id, wheel))
    bot.answer_callback_query(call.id, 'همه شانس‌ها مساوی شد!')
    return

  # ۵. بازگشت از منوی کاستوم به صفحه اصلی گردونه
  if action == 'back':
    text = render_wheel_message(
        wheel, '✅ **تغییرات ذخیره شد! آماده چرخش:**'
    )
    edit_msg(call, text, get_main_keyboard(w_id))
    bot.answer_callback_query(call.id, 'ذخیره شد!')
    return

  # ۶. چرخش اصلی دایره رنگی (یا چرخش حذفی)
  if action in ['spin', 'elim']:
    active_items = [it for it in wheel['items'] if it['weight'] > 0]
    if not active_items:
      for it in wheel['items']:
        it['weight'] = 1
      active_items = wheel['items']

    bot.answer_callback_query(call.id, '🎡 گردونه داره می‌چرخه...')

    # ۵ فریم چرخش زاویه‌ای رنگ‌های دایره
    current_rot = wheel.get('rotation', 0)
    for step in range(4):
      current_rot = (current_rot + random.randint(55, 110)) % 360
      wheel['rotation'] = current_rot
      anim_msg = render_wheel_message(
          wheel, f'🌀 **در حال چرخش توسط {user}...**'
      )
      edit_msg(call, anim_msg)
      time.sleep(0.55)

    # انتخاب برنده نهایی دقیقاً بر اساس زاویه و وزن شانس
    final_rot = (current_rot + random.randint(40, 160)) % 360
    wheel['rotation'] = final_rot
    _, winner = render_pie_wheel(wheel['items'], rotation_deg=final_rot)

    if action == 'elim':
      winner['weight'] = 0  # حذف از دور بعدی
      alive_left = [it for it in wheel['items'] if it['weight'] > 0]
      if len(alive_left) == 1:
        champ = alive_left[0]
        final_msg = render_wheel_message(
            wheel,
            f'🏆 **پایان دور حذفی! ({winner["name"]} حذف شد)**',
            winner=champ,
        )
      else:
        final_msg = render_wheel_message(
            wheel,
            f'💀 **گزینه {winner["color"]} «{winner["name"]}» حذف شد و از دایره بیرون رفت!**',
        )
    else:
      final_msg = render_wheel_message(
          wheel, f'🎯 **گردونه ایستاد! (توسط {user})**', winner=winner
      )

    edit_msg(call, final_msg, get_main_keyboard(w_id))


def run_bot():
  bot.infinity_polling(timeout=20, long_polling_timeout=10)


if __name__ == '__main__':
  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)
