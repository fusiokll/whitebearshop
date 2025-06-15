import subprocess
import sys
import os
import math

try:
    import requests
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
except ImportError:
    print("Установка необходимых зависимостей...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("Зависимости установлены. Перезапустите бот.")
    sys.exit(1)

import requests
import logging
import time
import asyncio
from typing import Optional, Dict, Any

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
API_KEY = os.getenv("API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
MNEMONICS = os.getenv("MNEMONICS", "").split()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Проверка наличия обязательных переменных
if not all([API_KEY, TELEGRAM_TOKEN, CRYPTOBOT_TOKEN, PHONE_NUMBER, MNEMONICS, ADMIN_CHAT_ID]):
    logger.error("Не все обязательные переменные окружения установлены!")
    missing = []
    if not API_KEY: missing.append("API_KEY")
    if not TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
    if not CRYPTOBOT_TOKEN: missing.append("CRYPTOBOT_TOKEN")
    if not PHONE_NUMBER: missing.append("PHONE_NUMBER")
    if not MNEMONICS: missing.append("MNEMONICS")
    if not ADMIN_CHAT_ID: missing.append("ADMIN_CHAT_ID")
    logger.error(f"Отсутствующие переменные: {', '.join(missing)}")
    sys.exit(1)

MAX_RETRIES = 3
RETRY_DELAY = 5
MAX_STARS = 100000

# URL изображений
MAIN_MENU_PHOTO_URL = "https://i.ibb.co/Jj1fvZ3X/Chat-GPT-Image-9-2025-20-22-00.png"
BUY_STARS_PHOTO_URL = "https://i.ibb.co/zWrKLHyN/Chat-GPT-Image-9-2025-20-20-03.png"
INVOICE_PHOTO_URL = "https://i.ibb.co/YBhRtD2q/photo-2025-06-09-23-19-53.jpg"
PROFILE_PHOTO_URL = "https://i.ibb.co/rRFd15ry/Chat-GPT-Image-9-Juni-2025-21-05-34.png"
SUPPORT_PHOTO_URL = "https://i.ibb.co/zhCxKY1n/Chat-GPT-Image-9-Juni-2025-21-12-34.png"
USERNAME_INPUT_PHOTO_URL = "https://i.ibb.co/9CsNmQ5/Chat-GPT-Image-9-Juni-2025-21-09-14.png"
CURRENCY_CHOICE_PHOTO_URL = "https://i.ibb.co/mCJsS2tJ/Chat-GPT-Image-9-2025-21-05-47.png"
PROMO_PHOTO_URL = "https://i.ibb.co/vCH6qkWf/Chat-GPT-Image-10-2025-12-28-53.png"

# Хранилище данных пользователей
user_data_store = {}

class FragmentAPIClient:
    def __init__(self, api_key: str, telegram_token: Optional[str] = None, cryptobot_token: Optional[str] = None):
        self.base_url = "https://api.fragment-api.com/v1"
        self.api_key = api_key
        self.telegram_token = telegram_token
        self.cryptobot_token = cryptobot_token
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FragmentBot/1.0"
        })
        self.auth_token: Optional[str] = None
        self.MIN_STARS = 50
        self.PRICE_PER_STAR = 1.45
        self.ton_rate = 200
        self.usdt_rate = 90
        self.last_rate_update = 0

    async def update_rates(self):
        """Обновление курсов TON/RUB и USDT/RUB"""
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network,tether&vs_currencies=rub", 
                timeout=10
            )
            data = response.json()
            
            ton_rate = data.get('the-open-network', {}).get('rub', self.ton_rate)
            usdt_rate = data.get('tether', {}).get('rub', self.usdt_rate)
            
            if ton_rate and ton_rate != self.ton_rate:
                logger.info(f"Обновлен курс TON: {self.ton_rate} -> {ton_rate} RUB")
                self.ton_rate = ton_rate
                
            if usdt_rate and usdt_rate != self.usdt_rate:
                logger.info(f"Обновлен курс USDT: {self.usdt_rate} -> {usdt_rate} RUB")
                self.usdt_rate = usdt_rate
                
            self.last_rate_update = time.time()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении курсов: {str(e)}")
            return False

    def get_ton_rate(self):
        if time.time() - self.last_rate_update > 3600:
            asyncio.create_task(self.update_rates())
        return self.ton_rate

    def get_usdt_rate(self):
        if time.time() - self.last_rate_update > 3600:
            asyncio.create_task(self.update_rates())
        return self.usdt_rate

    def authenticate(self, phone_number: str, mnemonics: list[str]) -> bool:
        endpoint = f"{self.base_url}/auth/authenticate/"
        payload = {
            "api_key": self.api_key,
            "phone_number": phone_number,
            "mnemonics": mnemonics
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Попытка аутентификации #{attempt + 1}")
                response = self.session.post(endpoint, json=payload, timeout=60)
                logger.info(f"Ответ API: {response.status_code}, {response.text}")
                
                response.raise_for_status()
                data = response.json()
                self.auth_token = data.get("token")
                
                if self.auth_token:
                    logger.info("Аутентификация успешна")
                    return True
                
                logger.error("Токен не получен в ответе")
                return False
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка аутентификации: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Повтор через {RETRY_DELAY} сек...")
                    time.sleep(RETRY_DELAY)
                    continue
                logger.error(f"Ошибка аутентификации после {MAX_RETRIES} попыток")
                return False

    def send_stars(self, username: str, quantity: int) -> Dict[str, Any]:
        if not self.auth_token:
            logger.error("Токен аутентификации отсутствует")
            return {"error": "Требуется аутентификация"}
        
        endpoint = f"{self.base_url}/order/stars/"
        
        payload = {
            "username": username,
            "quantity": quantity
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"JWT {self.auth_token}"
        }

        try:
            logger.info(f"Отправка звезд: {payload}")
            logger.debug(f"Заголовки запроса: {headers}")
            
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            logger.info(f"Ответ API: {response.status_code}, {response.text}")
            
            if response.status_code == 403:
                logger.warning("Обнаружена 403 ошибка, пробуем переаутентификацию")
                if self.authenticate(PHONE_NUMBER, MNEMONICS):
                    headers["Authorization"] = f"JWT {self.auth_token}"
                    logger.info("Повторная отправка запроса с новым токеном")
                    response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
                    logger.info(f"Ответ API после повторной аутентификации: {response.status_code}, {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                return {"success": True, "data": result}
            else:
                error_msg = f"Ошибка {response.status_code}"
                try:
                    error_data = response.json()
                    if 'detail' in error_data:
                        error_msg += f": {error_data['detail']}"
                    elif 'error' in error_data:
                        error_msg += f": {error_data['error']}"
                except:
                    error_msg += f": {response.text[:100]}"
                return {"error": error_msg}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Ошибка запроса: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    def create_cryptobot_invoice(
        self,
        stars_amount: int,
        asset: str = "TON",
        recipient: Optional[str] = None,
        description: str = "Покупка звезд",
        hidden_message: Optional[str] = None,
        paid_btn_name: Optional[str] = None,
        paid_btn_url: Optional[str] = None,
        payload: Optional[str] = None,
        allow_comments: bool = True,
        allow_anonymous: bool = True,
        discount_percent: int = 0
    ) -> Dict[str, Any]:
        if not self.cryptobot_token:
            raise ValueError("Требуется токен CryptoBot")
        
        if stars_amount < self.MIN_STARS:
            raise ValueError(f"Минимальное количество звезд для покупки: {self.MIN_STARS}")

        amount_rub = stars_amount * self.PRICE_PER_STAR * (1 - discount_percent / 100)
        
        if asset == "TON":
            amount_asset = amount_rub / self.get_ton_rate()
        elif asset == "USDT":
            amount_asset = amount_rub / self.get_usdt_rate()
        else:
            raise ValueError(f"Неподдерживаемая валюта: {asset}")
        
        if amount_asset < 0.01:
            raise ValueError(f"Сумма платежа слишком мала: {amount_asset:.6f} {asset}. Минимум 0.01 {asset}.")
        
        endpoint = "https://pay.crypt.bot/api/createInvoice"
        headers = {"Crypto-Pay-API-Token": self.cryptobot_token}
        
        formatted_amount = f"{amount_asset:.9f}".rstrip('0').rstrip('.')
        if formatted_amount == '':
            formatted_amount = '0'
        
        desc = f"{description} ({stars_amount} звезд)"
        if discount_percent > 0:
            desc += f" со скидкой {discount_percent}%"
        if recipient:
            desc += f" для @{recipient}"
            
        payload_data = {
            "asset": asset,
            "amount": formatted_amount,
            "description": desc,
            "hidden_message": hidden_message or f"Спасибо за покупку {stars_amount} звезд!" + (f" для @{recipient}" if recipient else ""),
            "paid_btn_name": paid_btn_name or "openBot",
            "paid_btn_url": paid_btn_url or "https://t.me/WhiteBearStars_bot",
            "payload": payload or f"stars_{stars_amount}",
            "allow_comments": allow_comments,
            "allow_anonymous": allow_anonymous
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Отправка запроса в CryptoBot: {payload_data}")
                response = self.session.post(endpoint, json=payload_data, headers=headers, timeout=30)
                logger.info(f"Ответ CryptoBot: {response.status_code}, {response.text}")
                
                response.raise_for_status()
                data = response.json()
                
                if not data.get('ok'):
                    error_msg = data.get('error', 'Неизвестная ошибка CryptoBot')
                    logger.error(f"Ошибка CryptoBot: {error_msg}")
                    return {"error": error_msg}
                
                return data
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Ошибка создания инвойса, повтор #{attempt+1}: {str(e)}")
                    time.sleep(RETRY_DELAY)
                    continue
                error_msg = f"Ошибка создания инвойса: {str(e)}"
                logger.error(error_msg)
                return {"error": error_msg}

    def _notify_admin(self, message: str) -> bool:
        if not self.telegram_token:
            logger.warning("Telegram токен не указан")
            return False

        endpoint = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(endpoint, json=payload, timeout=60)
                response.raise_for_status()
                return True
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Ошибка уведомления админа, повтор #{attempt+1}: {str(e)}")
                    time.sleep(RETRY_DELAY)
                    continue
                logger.error(f"Ошибка уведомления админа: {str(e)}")
                return False

class StarBot:
    def __init__(self, api_key: str, telegram_token: str, cryptobot_token: str):
        self.fragment_client = FragmentAPIClient(
            api_key=api_key,
            telegram_token=telegram_token,
            cryptobot_token=cryptobot_token
        )
        self.telegram_token = telegram_token
        self.pending_payments = {}
        self.auto_check_task = None
        self.rate_update_task = None
        
        # Словарь активных промокодов с количеством активаций
        self.promocodes = {
            "WELCOME10": {"discount": 10, "activations": 10},
            "STARS20": {"discount": 20, "activations": 10},
            "BEAR30": {"discount": 30, "activations": 5},
            "MEGA40": {"discount": 40, "activations": 3},
            "SUPER50": {"discount": 50, "activations": 3},
            "ULTRA60": {"discount": 60, "activations": 2},
            "EPIC70": {"discount": 70, "activations": 2},
            "LEGEND80": {"discount": 80, "activations": 1},
            "GOD99": {"discount": 99, "activations": 1}
        }
        
        self.processing_payments = set()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        welcome_text = (
            f"<b>Привет, {user.first_name}!</b>\n\n"
            "🌟 <b>Купить звёзды</b>\n"
            "Лучший курс, без скрытых условий\n\n"
            "💳 <b>Оплачивай, как удобно:</b> TON, USDT\n\n"
            f"1 звезда = {self.fragment_client.PRICE_PER_STAR} ₽ (~{1 / self.fragment_client.get_ton_rate() * self.fragment_client.PRICE_PER_STAR:.6f} TON)"
        )

        keyboard = [
            [InlineKeyboardButton("🛒 Купить звёзды", callback_data="buy_stars")],
            [InlineKeyboardButton("🎁 Промокод", callback_data="promo")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
            [InlineKeyboardButton("📚 Инструкция", callback_data="instructions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_photo(
                photo=MAIN_MENU_PHOTO_URL,
                caption=welcome_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            query = update.callback_query
            await query.answer()
            try:
                await query.message.delete()
            except Exception as e:
                logger.error(f"Ошибка удаления сообщения: {e}")
            await query.message.reply_photo(
                photo=MAIN_MENU_PHOTO_URL,
                caption=welcome_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

    async def show_instructions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        instructions_text = (
            "<b>📚 Инструкция по покупке звезд</b>\n\n"
            "1. Нажмите кнопку <b>🛒 Купить звёзды</b>.\n"
            "2. Выберите, для кого покупаете звёзды (для себя или для друга).\n"
            "3. Если для друга, введите его username.\n"
            "4. Выберите валюту оплаты (TON или USDT).\n"
            "5. Введите количество звезд (минимум 50).\n"
            "6. Оплатите счет в течение 15 минут.\n"
            "7. После оплаты нажмите кнопку <b>🔄 Проверить оплату</b>.\n\n"
            "<b>Как пополнить CryptoBot?</b>\n"
            "Вы можете пополнить баланс в боте @CryptoBot через криптовалютную биржу или обменник.\n"
            "Для этого:\n"
            "• Перейдите в @CryptoBot\n"
            "• Нажмите <b>Start</b>\n"
            "• Выберите <b>Кошелек</b> -> <b>Пополнить</b>\n"
            "• Выберите валюту (TON или USDT) и следуйте инструкциям.\n\n"
            "После пополнения баланса в @CryptoBot вы можете оплатить счет в нашем боте."
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=instructions_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def show_promo_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        context.user_data['state'] = 'ENTERING_PROMO'

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=PROMO_PHOTO_URL,
            caption="🎁 Введите промокод:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
        )

    async def show_buy_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        buy_text = (
            "<b>🛒 Купить звёзды</b>\n\n"
            "Выберите, кому вы хотите отправить звёзды:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🫵 Для себя", callback_data="buy_self")],
            [InlineKeyboardButton("👥 Для друга", callback_data="buy_friend")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=USERNAME_INPUT_PHOTO_URL,
            caption=buy_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        user_data = user_data_store.get(user_id, {
            'total_stars': 0,
            'transactions': []
        })
        
        transactions_text = ""
        transactions = user_data.get('transactions', [])
        if transactions:
            transactions_text = "\n\n📝 <b>История транзакций:</b>\n"
            for i, t in enumerate(reversed(transactions[-5:]), start=1):
                trans_line = f"{i}. {t['date']}: {t['stars']} звезд"
                if t.get('recipient'):
                    trans_line += f" для @{t['recipient']}"
                if t.get('promo') and t['promo'] != "без скидки":
                    trans_line += f" ({t['promo']})"
                transactions_text += trans_line + "\n"
            
            if len(transactions) > 5:
                transactions_text += f"\n... и еще {len(transactions) - 5} транзакций"
        else:
            transactions_text = "\n\n📝 У вас еще нет транзакций."
        
        active_promo = ""
        if 'promo_code' in context.user_data:
            discount = context.user_data.get('discount_percent', 0)
            active_promo = f"\n\n🎁 Активный промокод: {context.user_data['promo_code']} ({discount}% скидка)"
        
        profile_text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"🌟 Всего звезд: <b>{user_data['total_stars']}</b>"
            f"{transactions_text}"
            f"{active_promo}\n\n"
            f"🆔 ID: <code>{user_id}</code>"
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=PROFILE_PHOTO_URL,
            caption=profile_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def show_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        support_text = (
            "<b>💬 Поддержка</b>\n\n"
            "По всем вопросам обращайтесь к нашему менеджеру:\n"
            "@fusiokll\n\n"
            "Мы отвечаем в течение 15 минут с 9:00 до 23:00 по МСК"
        )

        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            [InlineKeyboardButton("📨 Написать в поддержку", url="https://t.me/fusiokll")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=SUPPORT_PHOTO_URL,
            caption=support_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def request_friend_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        context.user_data['state'] = 'ENTERING_FRIEND_USERNAME'
        
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=USERNAME_INPUT_PHOTO_URL,
            caption="✏️ Введите username друга (без @):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
        )

    async def choose_currency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        context.user_data['state'] = 'CHOOSING_CURRENCY'
        
        currency_text = (
            "<b>💱 Выберите валюту оплаты</b>\n\n"
            f"Текущий курс:\n"
            f"1 TON = {self.fragment_client.get_ton_rate():.2f} RUB\n"
            f"1 USDT = {self.fragment_client.get_usdt_rate():.2f} RUB\n\n"
            f"1 звезда = {self.fragment_client.PRICE_PER_STAR} RUB"
        )

        keyboard = [
            [InlineKeyboardButton("💎 Оплатить в TON", callback_data="currency_ton")],
            [InlineKeyboardButton("💵 Оплатить в USDT", callback_data="currency_usdt")],
            [InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=CURRENCY_CHOICE_PHOTO_URL,
            caption=currency_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    async def process_buy_stars(self, message: Message, amount: int, currency: str, recipient: Optional[str] = None, discount_percent: int = 0, promo_code: Optional[str] = None):
        try:
            sender = message.from_user
            sender_username = sender.username if sender.username else sender.first_name
            
            amount_rub = amount * self.fragment_client.PRICE_PER_STAR * (1 - discount_percent / 100)
            
            if currency == "TON":
                amount_asset = amount_rub / self.fragment_client.get_ton_rate()
            elif currency == "USDT":
                amount_asset = amount_rub / self.fragment_client.get_usdt_rate()
            
            if amount_asset < 0.01:
                min_stars = math.ceil(0.01 * (self.fragment_client.get_ton_rate() if currency == "TON" else self.fragment_client.get_usdt_rate()) 
                                      / (self.fragment_client.PRICE_PER_STAR * (1 - discount_percent / 100)))
                
                await message.reply_text(
                    f"❌ После применения скидки {discount_percent}% сумма слишком мала для оплаты.\n"
                    f"Минимальное количество звезд для вашей скидки: {min_stars}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
                return
                
            invoice = self.fragment_client.create_cryptobot_invoice(
                stars_amount=amount,
                asset=currency,
                recipient=recipient,
                discount_percent=discount_percent
            )
            
            if "error" in invoice:
                error_msg = invoice["error"]
                logger.error(f"Ошибка создания инвойса: {error_msg}")
                await message.reply_text(
                    f"❌ Ошибка при создании платежа: {error_msg}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
                return
                
            if not invoice.get('ok'):
                await message.reply_text(
                    "❌ Не удалось создать платеж. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
                return

            invoice_data = invoice['result']
            payment_id = str(invoice_data['invoice_id'])
            pay_url = invoice_data['pay_url']
            
            self.pending_payments[payment_id] = {
                'user_id': message.from_user.id,
                'sender_username': sender_username,
                'recipient': recipient,
                'stars_amount': amount,
                'currency': currency,
                'amount_rub': amount_rub,
                'amount_crypto': float(invoice_data['amount']),
                'discount_percent': discount_percent,
                'promo_code': promo_code,
                'processed': False
            }
            
            payment_text = (
                f"<b>💳 Оплата {amount} звезд</b>\n\n"
                f"<b>Сумма к оплате:</b> {invoice_data['amount']} {currency}\n"
            )
            
            if discount_percent > 0:
                payment_text += f"<b>Скидка:</b> {discount_percent}%\n"
            
            if recipient:
                payment_text += f"<b>Получатель:</b> @{recipient}\n\n"
            else:
                payment_text += "\n"
            
            payment_text += "Ссылка для оплаты действительна 15 минут. После оплаты нажмите 'Проверить оплату'."
            
            keyboard = [
                [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
                [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_{payment_id}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_photo(
                photo=INVOICE_PHOTO_URL,
                caption=payment_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке покупки: {str(e)}", exc_info=True)
            await message.reply_text(
                "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
            )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data

        if data == "main_menu":
            await self.start(update, context)
        elif data == "profile":
            await self.show_profile(update, context)
        elif data == "buy_stars":
            await self.show_buy_options(update, context)
        elif data == "support":
            await self.show_support(update, context)
        elif data == "promo":
            await self.show_promo_input(update, context)
        elif data == "instructions":
            await self.show_instructions(update, context)
        elif data.startswith("check_"):
            payment_id = data.split("_")[1]
            await self.check_payment(update, context, payment_id)
        elif data == "buy_self":
            # Сохраняем промокод при переходе между опциями
            promo_code = context.user_data.get('promo_code')
            discount_percent = context.user_data.get('discount_percent', 0)
            
            # Очищаем только данные о друге
            keys_to_remove = ['friend_username', 'recipient', 'currency', 'state']
            for key in keys_to_remove:
                if key in context.user_data:
                    del context.user_data[key]
                    
            # Восстанавливаем промокод
            if promo_code:
                context.user_data['promo_code'] = promo_code
                context.user_data['discount_percent'] = discount_percent
                
            context.user_data['recipient'] = None
            await self.choose_currency(update, context)
        elif data == "buy_friend":
            # Сохраняем промокод при переходе между опциями
            promo_code = context.user_data.get('promo_code')
            discount_percent = context.user_data.get('discount_percent', 0)
            
            # Очищаем только данные о покупке
            keys_to_remove = ['friend_username', 'recipient', 'currency', 'state']
            for key in keys_to_remove:
                if key in context.user_data:
                    del context.user_data[key]
                    
            # Восстанавливаем промокод
            if promo_code:
                context.user_data['promo_code'] = promo_code
                context.user_data['discount_percent'] = discount_percent
                
            context.user_data['state'] = 'ENTERING_FRIEND_USERNAME'
            await self.request_friend_username(update, context)
        elif data == "currency_ton":
            context.user_data['currency'] = "TON"
            context.user_data['state'] = 'ENTERING_AMOUNT'
            try:
                await query.message.delete()
            except Exception as e:
                logger.error(f"Ошибка удаления сообщения: {e}")
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BUY_STARS_PHOTO_URL,
                caption="Введите количество звезд для покупки (минимум 50):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
            )
        elif data == "currency_usdt":
            context.user_data['currency'] = "USDT"
            context.user_data['state'] = 'ENTERING_AMOUNT'
            try:
                await query.message.delete()
            except Exception as e:
                logger.error(f"Ошибка удаления сообщения: {e}")
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BUY_STARS_PHOTO_URL,
                caption="Введите количество звезд для покупки (минимум 50):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
            )

    async def check_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: str = None):
        query = update.callback_query
        await query.answer()

        if payment_id in self.processing_payments:
            await query.edit_message_caption(caption="⌛ Платеж уже проверяется. Пожалуйста, подождите...", parse_mode='HTML')
            return

        if query.message.photo:
            await query.edit_message_caption(caption="🔄 Проверяем статус платежа...", parse_mode='HTML')
        else:
            await query.edit_message_text("🔄 Проверяем статус платежа...", parse_mode='HTML')

        if not payment_id:
            payment_id = next((k for k, v in self.pending_payments.items() 
                            if v['user_id'] == query.from_user.id), None)
        
        if not payment_id:
            if query.message.photo:
                await query.edit_message_caption(
                    caption="❌ Платеж не обнаружен. Если вы оплатили, подождите 1-2 минуты и проверьте снова.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
            else:
                await query.edit_message_text(
                    "❌ Платеж не обнаружен. Если вы оплатили, подождите 1-2 минуты и проверьте снова.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
            return
        
        self.processing_payments.add(payment_id)
        try:
            endpoint = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={payment_id}"
            headers = {"Crypto-Pay-API-Token": self.fragment_client.cryptobot_token}
            
            response = requests.get(endpoint, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('ok'):
                if query.message.photo:
                    await query.edit_message_caption(
                        caption="Ошибка при проверке платежа. Попробуйте позже.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                    )
                else:
                    await query.edit_message_text(
                        "Ошибка при проверке платежа. Попробуйте позже.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                    )
                return
            
            invoice = data['result']['items'][0]
            
            status_translation = {
                'active': 'ожидает оплаты',
                'paid': 'оплачен',
                'expired': 'истек'
            }
            status = status_translation.get(invoice['status'], invoice['status'])
            
            if invoice['status'] == 'paid':
                success, message = await self._process_payment(payment_id)
                if success:
                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("👤 Профиль", callback_data="profile")]])
                else:
                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Поддержка", callback_data="support")]])
                    
                if query.message.photo:
                    await query.edit_message_caption(
                        caption=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    await query.edit_message_text(
                        message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            else:
                payment_data = self.pending_payments.get(payment_id, {})
                if not payment_data:
                    await query.edit_message_text("❌ Информация о платеже утеряна")
                    return
                    
                price_crypto = payment_data['amount_crypto']
                price_rub = payment_data['amount_rub']
                currency = payment_data['currency']
                pay_url = f"https://pay.crypt.bot/invoice/{payment_id}"
                
                payment_text = (
                    f"<b>ℹ️ Статус платежа</b>\n\n"
                    f"<b>ID платежа:</b> <code>{payment_id}</code>\n"
                    f"<b>Статус:</b> {status}\n"
                    f"<b>Сумма:</b> {price_crypto:.6f} {currency} (~{price_rub:.2f} RUB)\n"
                    f"<b>Звезд:</b> {payment_data['stars_amount']}\n"
                )
                
                if payment_data.get('discount_percent', 0) > 0:
                    payment_text += f"<b>Скидка:</b> {payment_data['discount_percent']}%\n"
                
                if payment_data['recipient']:
                    payment_text += f"<b>Получатель:</b> @{payment_data['recipient']}\n\n"
                else:
                    payment_text += "\n"
                
                if invoice['status'] == 'expired':
                    payment_text += "⚠️ <b>Счет истек!</b> Если вы хотите купить звезды, создайте новый заказ."
                    keyboard = [
                        [InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]
                    ]
                    if payment_id in self.pending_payments:
                        del self.pending_payments[payment_id]
                else:
                    payment_text += "Если вы уже оплатили, нажмите кнопку 'Проверить оплату' через 1-2 минуты."
                    keyboard = [
                        [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
                        [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_{payment_id}")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]
                    ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if query.message.photo:
                    await query.edit_message_caption(
                        caption=payment_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    await query.edit_message_text(
                        payment_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                
        except Exception as e:
            logger.error(f"Ошибка при проверке платежа: {str(e)}")
            if query.message.photo:
                await query.edit_message_caption(
                    caption="Ошибка при проверке платежа. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
            else:
                await query.edit_message_text(
                    "Ошибка при проверке платежа. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
        finally:
            if payment_id in self.processing_payments:
                self.processing_payments.remove(payment_id)

    async def _process_payment(self, payment_id: str) -> tuple:
        if payment_id not in self.pending_payments:
            return False, "Платеж не найден"
        
        payment_data = self.pending_payments[payment_id]
        
        if payment_data.get('processed', False):
            return False, "❌ Платеж уже был обработан ранее"
        
        payment_data['processed'] = True
        self.pending_payments[payment_id] = payment_data
        
        try:
            recipient_username = payment_data['recipient'] or payment_data['sender_username']
            
            result = self.fragment_client.send_stars(
                username=recipient_username,
                quantity=payment_data['stars_amount']
            )
            
            if "success" in result and result["success"]:
                user_id = payment_data['user_id']
                if user_id not in user_data_store:
                    user_data_store[user_id] = {
                        'total_stars': 0,
                        'transactions': []
                    }
                
                if not payment_data['recipient']:
                    user_data_store[user_id]['total_stars'] += payment_data['stars_amount']
                
                transaction = {
                    'stars': payment_data['stars_amount'],
                    'date': time.strftime("%Y-%m-%d %H:%M"),
                    'promo': "без скидки"
                }
                
                promo_code = payment_data.get('promo_code')
                if promo_code:
                    if promo_code in self.promocodes:
                        self.promocodes[promo_code]["activations"] -= 1
                        
                        discount_percent = payment_data.get('discount_percent', 0)
                        transaction['promo'] = f"промокод {promo_code} ({discount_percent}%)"
                        
                        if self.promocodes[promo_code]["activations"] == 0:
                            admin_msg = (
                                f"⚠️ Промокод <code>{promo_code}</code> израсходован!\n"
                                f"• Скидка: {discount_percent}%\n"
                                f"• Последняя активация: @{payment_data['sender_username']}"
                            )
                            self.fragment_client._notify_admin(admin_msg)
                
                if payment_data['recipient']:
                    transaction['recipient'] = payment_data['recipient']
                
                user_data_store[user_id]['transactions'].append(transaction)
                
                admin_msg = (
                    f"✅ Успешная покупка:\n"
                    f"• Покупатель: @{payment_data['sender_username']}\n"
                    f"• Звезд: {payment_data['stars_amount']}\n"
                )
                
                if payment_data.get('discount_percent', 0) > 0:
                    admin_msg += f"• Скидка: {payment_data['discount_percent']}% (промокод: {promo_code})\n"
                
                if payment_data['recipient']:
                    admin_msg += f"• Получатель: @{payment_data['recipient']}\n"
                
                admin_msg += (
                    f"• Сумма: {payment_data['amount_crypto']:.6f} {payment_data['currency']} (~{payment_data['amount_rub']:.2f} RUB)\n"
                    f"• Payment ID: {payment_id}"
                )
                
                self.fragment_client._notify_admin(admin_msg)
                
                del self.pending_payments[payment_id]
                
                if payment_data['recipient']:
                    user_msg = f"✅ {payment_data['stars_amount']} звезд отправлено @{payment_data['recipient']}!"
                else:
                    user_msg = f"✅ {payment_data['stars_amount']} звезд зачислено на ваш аккаунт!"
                    
                if payment_data.get('discount_percent', 0) > 0:
                    user_msg += f"\n\n🎁 Скидка по промокоду: {payment_data['discount_percent']}%"
                return True, user_msg
            else:
                error_msg = result.get('error', 'Неизвестная ошибка')
                logger.error(f"Ошибка отправки звезд: {error_msg}")
                
                admin_msg = (
                    f"⚠️ Ошибка отправки звезд:\n"
                    f"• Покупатель: @{payment_data['sender_username']}\n"
                    f"• Звезд: {payment_data['stars_amount']}\n"
                )
                
                if payment_data['recipient']:
                    admin_msg += f"• Получатель: @{payment_data['recipient']}\n"
                
                admin_msg += (
                    f"• Ошибка: {error_msg}\n"
                    f"• Payment ID: {payment_id}"
                )
                
                self.fragment_client._notify_admin(admin_msg)
                return False, f"❌ Ошибка при отправке звезд: {error_msg}"
            
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {str(e)}", exc_info=True)
            return False, f"❌ Неожиданная ошибка: {str(e)}"

    async def start_auto_check(self):
        if self.auto_check_task:
            self.auto_check_task.cancel()
            
        self.auto_check_task = asyncio.create_task(self.auto_check_payments())

    async def auto_check_payments(self):
        while True:
            try:
                logger.info("Автопроверка платежей...")
                payment_ids = list(self.pending_payments.keys())
                for payment_id in payment_ids:
                    if payment_id in self.processing_payments:
                        continue
                    await self.check_single_payment(payment_id)
            except Exception as e:
                logger.error(f"Ошибка автопроверки: {str(e)}")
            
            await asyncio.sleep(300)

    async def check_single_payment(self, payment_id: str):
        if payment_id in self.processing_payments:
            return
            
        self.processing_payments.add(payment_id)
        try:
            endpoint = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={payment_id}"
            headers = {"Crypto-Pay-API-Token": self.fragment_client.cryptobot_token}
            
            response = requests.get(endpoint, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('ok'):
                return
                
            invoice = data['result']['items'][0]
            
            if invoice['status'] == 'paid':
                await self._process_payment(payment_id)
            elif invoice['status'] == 'expired':
                if payment_id in self.pending_payments:
                    del self.pending_payments[payment_id]
        except Exception as e:
            logger.error(f"Ошибка при автоматической проверке платежа {payment_id}: {str(e)}")
        finally:
            if payment_id in self.processing_payments:
                self.processing_payments.remove(payment_id)

    async def start_rate_updater(self):
        while True:
            try:
                await self.fragment_client.update_rates()
                await asyncio.sleep(600)
            except Exception as e:
                logger.error(f"Ошибка в задаче обновления курса: {str(e)}")
                await asyncio.sleep(60)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data = context.user_data
        
        if user_data.get('state') == 'ENTERING_PROMO':
            promo = update.message.text.strip().upper()
            
            if promo in self.promocodes and self.promocodes[promo]["activations"] > 0:
                discount = self.promocodes[promo]["discount"]
                user_data['promo_code'] = promo
                user_data['discount_percent'] = discount
                
                await update.message.reply_text(
                    f"✅ Промокод активирован!\n\n"
                    f"Ваша скидка: <b>{discount}%</b>\n\n"
                    f"Скидка будет применена к вашей следующей покупке.",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Купить звёзды", callback_data="buy_stars")]])
                )
                del user_data['state']
            else:
                error_msg = "❌ Неверный промокод"
                if promo in self.promocodes and self.promocodes[promo]["activations"] <= 0:
                    error_msg = "❌ Промокод уже израсходован"
                
                await update.message.reply_text(
                    error_msg,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]])
                )
            return
        
        if user_data.get('state') == 'ENTERING_FRIEND_USERNAME':
            friend_username = update.message.text.strip()
            
            if friend_username.startswith('@'):
                friend_username = friend_username[1:]
                
            if len(friend_username) < 5:
                await update.message.reply_text(
                    "❌ Username должен содержать не менее 5 символов. Попробуйте снова:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
                return
                
            user_data['friend_username'] = friend_username
            user_data['state'] = 'CHOOSING_CURRENCY'
            
            currency_text = (
                "<b>💱 Выберите валюту оплаты</b>\n\n"
                f"Текущий курс:\n"
                f"1 TON = {self.fragment_client.get_ton_rate():.2f} RUB\n"
                f"1 USDT = {self.fragment_client.get_usdt_rate():.2f} RUB\n\n"
                f"1 звезда = {self.fragment_client.PRICE_PER_STAR} RUB"
            )

            keyboard = [
                [InlineKeyboardButton("💎 Оплатить в TON", callback_data="currency_ton")],
                [InlineKeyboardButton("💵 Оплатить в USDT", callback_data="currency_usdt")],
                [InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_photo(
                photo=CURRENCY_CHOICE_PHOTO_URL,
                caption=currency_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return

        if user_data.get('state') == 'ENTERING_AMOUNT':
            user_input = update.message.text
            try:
                amount = int(user_input)
                if amount < 50:
                    await update.message.reply_text(
                        "❌ Минимальное количество - 50 звезд. Введите другое количество:",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                    )
                    return
                elif amount > MAX_STARS:
                    await update.message.reply_text(
                        f"❌ Максимальное количество за одну покупку - {MAX_STARS} звезд. Введите другое количество:",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                    )
                    return
                
                del user_data['state']
                
                recipient = None
                if 'friend_username' in user_data:
                    recipient = user_data['friend_username']
                
                currency = user_data.get('currency', 'TON')
                
                discount_percent = user_data.get('discount_percent', 0)
                promo_code = user_data.get('promo_code', None)
                
                await self.process_buy_stars(
                    update.message, 
                    amount, 
                    currency, 
                    recipient,
                    discount_percent,
                    promo_code
                )
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Пожалуйста, введите целое число. Попробуйте снова:",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="buy_stars")]])
                )
        else:
            await update.message.reply_text(
                "Пожалуйста, используйте кнопки меню для взаимодействия с ботом.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]])
            )

def run_bot():
    api_key = API_KEY
    telegram_token = TELEGRAM_TOKEN
    cryptobot_token = CRYPTOBOT_TOKEN
    
    bot = StarBot(api_key, telegram_token, cryptobot_token)
    
    if not bot.fragment_client.authenticate(phone_number=PHONE_NUMBER, mnemonics=MNEMONICS):
        logger.error("Не удалось аутентифицироваться в Fragment API после нескольких попыток")

    application = Application.builder().token(telegram_token).build()
    
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if bot.auto_check_task is None:
        bot.auto_check_task = loop.create_task(bot.start_auto_check())
    if bot.rate_update_task is None:
        bot.rate_update_task = loop.create_task(bot.start_rate_updater())
    
    application.run_polling()

if __name__ == "__main__":
    logger.info("Запуск бота...")
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
    finally:
        logger.info("Бот завершил работу")
