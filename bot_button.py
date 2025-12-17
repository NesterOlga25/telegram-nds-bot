import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import threading

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '8193790556:AAFDGDApuUz0tyEiK5I2bapp0VdUHF2X9PM')
BITRIX_WEBHOOK = os.getenv('BITRIX_WEBHOOK', 'https://khakasia.bitrix24.ru/rest/10704/kohg28vjqkuyyt2x/')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003585038755'))
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '778115078').split(',')]
VERCEL_DOMAIN = os.getenv('VERCEL_DOMAIN', 'https://telegram-nds-bot.vercel.app')  # ✅ ДОМЕН

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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data='get_consult')]
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


@dp.callback_query(F.data == 'get_consult')
async def start_lead_form(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await bot.send_message(callback.from_user.id, "👋 Введите ваше имя:")
    await state.set_state(LeadForm.waiting_name)


@dp.message(LeadForm.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Имя не может быть пустым!")
        return

    await state.update_data(name=message.text.strip())
    await message.answer("📱 Введите телефон (+7 999 123-45-67):")
    await state.set_state(LeadForm.waiting_phone)


@dp.message(LeadForm.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if not message.text or message.text.strip() == "":
        await message.answer("❌ Телефон не может быть пустым!")
        return

    data = await state.get_data()
    name = data.get('name')
    phone = message.text.strip()

    if not name:
        await message.answer("❌ Ошибка! Начните заново.")
        await state.clear()
        return

    async with aiohttp.ClientSession() as session:
        payload = {
            'fields': {
                'TITLE': 'Заявка НДС2026 с ТГ-канала',
                'NAME': name,
                'PHONE': [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}],
                'COMMENTS': f'Источник: Telegram канал\n👤 {name}\n📱 {phone}',
                'SOURCE_ID': 'Telegram НДС2026'
            }
        }
        try:
            async with session.post(BITRIX_WEBHOOK + 'crm.lead.add.json', json=payload,
                                    timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                if result.get('result'):
                    logger.info(f"✅ Лид в Bitrix: {result.get('result')}")
        except Exception as e:
            logger.error(f"❌ Bitrix ошибка: {e}")

    await message.answer(f"✅ {name}! Спасибо за заявку.\n\n"
                         f"📱 {phone}\n\n"
                         f"Перезвоним через час! ☎️")
    await state.clear()


# ✅ WEBHOOK маршруты (для Telegram обновлений)
@app.route('/webhook', methods=['POST'])
async def webhook():
    json_data = request.get_json()
    update = types.Update(**json_data)
    await dp.feed_update(bot, update)
    return {'ok': True}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


async def main():
    # ✅ Используем WEBHOOK с доменом Vercel
    webhook_url = f"{VERCEL_DOMAIN}/webhook"
    logger.info(f"🌐 Webhook URL: {webhook_url}")

    try:
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")


if __name__ == '__main__':
    # Запуск Flask
    app.run(host='0.0.0.0', port=8080, debug=False)
