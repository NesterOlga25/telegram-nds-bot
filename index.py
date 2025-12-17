import asyncio
import logging
import os
from datetime import datetime

from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import aiohttp

load_dotenv()

# ================ НАСТРОЙКИ (ИМЕНА КАК В VERCEL) ==================
BOT_TOKEN = os.getenv('bot_token', '8193790556:AAFDGDApuUz0tyEiK5I2bapp0VdUHF2X9PM')
BITRIX_WEBHOOK = os.getenv('bit_web', 'https://khakasia.bitrix24.ru/rest/10704/kohg28vjqkuyyt2x/')
CHANNEL_ID = int(os.getenv('channel_id', '-1003585038755'))
ADMIN_IDS_STR = os.getenv('admins_ids', '778115078')
ADMIN_IDS = [int(x) for x in ADMIN_IDS_STR.split(',') if x.strip()]

WEB_APP_BASE_URL = os.getenv('web_app_url', 'https://telegram-nds-bot.vercel.app')  # без /form в конце

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)


# ================ FSM ТОЛЬКО ДЛЯ АДМИНА (создание поста) ==================
class PostCreator(StatesGroup):
    waiting_post_text = State()
    waiting_media = State()
    waiting_button_text = State()


@dp.message(Command("create_post"), F.from_user.id.in_(ADMIN_IDS))
async def start_post_creator(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст поста:")
    await state.set_state(PostCreator.waiting_post_text)


@dp.message(PostCreator.waiting_post_text)
async def process_post_text(message: types.Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Текст не может быть пустым!")
        return
    await state.update_data(post_text=message.text.strip())
    await message.answer("🖼️ Отправьте фото/видео или /skip:")
    await state.set_state(PostCreator.waiting_media)


@dp.message(PostCreator.waiting_media, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(media_file_id=photo_file_id, media_type='photo')
    await message.answer("✅ Фото добавлено! Введите текст кнопки:")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media, F.video)
async def process_video(message: types.Message, state: FSMContext):
    video_file_id = message.video.file_id
    await state.update_data(media_file_id=video_file_id, media_type='video')
    await message.answer("✅ Видео добавлено! Введите текст кнопки:")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media, Command("skip"))
async def skip_media(message: types.Message, state: FSMContext):
    await state.update_data(media_file_id=None, media_type=None)
    await message.answer("⏭️ Введите текст кнопки (например: '📋 Оставить заявку'):")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media)
async def invalid_media(message: types.Message):
    await message.answer("❌ Отправьте фото/видео или /skip")


@dp.message(PostCreator.waiting_button_text)
async def create_post_with_button(message: types.Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Текст кнопки не может быть пустым!")
        return

    data = await state.get_data()
    post_text = data.get('post_text')
    button_text = message.text.strip()
    media_file_id = data.get('media_file_id')
    media_type = data.get('media_type')

    if not post_text:
        await message.answer("❌ Ошибка! Начните заново с /create_post")
        await state.clear()
        return

    # URL формы (ваш WebApp на Vercel)
    web_app_url = f"{WEB_APP_BASE_URL}/form"

    # В канале допустима только url-кнопка (web_app даёт BUTTON_TYPE_INVALID)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=web_app_url)]
        ]
    )

    try:
        if media_type == 'photo':
            sent_message = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=media_file_id,
                caption=post_text,
                reply_markup=keyboard
            )
            media_info = "📸 с фото"
        elif media_type == 'video':
            sent_message = await bot.send_video(
                chat_id=CHANNEL_ID,
                video=media_file_id,
                caption=post_text,
                reply_markup=keyboard
            )
            media_info = "🎥 с видео"
        else:
            sent_message = await bot.send_message(
                chat_id=CHANNEL_ID,
                text=post_text,
                reply_markup=keyboard
            )
            media_info = "без медиа"

        await message.answer(
            f"✅ Пост #{sent_message.message_id} опубликован {media_info}!\n\n"
            f"📝 Текст: {post_text[:50]}...\n"
            f"🔘 Кнопка (URL на форму): {button_text}"
        )
        logger.info(f"✅ Пост создан: {sent_message.message_id} ({media_info})")
    except Exception as e:
        error_msg = str(e)[:200]
        await message.answer(f"❌ Ошибка публикации: {error_msg}")
        logger.error(f"❌ Ошибка при создании поста: {e}")

    await state.clear()


# ================ FLASK: СТАТУС ==================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    }), 200


# ================ FLASK: WEB APP ФОРМА ==================
@app.route('/form', methods=['GET'])
def web_form():
    """HTML-форма, которая открывается по кнопке из канала."""
    return '''
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>Заявка НДС 2026</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f5;
      margin: 0;
      padding: 16px;
    }
    .card {
      max-width: 420px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.08);
    }
    h1 {
      font-size: 20px;
      margin-bottom: 12px;
    }
    p {
      font-size: 14px;
      color: #555;
      margin-bottom: 16px;
    }
    .field {
      margin-bottom: 14px;
    }
    label {
      display: block;
      font-size: 13px;
      margin-bottom: 4px;
      color: #555;
    }
    input {
      width: 100%;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid #ccc;
      font-size: 14px;
    }
    input:focus {
      outline: none;
      border-color: #208ae5;
      box-shadow: 0 0 0 2px rgba(32,138,229,0.2);
    }
    button {
      width: 100%;
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 8px;
      border: none;
      background: #208ae5;
      color: #fff;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled {
      background: #999;
      cursor: not-allowed;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>Заявка на консультацию НДС 2026</h1>
    <p>Оставьте контакты, и мы перезвоним в ближайшее время.</p>
    <div class="field">
      <label for="name">Имя</label>
      <input id="name" type="text" placeholder="Иван Иванов" />
    </div>
    <div class="field">
      <label for="phone">Телефон</label>
      <input id="phone" type="tel" placeholder="+7 999 123-45-67" />
    </div>
    <button id="submitBtn">Отправить заявку</button>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();

    const btn = document.getElementById('submitBtn');
    const nameInput = document.getElementById('name');
    const phoneInput = document.getElementById('phone');

    btn.addEventListener('click', async () => {
      const name = nameInput.value.trim();
      const phone = phoneInput.value.trim();

      if (!name || !phone) {
        alert('Пожалуйста, заполните имя и телефон');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Отправка...';

      try {
        const res = await fetch('/submit-lead', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, phone })
        });
        const data = await res.json();
        if (data.success) {
          alert('Заявка отправлена! Спасибо!');
          tg.close();
        } else {
          alert('Ошибка: ' + (data.error || 'неизвестная ошибка'));
          btn.disabled = false;
          btn.textContent = 'Отправить заявку';
        }
      } catch (e) {
        alert('Ошибка сети: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Отправить заявку';
      }
    });
  </script>
</body>
</html>
    '''


# ================ FLASK: ПРИЁМ ЛИДА И ОТПРАВКА В BITRIX ==================
@app.route('/submit-lead', methods=['POST'])
def submit_lead():
    """Получаем имя+телефон из формы и создаём лид в Битрикс."""
    try:
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()

        if not name or not phone:
            return jsonify({'success': False, 'error': 'Имя и телефон обязательны'}), 400

        import requests

        # ВАЖНО: BITRIX_WEBHOOK ДОЛЖЕН ЗАКАНЧИВАТЬСЯ НА /rest/.../КЛЮЧ/
        # БЕЗ crm.lead.add.json В КОНЦЕ
        url = BITRIX_WEBHOOK.rstrip('/') + '/crm.lead.add.json'

        payload = {
            'fields': {
                'TITLE': 'Заявка НДС2026 с WebApp',
                'NAME': name,
                'PHONE': [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}],
                'COMMENTS': (
                    f'Источник: Telegram WebApp (канал)\n'
                    f'Имя: {name}\n'
                    f'Телефон: {phone}\n'
                    f'Создано: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}'
                ),
                'SOURCE_ID': 'TELEGRAM_WEBAPP'
            },
            'params': {
                'REGISTER_SONET_EVENT': 'Y'
            }
        }

        r = requests.post(url, json=payload, timeout=10)
        resp_json = r.json()
        logger.info(f"Bitrix lead response: {resp_json}")

        if resp_json.get('result'):
            return jsonify({'success': True, 'lead_id': resp_json['result']}), 200
        else:
            # Пробрасываем текст ошибки наружу, чтобы её видеть
            return jsonify({
                'success': False,
                'error': resp_json.get('error'),
                'error_description': resp_json.get('error_description'),
                'raw': resp_json
            }), 500
    except Exception as e:
        logger.error(f"Ошибка submit-lead: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================ ЗАПУСК БОТА (POLLING) ===============
async def main():
    logger.info("🚀 Бот запущен в режиме polling (локально)...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    asyncio.run(main())
