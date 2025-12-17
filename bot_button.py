import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки (замените или используйте переменные окружения)
BOT_TOKEN = os.getenv('BOT_TOKEN', '8193790556:AAFDGDApuUz0tyEiK5I2bapp0VdUHF2X9PM')
BITRIX_WEBHOOK = os.getenv('BITRIX_WEBHOOK', 'https://khakasia.bitrix24.ru/rest/10704/kohg28vjqkuyyt2x/')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003585038755'))
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '778115078').split(',')]
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://ВАШ_ПРОЕКТ.vercel.app')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)


class PostCreator(StatesGroup):
    waiting_post_text = State()
    waiting_media = State()
    waiting_button_text = State()


class LeadForm(StatesGroup):
    waiting_name = State()
    waiting_phone = State()


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
    await message.answer("✅ Введите текст кнопки:")
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
        await message.answer("❌ Ошибка! Начните заново")
        await state.clear()
        return

    # ✅ Кнопка с Web App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=button_text,
            web_app=WebAppInfo(url=f"{WEB_APP_URL}/form")
        )]
    ])

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

        await message.answer(f"✅ Пост #{sent_message.message_id} опубликован {media_info}!")
        logger.info(f"✅ Пост: {sent_message.message_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
        logger.error(f"Ошибка: {e}")

    await state.clear()


# ✅ Web App форма
@app.route('/form', methods=['GET'])
def web_form():
    return '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Форма заявки НДС2026</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            font-size: 24px;
            margin-bottom: 20px;
            color: #333;
        }
        .form-group {
            margin-bottom: 16px;
        }
        label {
            display: block;
            font-size: 14px;
            color: #666;
            margin-bottom: 6px;
            font-weight: 500;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            font-family: inherit;
        }
        input:focus {
            outline: none;
            border-color: #208ae5;
            box-shadow: 0 0 0 3px rgba(32, 138, 229, 0.1);
        }
        button {
            width: 100%;
            padding: 12px;
            background: #208ae5;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:active {
            background: #1a6fb3;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Заявка НДС2026</h1>
        <form id="leadForm">
            <div class="form-group">
                <label for="name">👤 Ваше имя:</label>
                <input type="text" id="name" name="name" required placeholder="Иван Иванов">
            </div>
            <div class="form-group">
                <label for="phone">📱 Телефон:</label>
                <input type="tel" id="phone" name="phone" required placeholder="+7 999 123-45-67">
            </div>
            <button type="submit" id="submitBtn">✅ Отправить заявку</button>
        </form>
    </div>

    <script>
        const form = document.getElementById('leadForm');
        const submitBtn = document.getElementById('submitBtn');
        const Telegram = window.Telegram.WebApp;

        Telegram.ready();

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const name = document.getElementById('name').value.trim();
            const phone = document.getElementById('phone').value.trim();

            if (!name || !phone) {
                alert('❌ Заполните все поля!');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = '⏳ Отправка...';

            try {
                const response = await fetch('/submit-lead', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name,
                        phone: phone,
                        user_id: Telegram.initData.user?.id || 'unknown'
                    })
                });

                const result = await response.json();

                if (result.success) {
                    alert('✅ Заявка принята! Перезвоним через час');
                    Telegram.close();
                } else {
                    alert('❌ Ошибка: ' + result.error);
                    submitBtn.disabled = false;
                    submitBtn.textContent = '✅ Отправить заявку';
                }
            } catch (error) {
                alert('❌ Ошибка сети: ' + error.message);
                submitBtn.disabled = false;
                submitBtn.textContent = '✅ Отправить заявку';
            }
        });
    </script>
</body>
</html>
    '''


# ✅ Обработка данных из формы
@app.route('/submit-lead', methods=['POST'])
def submit_lead():
    try:
        data = request.json
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        user_id = data.get('user_id', 'unknown')

        if not name or not phone:
            return jsonify({'success': False, 'error': 'Заполните все поля'}), 400

        # Создание лида в Bitrix24 (синхронно для простоты)
        try:
            import requests
            payload = {
                'fields': {
                    'TITLE': 'Заявка НДС2026 с ТГ-канала (Web App)',
                    'NAME': name,
                    'PHONE': [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}],
                    'COMMENTS': f'Источник: Telegram Web App\n👤 {name}\n📱 {phone}\n🆔 {user_id}',
                    'SOURCE_ID': 'Telegram НДС2026 (Web App)'
                }
            }
            response = requests.post(BITRIX_WEBHOOK + 'crm.lead.add.json', json=payload, timeout=10)
            result = response.json()
            logger.info(f"✅ Лид в Bitrix: {result.get('result')}")
        except Exception as e:
            logger.error(f"❌ Bitrix ошибка: {e}")

        return jsonify({'success': True, 'message': 'Лид создан'})
    except Exception as e:
        logger.error(f"Ошибка submit-lead: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


async def main():
    logger.info("🚀 Бот запущен...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")


if __name__ == '__main__':
    asyncio.run(main())
