import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

if not BOT_TOKEN:
    raise ValueError("Критическая ошибка: Токен бота (BOT_TOKEN) не найден в файле .env!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

paid_users = {ADMIN_ID} if ADMIN_ID != 0 else set()
active_offers = {}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="5 Тон", callback_data="buy_5_ton")
    await message.answer("Нажми кнопку ниже", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "buy_5_ton")
async def process_buy(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="💚 Я оплатил", callback_data="check_payment")
    text = (
        "⚠️ Оплата 5 тон. Отправьте их на кошелек:\n\n"
        "`UQAQILAH9sLSZj_zm5BNY09EhWpTAXkIYHz2HTURkLZsMYtn`\n\n"
        "⚠️ В комментарии обязательно укажите ваш ID заказа: `812825178264`"
    )
    await callback.message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer()


@dp.callback_query(F.data == "check_payment")
async def notify_admin(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_name = callback.from_user.username or callback.from_user.first_name

    builder = InlineKeyboardBuilder()
    builder.button(text="Да", callback_data=f"admin_yes_{user_id}")
    builder.button(text="Нет", callback_data=f"admin_no_{user_id}")

    if ADMIN_ID == 0:
        await callback.message.answer("Ошибка: Администратор бота не настроен.")
        await callback.answer()
        return

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Оплата прошла? (От пользователя @{user_name}, ID: {user_id})",
            reply_markup=builder.as_markup()
        )
        await callback.message.answer("Запрос отправлен админу. Ожидайте.")
    except Exception as e:
        logging.error(f"Ошибка отправки админу: {e}")
        await callback.message.answer("Ошибка уведомления админа.")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_yes_"))
async def admin_confirm(callback: types.CallbackQuery):
    _, _, user_id_str = callback.data.split("_", 2)
    user_id = int(user_id_str)
    paid_users.add(user_id)
    try:
        await bot.send_message(
            chat_id=user_id,
            text="🎉 Оплата подтверждена! Функция автоматизации бизнес-чатов активирована.\n\n"
                 "Теперь вы можете писать в любом чате напрямую:\n"
                 "`_ай <Цена> <ссылка> <Валюта(г/с)>`"
        )
    except Exception:
        pass
    await callback.message.edit_text("Оплата подтверждена. Доступ предоставлен.")
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_no_"))
async def admin_decline(callback: types.CallbackQuery):
    _, _, user_id_str = callback.data.split("_", 2)
    user_id = int(user_id_str)
    try:
        await bot.send_message(chat_id=user_id, text="⚠️ Оплата не прошла, повторите попытку")
    except Exception:
        pass
    await callback.message.edit_text("Вы отклонили оплату.")
    await callback.answer()


# --- БИЗНЕС-ЧАТ: ОТПРАВКА ПРЕДЛОЖЕНИЯ ---

@dp.business_message(F.text.startswith("_ай "))
async def handle_business_automation(message: types.Message):
    user_id = message.from_user.id
    sender_username = message.from_user.username

    if user_id not in paid_users:
        return

    text = message.text.strip()
    parts = [p for p in text.split(" ") if p]

    if len(parts) < 4:
        return

    iterator = iter(parts)
    next(iterator)
    price = next(iterator)
    nft_url = next(iterator)
    currency_raw = next(iterator).lower()

    if nft_url.startswith("tg://"):
        nft_url = nft_url.replace("tg://", "/".join(["https:/", "t.me", ""]), 1)
    elif not nft_url.startswith(("http://", "https://")):
        nft_url = "/".join(["https:/", nft_url])

    if currency_raw == "с":
        currency = "⭐️"
    elif currency_raw == "г":
        currency = "GRAM"
    else:
        currency = currency_raw

    message_text = f"Пользователь предлагает вам {price} {currency} за ваш подарок: {nft_url}"

    # Комбинация ?profile&gift убирает вибрацию и сразу открывает меню подарков получателя
    if sender_username:
        gift_url = "/".join(["https:/", "t.me", f"{sender_username}?profile&gift"])
    else:
        gift_url = f"tg://user?id={user_id}"

    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Передать NFT", url=gift_url)
    builder.button(text="✅ Подтвердить", callback_data=f"req_confirm_{user_id}")
    builder.adjust(1)

    preview_options = LinkPreviewOptions(
        is_disabled=False,
        url=nft_url,
        prefer_large_media=True,
        show_above_text=False
    )

    try:
        sent_msg = await bot.send_message(
            chat_id=message.chat.id,
            text=message_text,
            reply_markup=builder.as_markup(),
            link_preview_options=preview_options,
            business_connection_id=message.business_connection_id
        )
        active_offers[user_id] = {
            "chat_id": message.chat.id,
            "message_id": sent_msg.message_id,
            "business_connection_id": message.business_connection_id,
            "nft_url": nft_url
        }
    except Exception as e:
        logging.error(f"Ошибка отправки бизнес-сообщения: {e}")
        return

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception:
        try:
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id
            )
        except Exception as del_err:
            logging.error(f"Не удалось удалить команду: {del_err}")


# --- ОБРАБОТКА НАЖАТИЯ НА "✅ Подтвердить" СОБЕСЕДНИКОМ ---

@dp.callback_query(F.data.startswith("req_confirm_"))
async def request_owner_confirmation(callback: types.CallbackQuery):
    _, _, owner_id_str = callback.data.split("_", 2)
    owner_id = int(owner_id_str)
    offer = active_offers.get(owner_id)

    if not offer:
        await callback.answer("Предложение не найдено или устарело.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✅", callback_data=f"owner_yes_{owner_id}")
    builder.button(text="❌", callback_data=f"owner_no_{owner_id}")

    try:
        await bot.send_message(
            chat_id=owner_id,
            text="Вы подтверждаете, что человек передал вам NFT?",
            reply_markup=builder.as_markup()
        )
        await callback.answer("Запрос на подтверждение отправлен. Ожидайте.", show_alert=True)
    except Exception as e:
        logging.error(f"Не удалось отправить запрос владельцу {owner_id}: {e}")
        await callback.answer("Ошибка: владелец не запустил бота в личных сообщениях.", show_alert=True)


# --- ОТВЕТ ОТПРАВИТЕЛЯ ПРЕДЛОЖЕНИЯ (✅ ИЛИ ❌ В ЛИЧКЕ БОТА) ---

@dp.callback_query(F.data.startswith("owner_yes_"))
async def owner_confirm_yes(callback: types.CallbackQuery):
    _, _, owner_id_str = callback.data.split("_", 2)
    owner_id = int(owner_id_str)
    offer = active_offers.get(owner_id)

    if not offer:
        await callback.message.edit_text("Сделка уже закрыта или не найдена.")
        await callback.answer()
        return

    try:
        await bot.send_message(
            chat_id=offer["chat_id"],
            text="Передача подтверждена, звёзды будут начислены в течение 24 часов",
            business_connection_id=offer["business_connection_id"]
        )
        await callback.message.edit_text("✅ Вы подтвердили получение NFT. Сообщение отправлено в чат.")
    except Exception as e:
        logging.error(f"Ошибка при отправке подтверждения в чат: {e}")
        await callback.message.edit_text("Ошибка отправки сообщения в бизнес-чат.")

    await callback.answer()


@dp.callback_query(F.data.startswith("owner_no_"))
async def owner_confirm_no(callback: types.CallbackQuery):
    _, _, owner_id_str = callback.data.split("_", 2)
    owner_id = int(owner_id_str)
    offer = active_offers.get(owner_id)

    if not offer:
        await callback.message.edit_text("Сделка уже закрыта или не найдена.")
        await callback.answer()
        return

    try:
        await bot.send_message(
            chat_id=offer["chat_id"],
            text="Подарок не был передан, повторите попытку",
            business_connection_id=offer["business_connection_id"]
        )
        await callback.message.edit_text("❌ Вы отклонили передачу. Сообщение отправлено в чат.")
    except Exception as e:
        logging.error(f"Ошибка при отправке отказа в чат: {e}")
        await callback.message.edit_text("Ошибка отправки сообщения в бизнес-чат.")

    await callback.answer()


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
