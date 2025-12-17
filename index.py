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
import aiohttp
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ═══════════════════════════════════════════════════════════════
# ⚙️ НАСТРОЙКИ - ЗАМЕНИТЕ ЭТИ ЗНАЧЕНИЯ
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv('BOT_TOKEN', '8193790556:AAFDGDApuUz0tyEiK5I2bapp0VdUHF2X9PM')
BITRIX_WEBHOOK = os.getenv('BITRIX_WEBHOOK', 'https://khakasia.bitrix24.ru/rest/10704/kohg28vjqkuyyt2x/')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003585038755'))
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '778115078')
ADMIN_IDS = [int(id) for id in ADMIN_IDS_STR.split(',') if id.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://telegram-nds-bot.vercel.app')

# ═══════════════════════════════════════════════════════════════
# 🔧 ЛОГИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 🤖 AIOGRAM SETUP
# ═══════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)


# ═══════════════════════════════════════════════════════════════
# 🎯 STATES (состояния FSM)
# ═══════════════════════════════════════════════════════════════

class PostCreator(StatesGroup):
    """Состояния для создания поста"""
    waiting_post_text = State()
    waiting_media = State()
    waiting_button_text = State()


class LeadForm(StatesGroup):
    """Состояния для формы заявки"""
    waiting_name = State()
    waiting_phone = State()


# ═══════════════════════════════════════════════════════════════
# 📝 ОБРАБОТЧИК: Создание поста
# ═══════════════════════════════════════════════════════════════

@dp.message(Command("create_post"), F.from_user.id.in_(ADMIN_IDS))
async def start_post_creator(message: types.Message, state: FSMContext):
    """Начало создания поста - только для админов"""
    await message.answer(
        "📝 Введите текст поста (можно с эмодзи и форматированием):"
    )
    await state.set_state(PostCreator.waiting_post_text)


@dp.message(PostCreator.waiting_post_text)
async def process_post_text(message: types.Message, state: FSMContext):
    """Получение текста поста"""
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Текст не может быть пустым! Введите текст поста:")
        return

    await state.update_data(post_text=message.text.strip())
    await message.answer(
        "🖼️ Отправьте фото или видео (или напишите /skip для пропуска):"
    )
    await state.set_state(PostCreator.waiting_media)


@dp.message(PostCreator.waiting_media, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Получение фото"""
    photo_file_id = message.photo[-1].file_id
    await state.update_data(media_file_id=photo_file_id, media_type='photo')
    await message.answer("✅ Фото добавлено! Введите текст кнопки:")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media, F.video)
async def process_video(message: types.Message, state: FSMContext):
    """Получение видео"""
    video_file_id = message.video.file_id
    await state.update_data(media_file_id=video_file_id, media_type='video')
    await message.answer("✅ Видео добавлено! Введите текст кнопки:")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media, Command("skip"))
async def skip_media(message: types.Message, state: FSMContext):
    """Пропуск медиа"""
    await state.update_data(media_file_id=None, media_type=None)
    await message.answer("⏭️ Введите текст кнопки (например: '📞 Консультация'):")
    await state.set_state(PostCreator.waiting_button_text)


@dp.message(PostCreator.waiting_media)
async def invalid_media(message: types.Message):
    """Ошибка - неправильный тип"""
    await message.answer("❌ Отправьте фото или видео!\nИли используйте /skip для пропуска")


@dp.message(PostCreator.waiting_button_text)
async def create_post_with_button(message: types.Message, state: FSMContext):
    """Создание и публикация поста в канал"""
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Текст кнопки не может быть пустым! Введите текст:")
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

    # Создание клавиатуры с кнопкой
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data='get_consult')]
    ])

    try:
        # Публикация в зависимости от типа медиа
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
            f"🔘 Кнопка: {button_text}"
        )
        logger.info(f"✅ Пост создан: {sent_message.message_id} ({media_info})")
    except Exception as e:
        error_msg = str(e)[:100]
        await message.answer(f"❌ Ошибка публикации: {error_msg}")
        logger.error(f"❌ Ошибка при создании поста: {e}")

    await state.clear()


# ═══════════════════════════════════════════════════════════════
# 🔘 ОБРАБОТЧИК: Клик на кнопку
# ═══════════════════════════════════════════════════════════════

@dp.callback_query(F.data == 'get_consult')
async def start_lead_form(callback: types.CallbackQuery, state: FSMContext):
    """При клике на кнопку - начало формы"""
    await callback.answer()

    # Отправляем форму в личку
    await bot.send_message(
        callback.from_user.id,
        "👋 Добро пожаловать!\n\n"
        "Для консультации введите ваше имя:"
    )
    await state.set_state(LeadForm.waiting_name)


@dp.message(LeadForm.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    """Получение имени"""
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Имя не может быть пустым! Введите ваше имя:")
        return

    await state.update_data(name=message.text.strip())
    await message.answer(
        "📱 Спасибо! Теперь введите телефон для звонка:\n\n"
        "Формат: +7 999 123-45-67"
    )
    await state.set_state(LeadForm.waiting_phone)


@dp.message(LeadForm.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    """Получение телефона и создание лида"""
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Телефон не может быть пустым! Введите телефон:")
        return

    data = await state.get_data()
    name = data.get('name')
    phone = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"

    if not name:
        await message.answer("❌ Ошибка! Начните заново.")
        await state.clear()
        return

    # ✅ СОЗДАНИЕ ЛИДА В BITRIX24
    async with aiohttp.ClientSession() as session:
        payload = {
            'fields': {
                'TITLE': 'Заявка НДС2026 с ТГ-канала',
                'NAME': name,
                'PHONE': [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}],
                'COMMENTS': (
                    f'Источник: Telegram канал\n'
                    f'👤 Имя: {name}\n'
                    f'📱 Телефон: {phone}\n'
                    f'🆔 Telegram ID: {user_id}\n'
                    f'@Username: @{username}\n'
                    f'⏰ Дата: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}'
                ),
                'SOURCE_ID': 'Telegram НДС2026'
            }
        }
        try:
            async with session.post(
                    BITRIX_WEBHOOK + 'crm.lead.add.json',
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                result = await resp.json()
                if result.get('result'):
                    lead_id = result.get('result')
                    logger.info(f"✅ Лид создан в Bitrix: {lead_id}")
                    await message.answer(
                        f"✅ {name}! Спасибо за заявку.\n\n"
                        f"📞 Телефон: {phone}\n\n"
                        f"Наш менеджер перезвонит вам в течение одного часа! ☎️"
                    )
                else:
                    logger.error(f"❌ Ошибка Bitrix: {result}")
                    await message.answer(
                        "⚠️ Заявка получена, но возникла ошибка при отправке в CRM.\n"
                        "Менеджер свяжется с вами вскоре!"
                    )
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке в Bitrix: {e}")
            await message.answer(
                "⚠️ Заявка получена!\n"
                "Менеджер перезвонит вам через время."
            )

    logger.info(f"✅ Новая заявка: {name} | {phone} | ID: {user_id}")
    await state.clear()


# ═══════════════════════════════════════════════════════════════
# 🌐 FLASK ROUTES (для Vercel)
# ═══════════════════════════════════════════════════════════════

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Главный webhook для Telegram"""
    try:
        json_data = request.get_json()

        if not json_data:
            logger.warning("⚠️ Пустой webhook запрос")
            return jsonify({'ok': False}), 400

        # Создаём Update объект
        update = types.Update(**json_data)

        # Обработка обновления
        await dp.feed_update(bot, update)

        logger.info(f"✅ Webhook обработан")
        return jsonify({'ok': True}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Проверка статуса"""
    return jsonify({
        'status': 'ok',
        'bot': 'telegram-nds-bot',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    return jsonify({
        'message': '✅ Telegram NDS Bot работает!',
        'webhook_url': WEBHOOK_URL,
        'channel': CHANNEL_ID,
        'admins': len(ADMIN_IDS),
        'timestamp': datetime.now().isoformat()
    }), 200


# ═══════════════════════════════════════════════════════════════
# 🚀 ИНИЦИАЛИЗАЦИЯ WEBHOOK
# ═══════════════════════════════════════════════════════════════

async def setup_webhook():
    """Установка webhook при запуске"""
    try:
        webhook_info = await bot.get_webhook_info()

        if webhook_info.url != WEBHOOK_URL:
            await bot.set_webhook(WEBHOOK_URL)
            logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        else:
            logger.info(f"✅ Webhook уже установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка при установке webhook: {e}")


@app.before_request
async def before_request():
    """Инициализация при первом запросе"""
    if not hasattr(app, 'webhook_initialized'):
        await setup_webhook()
        app.webhook_initialized = True


# ═══════════════════════════════════════════════════════════════
# 🔌 ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    logger.info("🚀 Бот запущен в режиме webhook (Vercel)")
    app.run(host='0.0.0.0', port=8080, debug=False)
