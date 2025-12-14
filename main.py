# bot.py
import asyncio
import re
import os
import json
import html
from datetime import datetime

# --- ایمپورت‌های aiogram ---
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup 
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, KeyboardButton, ReplyKeyboardMarkup
from aiogram.client.default import DefaultBotProperties # برای رفع خطای TypeError در تعریف Bot
from aiogram.utils.markdown import markdown_decoration

# --- ایمپورت‌های محلی ---
import config 
from database import DatabaseManager

# --- پیکربندی اولیه ---
bot = Bot(
    token=config.TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN) # رفع خطای TypeError
)
dp = Dispatcher()
db = DatabaseManager()
# per-admin toggle to include deleted users in listings
admin_show_deleted = {}


async def persist_state_to_db(user_id: int, state: FSMContext) -> None:
    """Unified helper to persist current FSM state data to the database.

    This centralizes saving logic so the codebase is consistent and
    every save goes through the same path.
    """
    try:
        data = await state.get_data()
        db.save_resume_data(user_id, data)
    except Exception as e:
        db.log("ERROR", f"Failed to persist state for user {user_id}: {e}")

# --- تعاریف FSM ---
class ResumeStates(StatesGroup):
    username = State()
    full_name = State()
    study_status = State()
    degree = State()
    major = State()
    english_level = State()
    field_university = State()
    gpa = State()
    location = State()
    phone_main = State()
    phone_emergency = State()

    skills_start = State()
    skills_select_level = State()

    work_sample_upload = State()
    work_history = State()
    job_position = State()
    other_details = State()
    has_work_license = State() # State جدید برای پروانه اشتغال
    work_license_city = State() # State جدید برای شهر صدور پروانه
    confirm_resume = State()
    edit_field = State()
    edit_value = State()
    training_request = State()

    finished = State()

# --- توابع کمکی ساخت کیبورد (رفع خطای ValidationError) ---

def create_reply_keyboard(texts: list, one_time: bool = True) -> ReplyKeyboardMarkup:
    """ساخت ReplyKeyboardMarkup با تبدیل لیست رشته‌ای به KeyboardButton"""
    keyboard_rows = []
    # Arrange buttons in 2 columns per row for a compact layout
    cols = 2
    row = []
    for t in texts:
        row.append(KeyboardButton(text=t))
        if len(row) >= cols:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True, one_time_keyboard=one_time)

def get_main_keyboard(is_admin) -> ReplyKeyboardMarkup:
    # ساخت دکمه‌های اصلی: ارسال رزومه و پشتیبانی در یک ردیف، دکمه پنل ادمین در ردیف جداگانه (در صورت ادمین)
    main_btn = KeyboardButton(text=config.KEYBOARD_MAIN_TEXTS[0])
    support_btn = KeyboardButton(text=config.SUPPORT_LABEL)
    channel_btn = KeyboardButton(text=config.MOHANDES_YAR_CHANNEL_LABEL)

    keyboard_rows = [[main_btn, support_btn, channel_btn]]

    # اضافه کردن دکمه ادمین (Admin Panel) در ردیف بعدی
    if is_admin:
        admin_button = KeyboardButton(text=config.KEYBOARD_ADMIN_TEXTS[0])
        keyboard_rows.append([admin_button])

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder="منوی اصلی..."
    )


def get_skill_keyboard(is_editing: bool = False) -> InlineKeyboardMarkup:
    # این کیبورد Inline است و نیازی به تبدیل ندارد
    kb = []
    for row in config.KEYBOARD_SKILLS[:-1]:
        kb.append([InlineKeyboardButton(text=s, callback_data=f"skill_{s}") for s in row])
    
    # اگر در حالت ویرایش باشیم، دکمه "اتمام ویرایش" را نمایش می‌دهیم
    if is_editing:
        kb.append([InlineKeyboardButton(text="✅ اتمام ویرایش مهارت‌ها", callback_data="skill_edit_finish")])
    else:
        # در حالت عادی، دکمه "ادامه" نمایش داده می‌شود
        kb.append([InlineKeyboardButton(text=config.KEYBOARD_SKILLS[-1][0], callback_data="skill_continue")])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_skill_level_keyboard(skill_name) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=level, callback_data=f"level_{skill_name}_{level}")]
        for level in config.KEYBOARD_SKILL_LEVEL[0]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_english_level_keyboard() -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای برای انتخاب میزان تسلط به زبان انگلیسی"""
    kb = [
        [InlineKeyboardButton(text=level, callback_data=f"english_{level}")]
        for level in config.KEYBOARD_SKILL_LEVEL[0]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_major_keyboard() -> InlineKeyboardMarkup:
    """شیشه‌ای کردن کلیدهای انتخاب رشته (Inline keyboard)"""
    # ساخت کیبورد با چیدمان چندستونه (پیش‌فرض: 2 ستون) برای ظاهر جمع‌وجور
    kb = []
    row = []
    cols = 2
    for m in config.KEYBOARD_MAJOR_TEXTS:
        row.append(InlineKeyboardButton(text=m, callback_data=f"major_{m}"))
        if len(row) >= cols:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_study_status_keyboard() -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای برای انتخاب وضعیت تحصیلی."""
    kb = [
        [InlineKeyboardButton(text=status, callback_data=f"study_status_{status}")]
        for status in config.KEYBOARD_STUDY_STATUS_TEXTS
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_degree_keyboard() -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای برای انتخاب مقطع تحصیلی."""
    kb = []
    row = []
    for degree in config.KEYBOARD_DEGREE_TEXTS:
        row.append(InlineKeyboardButton(text=degree, callback_data=f"degree_{degree}"))
        if len(row) >= 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_consent_keyboard() -> InlineKeyboardMarkup:
    """کیبورد درخواست تایید شرایط: دو دکمه پذیرش یا عدم پذیرش به صورت شیشه‌ای (Inline)."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ شرایط را میپذیرم", callback_data="consent_accept"),
            InlineKeyboardButton(text="❌ شرایط را نمیپذیرم", callback_data="consent_decline")
        ]
    ])
    return kb


def get_skip_worksample_keyboard() -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای برای رد کردن مرحله آپلود نمونه‌کار (مرحله بعد)"""
    # Provide two actions: skip the uploads or finish uploads and continue
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="مرحله بعد", callback_data="worksample_skip"),
            InlineKeyboardButton(text="اتمام آپلود و ارسال فایل", callback_data="worksample_finish")
        ]
    ])
    return kb

def is_valid_phone(phone: str) -> bool:
    return re.fullmatch(r"09\d{9}", phone.strip())

# --- هندلر کاربر: شروع و منوی اصلی ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    # هنگام استارت، متن طولانی شرایط را نمایش بده و درخواست تایید کن
    is_admin = message.from_user.id in config.ADMIN_IDS
    await message.answer(config.START_MESSAGE, reply_markup=get_consent_keyboard())
    db.log("INFO", f"User {message.from_user.id} started bot.")

@dp.message(F.text == config.KEYBOARD_MAIN_TEXTS[0], StateFilter(None))
async def start_resume_flow(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    # ابتدا آیدی تلگرام را بپرس
    await state.set_state(ResumeStates.username)
    await message.answer(
        "**۱. آیدی تلگرام**\n"
        "لطفاً آیدی تلگرام خود را وارد کنید (مثال: @alirezaei)",
        reply_markup=types.ReplyKeyboardRemove()
    )


# --- Consent handlers ---
@dp.callback_query(F.data == "consent_accept")
async def consent_accept(callback: types.CallbackQuery, state: FSMContext) -> None:
    """اگر کاربر شرایط را پذیرفت، دکمه‌های اصلی نمایش داده می‌شود و ادامه از سر گرفته می‌شود."""
    await callback.answer()
    await state.clear()
    is_admin = callback.from_user.id in config.ADMIN_IDS
    # پاسخ به کال‌بک: ارسال پیام جدید با کیبورد اصلی
    await bot.send_message(
        callback.from_user.id,
        "مرسی؛ شرایط پذیرفته شد. اکنون می‌توانید رزومه خود را ارسال کنید.",
        reply_markup=get_main_keyboard(is_admin)
    )
    db.log("INFO", f"User {callback.from_user.id} accepted terms.")


@dp.callback_query(F.data == "consent_decline")
async def consent_decline(callback: types.CallbackQuery, state: FSMContext) -> None:
    """اگر کاربر شرایط را نپذیرفت، فرایند متوقف شده و دکمه استارت مجدد نمایش داده می‌شود."""
    await callback.answer()
    await state.clear()
    # نمایش پیام تشکر و یک دکمه استارت مجدد (ReplyKeyboard با دستور /start)
    restart_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/start")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await bot.send_message(
        callback.from_user.id,
        "متشکریم از شما. در صورت تمایل می‌توانید بعداً دوباره اقدام به ثبت اطلاعات کنید.",
        reply_markup=restart_kb
    )
    db.log("INFO", f"User {callback.from_user.id} declined terms.")


@dp.message(F.text == config.SUPPORT_LABEL)
async def support_button_handler(message: types.Message) -> None:
    """Send support chat link as an inline URL button when user presses the support reply-keyboard button."""
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="رفتن به پشتیبانی", url=config.SUPPORT_CHAT_LINK)]
        ])
        await message.answer("برای ارتباط با پشتیبانی روی دکمه زیر بزنید:", reply_markup=kb)
        db.log("INFO", f"User {message.from_user.id} requested support link.")
    except Exception as e:
        db.log("ERROR", f"Failed to send support link to {message.from_user.id}: {e}")
        await message.answer(f"ارتباط با پشتیبانی: {config.SUPPORT_CHAT_LINK}")

@dp.message(F.text == config.MOHANDES_YAR_CHANNEL_LABEL)
async def channel_button_handler(message: types.Message) -> None:
    """When user presses the channel button, send a message with an inline URL button."""
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ورود به کانال", url=config.MOHANDES_YAR_CHANNEL_LINK)]
        ])
        await message.answer("برای عضویت در کانال مهندس یار روی دکمه زیر کلیک کنید:", reply_markup=kb)
        db.log("INFO", f"User {message.from_user.id} requested channel link.")
    except Exception as e:
        db.log("ERROR", f"Failed to send channel link to {message.from_user.id}: {e}")
        # Fallback in case the inline button fails
        await message.answer(f"لینک کانال مهندس یار: {config.MOHANDES_YAR_CHANNEL_LINK}")


# --- FSM هندلرهای رزومه (استفاده از توابع جدید کیبورد) ---

@dp.message(ResumeStates.full_name)
async def process_full_name(message: types.Message, state: FSMContext) -> None:
    # انتظار برای نام و نام خانوادگی (بدون آیدی)
    text = message.text.strip()
    if not re.search(r"\S+\s+\S+", text):
        await message.answer("ورودی نامعتبر. لطفاً نام و نام خانوادگی خود را وارد کنید (مثال: علی رضایی)")
        return

    await state.update_data(
        full_name=text,
        register_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    await persist_state_to_db(message.from_user.id, state)

    # If we are editing this single field, return to edit menu
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.study_status)
    await message.answer(
        "**۲. وضعیت تحصیلی**\n"
        "لطفاً وضعیت تحصیلی خود را انتخاب کنید.",
        reply_markup=get_study_status_keyboard()
    )


@dp.message(ResumeStates.username)
async def process_username(message: types.Message, state: FSMContext) -> None:
    # انتظار برای آیدی تلگرام؛ ذخیره بدون علامت @
    txt = message.text.strip()
    m = re.fullmatch(r"@?(\w{5,32})", txt)
    if not m:
        await message.answer("آیدی نامعتبر. لطفاً آیدی تلگرام خود را به صورت @username وارد کنید (بدون فضای خالی).")
        return

    username = m.group(1)
    await state.update_data(username=username)
    await message.answer("لطفاً نام و نام خانوادگی خود را وارد کنید (مثال: علی رضایی)")
    await state.set_state(ResumeStates.full_name)
    await persist_state_to_db(message.from_user.id, state)

    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    data = await state.get_data()
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return
@dp.callback_query(F.data.startswith("study_status_"))
async def process_study_status(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    status = callback.data[len("study_status_"):]
    try:
        await callback.message.edit_text(f"✅ وضعیت تحصیلی انتخاب شد: {status}")
    except Exception:
        pass

    await state.update_data(study_status=status)
    await persist_state_to_db(callback.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(callback.message, state)
        return

    await state.set_state(ResumeStates.degree)
    await bot.send_message(
        callback.from_user.id,
        "**۳. مقطع تحصیلی**\n"
        "لطفاً مقطع تحصیلی خود را انتخاب کنید.",
        reply_markup=get_degree_keyboard()
    )

@dp.callback_query(F.data.startswith("degree_"))
async def process_degree(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    degree = callback.data[len("degree_"):]
    try:
        await callback.message.edit_text(f"✅ مقطع تحصیلی انتخاب شد: {degree}")
    except Exception:
        pass

    await state.update_data(degree=degree)
    await persist_state_to_db(callback.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(callback.message, state)
        return

    # اکنون رشته تحصیلی را از لیست انتخابی بپرس
    await state.set_state(ResumeStates.major)
    await bot.send_message(
        callback.from_user.id,
        "**۴. رشته تحصیلی**\n"
        "لطفاً رشته تحصیلی خود را انتخاب کنید.\n\n"
        "نکته: پس از انتخاب رشته، لطفاً نام دانشگاه یا مؤسسه آموزشی آخرین محل تحصیل را وارد کنید.",
        reply_markup=get_major_keyboard()
    )

# bot.py (بخش هندلرهای FSM)
@dp.message(ResumeStates.degree)
async def process_degree_invalid(message: types.Message) -> None:
    """Handle invalid input for degree."""
    await message.answer("لطفاً از دکمه‌های شیشه‌ای برای انتخاب مقطع تحصیلی استفاده کنید.")

# --- اضافه شدن هندلر گمشده: ۴. رشته تحصیلی و دانشگاه ---
@dp.message(ResumeStates.field_university)
async def process_field_university(message: types.Message, state: FSMContext) -> None:
    await state.update_data(field_university=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if user_data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.gpa)
    await message.answer(
        "**۵. معدل کل**\n"
        "لطفاً معدل کل خود را وارد کنید (فقط عدد، اعشاری مجاز است)."
    )


@dp.callback_query(F.data.startswith("major_"))
async def process_major_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """پردازش انتخاب رشته از طریق Inline keyboard و سپس درخواست نام آخرین محل تحصیل."""
    await callback.answer()
    major = callback.data[len("major_"):]
    # edit the originating message to indicate the selection and remove inline buttons
    try:
        await callback.message.edit_text(f"✅ رشته انتخاب شد: {major}")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    
    await state.update_data(major=major)
    await persist_state_to_db(callback.from_user.id, state)

    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(callback.message, state)
        return

    await state.set_state(ResumeStates.field_university)
    await bot.send_message(
        callback.from_user.id,
        "**آخرین محل تحصیل**\n" +
        "لطفاً نام دانشگاه یا مؤسسه آموزشی آخرین محل تحصیل خود را وارد کنید.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# --- اضافه شدن هندلر گمشده: ۵. معدل کل ---
@dp.message(ResumeStates.gpa)
async def process_gpa(message: types.Message, state: FSMContext) -> None:
    try:
        gpa = float(message.text)
    except ValueError:
        await message.answer("ورودی نامعتبر. لطفاً فقط یک عدد (اعشاری مجاز) وارد کنید.")
        return
        
    await state.update_data(gpa=str(gpa))
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.location)
    await message.answer(
        "**۶. محل سکونت**\n"
        "لطفاً شهر و آدرس دقیق محل سکونت خود را وارد کنید."
    )

# bot.py (فقط بخش‌های کلیدی FSM که نیاز به بازبینی/تکمیل داشتند)
# فرض بر این است که ایمپورت‌ها و پیکربندی اولیه درست هستند.

# --- توابع کمکی ساخت کیبورد (برای اطمینان از صحت) ---
# ... (توابع get_main_keyboard, create_reply_keyboard, get_skill_keyboard, get_skill_level_keyboard) ...
# ... (تابع is_valid_phone) ...


# --- FSM هندلرها (شروع از مرحله ۶ که آخرین مرحله درست‌شده بود) ---

@dp.message(ResumeStates.location)
async def process_location(message: types.Message, state: FSMContext) -> None:
    await state.update_data(location=message.text)
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.phone_main)
    await message.answer(
        "**۷. شماره تلفن همراه**\n"
        "لطفاً شماره تلفن همراه ۱۱ رقمی خود را وارد کنید (شروع با 09).",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(ResumeStates.phone_main)
async def process_phone_main(message: types.Message, state: FSMContext) -> None:
    if not is_valid_phone(message.text):
        await message.answer(
            "❌ شماره تلفن نامعتبر. لطفاً شماره ۱۱ رقمی (شروع با 09) را وارد کنید."
        )
        return
        
    await state.update_data(phone_main=message.text.strip())
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.phone_emergency)
    await message.answer(
        "**۸. شماره تماس اضطراری**\n"
        "لطفاً شماره تماس اضطراری ۱۱ رقمی را وارد کنید (شروع با 09)."
    )

@dp.message(ResumeStates.phone_emergency)
async def process_phone_emergency(message: types.Message, state: FSMContext) -> None:
    if not is_valid_phone(message.text):
        await message.answer(
            "❌ شماره تلفن نامعتبر. لطفاً شماره ۱۱ رقمی (شروع با 09) را وارد کنید."
        )
        return
        
    await state.update_data(phone_emergency=message.text.strip())
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.update_data(skills=[]) # آماده‌سازی لیست مهارت‌ها
    # رفتن به مرحله انتخاب میزان تسلط زبان انگلیسی قبل از شروع مهارت‌ها
    await state.set_state(ResumeStates.english_level)
    await message.answer(
        "**۹. میزان تسلط به زبان انگلیسی**\n"
        "لطفاً میزان تسلط خود به زبان انگلیسی را انتخاب کنید.",
        reply_markup=get_english_level_keyboard()
    )


# --- لوپ مهارت‌ها (Skill Loop Handlers) ---

@dp.callback_query(ResumeStates.skills_start, F.data.startswith("skill_") & ~F.data.endswith("_finish"))
async def process_skill_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # edit the originating message to indicate the selection and remove inline buttons
    skill_action = callback.data[len("skill_"):] # امن‌تر کردن پارس کردن callback data: بقیه رشته بعد از پیش‌وند را بگیریم

    try:
        if skill_action == "continue":
            await callback.message.edit_text("⏭️ ادامه به مرحله آپلود نمونه‌کار انتخاب شد.")
        else:
            display_skill = "سایر" if skill_action == "سایر مهارت‌ها" else skill_action
            await callback.message.edit_text(f"✅ مهارت انتخاب شد: {display_skill}")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    # امن‌تر کردن پارس کردن callback data: بقیه رشته بعد از پیش‌وند را بگیریم
    if skill_action == "continue":
        user_data = await state.get_data()
        db.save_resume_data(callback.from_user.id, user_data)
        data = await state.get_data()
        # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
        if data.get('is_editing'):
            await finish_single_edit(callback.message, state)
            return

        await state.set_state(ResumeStates.work_sample_upload)
        await bot.send_message(
            callback.from_user.id,
            "**۱۰. آپلود نمونه کار**\n"
            f"لطفاً نمونه کار خود را آپلود کنید (حداکثر **{config.MAX_FILE_SIZE_MB} مگابایت**، فرمت: PDF, DOCX, ZIP, JPG, PNG).\n"
            "**توجه**: فایل خود را به صورت سند (Document) ارسال کنید."
            ,
            reply_markup=get_skip_worksample_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    skill_name = skill_action if skill_action != "سایر مهارت‌ها" else "سایر"

    if skill_name == "سایر":
        await state.set_state(ResumeStates.skills_select_level)
        await bot.send_message(
            callback.from_user.id,
            "لطفاً نام دقیق **سایر مهارت** خود را وارد کنید."
        )
        return

    await state.set_state(ResumeStates.skills_select_level)
    await state.update_data(current_skill=skill_name)
    await bot.send_message(
        callback.from_user.id,
        f"سطح خود را در مهارت **{skill_name}** انتخاب کنید:",
        reply_markup=get_skill_level_keyboard(skill_name)
    )

@dp.message(ResumeStates.skills_select_level, ~F.text.startswith("/"))
async def process_other_skill_name(message: types.Message, state: FSMContext) -> None:
    # ثبت نام مهارت وارد شده توسط کاربر برای "سایر مهارت‌ها"
    skill_name = message.text.strip()
    await state.update_data(current_skill=skill_name)
    
    await message.answer(
        f"سطح خود را در مهارت **{skill_name}** انتخاب کنید:",
        reply_markup=get_skill_level_keyboard(skill_name)
    )

@dp.callback_query(ResumeStates.skills_select_level, F.data.startswith("level_"))
async def process_skill_level_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # edit the originating message to show selected level and remove inline buttons
    try:
        # we'll attempt to show a compact confirmation on the source message
        payload_preview = callback.data[len("level_"):]
        skill_name_preview, _, level_preview = payload_preview.rpartition('_')

        if not level_preview:
            await callback.message.edit_reply_markup(reply_markup=None)
        else:
            await callback.message.edit_text(f"✅ سطح {level_preview} برای مهارت {skill_name_preview} انتخاب شد.")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    # قالب: level_{skill_name}_{level} — برای اطمینان، از rpartition روی آخرین '_' استفاده می‌کنیم
    payload = callback.data[len("level_"):]
    skill_name, sep, skill_level = payload.rpartition('_')
    if not sep:
        # در صورتی که فرمت غیرمنتظره باشد، یک پاسخ خطا بده
        await bot.send_message(callback.from_user.id, "خطا در پردازش سطح مهارت. لطفاً دوباره تلاش کنید.")
        await state.set_state(ResumeStates.skills_start)
        return
    data = await state.get_data()
    
    # اگر از دکمه Inline انتخاب شده، نام مهارت همان skill_name است
    final_skill_name = skill_name
    
    # اگر از طریق input "سایر" وارد شده باشد، نام مهارت در current_skill است
    if skill_name not in config.SKILLS_LIST and data.get('current_skill'):
        final_skill_name = data['current_skill']

    if not final_skill_name:
        await bot.send_message(callback.from_user.id, "خطا در ثبت مهارت. لطفاً دوباره تلاش کنید.", reply_markup=get_skill_keyboard())
        await state.set_state(ResumeStates.skills_start)
        return

    # حذف مهارت قدیمی با همین نام و افزودن مهارت جدید
    current_skills = data.get('skills', [])
    new_skills = [s for s in current_skills if s['name'] != final_skill_name]
    new_skills.append({"name": final_skill_name, "level": skill_level})
    
    await state.update_data(skills=new_skills, current_skill=None)
    await state.set_state(ResumeStates.skills_start)
    
    skills_text = "\n".join([f"- **{s['name']}**: {s['level']}" for s in new_skills])
    
    await persist_state_to_db(callback.from_user.id, state)
    await bot.send_message(
        callback.from_user.id,
        f"مهارت **{final_skill_name}** با سطح **{skill_level}** ثبت شد.\n"
        "**مهارت‌های ثبت‌شده تا کنون:**\n"
        f"{skills_text}",
        reply_markup=get_skill_keyboard(is_editing=data.get('is_editing', False))
    )


@dp.callback_query(F.data.startswith("english_"))
async def process_english_level(callback: types.CallbackQuery, state: FSMContext) -> None:
    """پردازش انتخاب میزان تسلط انگلیسی و ادامه به مرحله مهارت‌ها"""
    await callback.answer()
    level = callback.data[len("english_"):]
    # edit source message to indicate chosen english level and remove inline buttons
    try:
        await callback.message.edit_text(f"✅ سطح زبان انگلیسی انتخاب شد: {level}")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await state.update_data(english_level=level)
    await persist_state_to_db(callback.from_user.id, state)

    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(callback.message, state)
        return

    await state.set_state(ResumeStates.skills_start)
    await bot.send_message(
        callback.from_user.id,
        "**۱۰. مهارت‌های نرم‌افزاری**\n"
        "لطفاً مهارت‌های خود را از لیست زیر انتخاب کنید و سپس سطح خود را مشخص نمایید.\n"
        "پس از اتمام، روی **ادامه به مرحله بعد** کلیک کنید.",
        reply_markup=get_skill_keyboard() # در حالت عادی، دکمه "ادامه" نمایش داده می‌شود
    )


# --- مرحله ۱۰: آپلود نمونه کار ---

@dp.message(ResumeStates.work_sample_upload, F.document | F.photo)
async def process_work_sample(message: types.Message, state: FSMContext) -> None:
    # ممکن است کاربر فایل ارسال کند یا عکس؛ برای هر دو حالت سازگار رفتار کنیم
    file_info = message.document if message.document else (message.photo[-1] if message.photo else None)
    if not file_info:
        await message.answer("فایلی دریافت نشد. لطفاً فایل را به صورت Document یا Photo ارسال کنید.")
        return

    file_size = getattr(file_info, 'file_size', None)
    if file_size and file_size > config.MAX_FILE_SIZE_BYTES:
        await message.answer(
            f"❌ حجم فایل ارسالی ({round(file_info.file_size / 1024 / 1024, 2)} مگابایت) بیشتر از حداکثر مجاز (**{config.MAX_FILE_SIZE_MB} مگابایت**) است. لطفاً فایل دیگری ارسال کنید."
        )
        return

    timestamp = int(datetime.now().timestamp())
    # ممکن است photo فاقد file_name باشد؛ در اینصورت پسوند پیش‌فرض .jpg استفاده می‌کنیم
    filename = getattr(file_info, 'file_name', None)
    if not filename:
        file_extension = '.jpg' if message.photo else os.path.splitext(filename or 'file')[1]
    else:
        file_extension = os.path.splitext(filename)[1]
    # create per-user uploads folder using user_id and sanitized full name
    data = await state.get_data()
    full_name = data.get('full_name') or str(message.from_user.id)
    # sanitize folder name
    safe_name = re.sub(r'[<>:"/\\|?*]', '', full_name)
    safe_name = safe_name.replace(' ', '_')[:50]
    user_folder = f"{message.from_user.id}_{safe_name}"
    user_dir = os.path.join(config.UPLOADS_DIR, user_folder)
    os.makedirs(user_dir, exist_ok=True)
    save_path = os.path.join(user_dir, f"resume_{message.from_user.id}_{timestamp}{file_extension}")

    try:
        file = await bot.get_file(file_info.file_id)
        await bot.download_file(file.file_path, save_path)

        # store in per-user uploaded_files list
        data = await state.get_data()
        uploaded = data.get('uploaded_files', []) or []
        uploaded.append(save_path)
        await state.update_data(uploaded_files=uploaded, file_path=save_path)
        await persist_state_to_db(message.from_user.id, state)
        db.log("INFO", f"User {message.from_user.id} uploaded file to: {save_path}")

        # remain in the same state so user can upload more files; present finish/skip keyboard
        await message.answer(
            "✅ فایل با موفقیت آپلود شد. می‌توانید فایل دیگری ارسال کنید یا روی 'اتمام آپلود و ارسال فایل' بزنید.",
            reply_markup=get_skip_worksample_keyboard()
        )
        await state.set_state(ResumeStates.work_sample_upload)

    except Exception as e:
        db.log("ERROR", f"File download failed for user {message.from_user.id}: {e}")
        await message.answer("❌ خطایی در آپلود فایل رخ داد. لطفاً دوباره تلاش کنید.")
        await state.set_state(ResumeStates.work_sample_upload)


@dp.callback_query(F.data == "worksample_skip")
async def worksample_skip_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """پردازش دکمه 'مرحله بعد' در صفحه آپلود نمونه‌کار برای عبور از این مرحله."""
    await callback.answer()
    # edit source message to indicate the step was skipped and remove inline buttons
    try:
        await callback.message.edit_text("⏭️ مرحله آپلود نمونه‌کار نادیده گرفته شد.")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await state.set_state(ResumeStates.work_history)
    db.log("INFO", f"User {callback.from_user.id} skipped work sample upload.")
    await bot.send_message(
        callback.from_user.id,
        "**۱۱. سابقه کار**\n" + "آیا سابقه کار مرتبط دارید؟",
        reply_markup=create_reply_keyboard(config.KEYBOARD_WORK_HISTORY_TEXTS)
    )


@dp.callback_query(F.data == "worksample_finish")
async def worksample_finish_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User finished uploading files and wants to continue the flow."""
    await callback.answer()
    # edit source message to indicate uploads finished and remove inline buttons
    try:
        await callback.message.edit_text(f"✅ آپلودها تکمیل شد. تعداد فایل‌ها: {len(uploaded)}")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    data = await state.get_data()
    uploaded = data.get('uploaded_files', []) or []
    db.log("INFO", f"User {callback.from_user.id} finished uploads. {len(uploaded)} files saved.")
    await state.set_state(ResumeStates.work_history)
    await bot.send_message(
        callback.from_user.id,
        "**۱۱. سابقه کار**\n" + "آیا سابقه کار مرتبط دارید؟",
        reply_markup=create_reply_keyboard(config.KEYBOARD_WORK_HISTORY_TEXTS)
    )

@dp.message(ResumeStates.work_sample_upload)
async def process_work_sample_invalid(message: types.Message) -> None:
    await message.answer(
        "ورودی نامعتبر. لطفاً نمونه کار خود را به صورت **فایل** (Document/Photo) ارسال کنید."
    )

# --- مرحله ۱۱ تا ۱۴ (سابقه کار، جایگاه شغلی، توضیحات، آموزش) ---

@dp.message(ResumeStates.work_history, F.text == "دارم")
async def process_work_history_yes(message: types.Message, state: FSMContext) -> None:
    await state.update_data(work_history="دارم")
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.job_position) 
    await message.answer(
        "**۱۱. سابقه کار (ادامه)**\n"
        "لطفاً سابقه کاری خود را با جزئیات شرح دهید (نام شرکت‌ها، سمت، مدت زمان).",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(ResumeStates.work_history, F.text == "ندارم")
async def process_work_history_no(message: types.Message, state: FSMContext) -> None:
    await state.update_data(work_history="ندارم")
    await persist_state_to_db(message.from_user.id, state)
    data = await state.get_data()
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.job_position)
    await message.answer(
        "**۱۲. جایگاه شغلی طبق توانایی شما**\n"
        "لطفاً جایگاه مدنظر خود را انتخاب کنید.",
        reply_markup=create_reply_keyboard(config.KEYBOARD_JOB_POSITION_TEXTS)
    )

@dp.message(ResumeStates.job_position, ~F.text.in_(config.KEYBOARD_JOB_POSITION_TEXTS))
async def process_work_history_details(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    # اگر سابقه کار 'دارم' بوده، این پیام به عنوان شرح سابقه در نظر گرفته می‌شود
    if data.get('work_history') == "دارم":
        await state.update_data(work_history=f"دارم: {message.text}")
        await persist_state_to_db(message.from_user.id, state)
        
        await state.set_state(ResumeStates.job_position)
        await message.answer(
            "**۱۲. جایگاه شغلی طبق توانایی شما**\n"
            "لطفاً جایگاه مدنظر خود را انتخاب کنید.",
            reply_markup=create_reply_keyboard(config.KEYBOARD_JOB_POSITION_TEXTS),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    await message.answer("لطفاً از دکمه‌های تعیین شده استفاده کنید.")

@dp.message(ResumeStates.job_position, F.text.in_(config.KEYBOARD_JOB_POSITION_TEXTS))
async def process_job_position(message: types.Message, state: FSMContext) -> None:
    await state.update_data(job_position=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if user_data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    await state.set_state(ResumeStates.other_details)
    await message.answer(
        "**۱۳. توضیحات دیگر**\n"
        "اگر توضیح دیگری دارید که فکر می‌کنید می‌تواند در پذیرش شما موثر باشد، وارد کنید (اختیاری).",
        reply_markup=create_reply_keyboard(["رد شدن"], one_time=True)
    )

@dp.message(ResumeStates.other_details)
async def process_other_details(message: types.Message, state: FSMContext) -> None:
    # Allow user to skip this optional step
    if message.text.strip() == "رد شدن":
        await state.update_data(other_details=None)
        user_data = await state.get_data()
        db.save_resume_data(message.from_user.id, user_data)
        # رفتن به مرحله جدید: پروانه اشتغال
        await state.set_state(ResumeStates.has_work_license)
        await message.answer(
            "**۱۵. پروانه اشتغال (اختیاری)**\n"
            "آیا پروانه اشتغال به کار سازمان نظام مهندسی ساختمان دارید؟",
            reply_markup=create_reply_keyboard(["بله", "خیر"]) 
        )
        return

    await state.update_data(other_details=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    if user_data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    # مسیر جدید: سؤال در مورد پروانه اشتغال
    await state.set_state(ResumeStates.has_work_license)
    await message.answer(
        "**۱۵. پروانه اشتغال (اختیاری)**\n"
        "آیا پروانه اشتغال به کار سازمان نظام مهندسی ساختمان دارید؟",
        reply_markup=create_reply_keyboard(["بله", "خیر"]) 
    )

# --- هندلرهای جدید برای پروانه اشتغال ---

@dp.message(ResumeStates.has_work_license, F.text.in_(["بله", "خیر"]))
async def process_has_work_license(message: types.Message, state: FSMContext) -> None:
    if message.text == "بله":
        await state.update_data(has_work_license="بله")
        await state.set_state(ResumeStates.work_license_city)
        await message.answer("لطفاً شهر یا محل صدور پروانه را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        return

    # اگر پاسخ "خیر" بود یا در حال ویرایش بودیم و "خیر" انتخاب شد
    await state.update_data(has_work_license="خیر", work_license_city=None) # شهر را پاک می‌کنیم
    await persist_state_to_db(message.from_user.id, state)

    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    data = await state.get_data()
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    # در غیر این صورت، به مرحله بعد (درخواست آموزش) می‌رویم
    await state.set_state(ResumeStates.training_request)
    await message.answer(
        "**۱۴. درخواست آموزش**\n"
        "آیا تمایل به شرکت در دوره‌های آموزشی مرتبط دارید؟",
        reply_markup=create_reply_keyboard(config.KEYBOARD_TRAINING_REQUEST_TEXTS)
    )
@dp.message(ResumeStates.work_license_city)
async def process_work_license_city(message: types.Message, state: FSMContext) -> None:
    await state.update_data(work_license_city=message.text)
    await persist_state_to_db(message.from_user.id, state)
    # بعد از عضویت، به سوال درخواست آموزش می‌رویم
    await state.set_state(ResumeStates.training_request)
    await message.answer(
        "**۱۴. درخواست آموزش**\n"
        "آیا تمایل به شرکت در دوره‌های آموزشی مرتبط دارید؟",
        reply_markup=create_reply_keyboard(config.KEYBOARD_TRAINING_REQUEST_TEXTS)
    )

    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    data = await state.get_data()
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و ارسال", callback_data="confirm_send"),
            InlineKeyboardButton(text="✏️ ویرایش", callback_data="edit_resume")
        ]
    ])


async def finish_single_edit(message: types.Message, state: FSMContext) -> None:
    """Helper: پس از ویرایش یک فیلد، به منوی انتخاب فیلد بازمی‌گردد."""
    try:
        # پاک کردن فلگ‌ها و بازگشت به منوی ویرایش
        await state.update_data(is_editing=True, edit_field_name=None)
        await state.set_state(ResumeStates.edit_field)
        await message.answer("✅ ویرایش انجام شد. برای ویرایش فیلد دیگر، آن را انتخاب کنید یا روی 'تایید ویرایش' بزنید.", reply_markup=get_edit_fields_keyboard())
    except Exception as e:
        db.log("ERROR", f"finish_single_edit failed: {e}")


def get_edit_fields_keyboard() -> ReplyKeyboardMarkup:
    # Present Persian labels to the user using config.FIELD_LABELS
    labels = []
    for key, label in config.FIELD_LABELS.items():
        if key in ("register_date", "file_path"):
            continue
        labels.append((key, label))

    keyboard_rows = []
    cols = 2
    row = []
    for _, label in labels:
        row.append(KeyboardButton(text=label))
        if len(row) >= cols:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    # add a confirm-edit button next to cancel so user can finish editing
    keyboard_rows.append([
        KeyboardButton(text="تایید ویرایش"),
        KeyboardButton(text="انصراف")
    ])
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True, one_time_keyboard=True)


@dp.message(ResumeStates.training_request, F.text.in_(config.KEYBOARD_TRAINING_REQUEST_TEXTS))
async def process_training_request(message: types.Message, state: FSMContext) -> None:
    await state.update_data(training_request=message.text)
    await persist_state_to_db(message.from_user.id, state)

    # اگر در حال ویرایش هستیم، به منوی ویرایش برمی‌گردیم
    data = await state.get_data()
    if data.get('is_editing'):
        await finish_single_edit(message, state)
        return

    user_data = await state.get_data()
    user_data['user_id'] = message.from_user.id

    # نشان دادن پیش‌نمایش رزومه و درخواست تایید از کاربر
    await state.set_state(ResumeStates.confirm_resume)
    text = format_resume_data(user_data)
    await message.answer("لطفاً رزومه خود را بررسی کنید و در صورت صحت آن را ارسال یا ویرایش نمایید:")
    await message.answer(text, reply_markup=get_confirmation_keyboard(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "confirm_send")
async def callback_confirm_send(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # edit source confirmation message so buttons are not ambiguous
    try:
        await callback.message.edit_text("✅ رزومه تایید و ارسال شد. دکمه‌ها غیرفعال شدند.")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    user_id = callback.from_user.id
    user_data = await state.get_data()
    user_data['user_id'] = user_id
    await persist_state_to_db(user_id, state)

    # notify admins
    await notify_admin(user_data)
    db.log("SUCCESS", f"Resume confirmed and sent by User ID: {user_id}")

    await bot.send_message(user_id, config.SUCCESS_MESSAGE, reply_markup=get_main_keyboard(user_id in config.ADMIN_IDS))
    await state.clear()


@dp.callback_query(F.data == "edit_resume")
async def callback_edit_resume(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # edit the confirmation message to indicate the user chose to edit
    try:
        await callback.message.edit_text("✏️ کاربر در حال ویرایش رزومه است. دکمه‌ها غیرفعال شدند.")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    # فلگ ویرایش را برای شروع فرآیند ویرایش تنظیم می‌کنیم
    await state.update_data(is_editing=True)
    await state.set_state(ResumeStates.edit_field)
    await bot.send_message(callback.from_user.id, "لطفاً فیلد موردنظر برای ویرایش را انتخاب کنید:", reply_markup=get_edit_fields_keyboard())


@dp.message(ResumeStates.edit_field)
async def handle_edit_field(message: types.Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text == "انصراف":
        # بازگشت به نمایش پیش‌نمایش
        data = await state.get_data()
        await state.set_state(ResumeStates.confirm_resume)
        await message.answer("ویرایش لغو شد. پیش‌نمایش رزومه را بررسی کنید:")
        await message.answer(format_resume_data(data), reply_markup=get_confirmation_keyboard(), parse_mode=ParseMode.HTML)
        return

    if text == "تایید ویرایش":
        # Finalize edits and show profile/preview to the user
        await persist_state_to_db(message.from_user.id, state)
        await state.update_data(is_editing=None, edit_field_name=None) # پاک کردن فلگ‌ها
        user_data = await state.get_data()
        user_data['user_id'] = message.from_user.id
        await state.set_state(ResumeStates.confirm_resume)
        await message.answer("ویرایش‌ها ذخیره شد. می‌توانید مشخصات خود را بررسی کنید:")
        await message.answer(format_resume_data(user_data), reply_markup=get_confirmation_keyboard(), parse_mode=ParseMode.HTML)
        return

    # Map Persian label back to internal field key
    selected_key = None
    for key, label in config.FIELD_LABELS.items():
        if label == text:
            selected_key = key
            break

    if not selected_key:
        await message.answer("فیلد نامعتبر. لطفاً یکی از فیلدهای نمایش‌داده‌شده را انتخاب کنید.")
        return

    await state.update_data(edit_field_name=selected_key)

    # --- منطق اختصاصی برای ویرایش مهارت‌ها ---
    if selected_key == 'skills':
        await state.set_state(ResumeStates.skills_start)
        data = await state.get_data()
        current_skills = data.get('skills', [])
        
        # نمایش مهارت‌های فعلی به کاربر
        if isinstance(current_skills, list) and current_skills:
            skills_text = "\n".join([f"- **{s['name']}**: {s['level']}" for s in current_skills])
            await message.answer(f"**مهارت‌های فعلی شما:**\n{skills_text}\n\nبرای ویرایش، مهارت جدیدی اضافه کنید یا مهارت موجود را با سطح جدید انتخاب کنید. در پایان روی 'اتمام ویرایش مهارت‌ها' بزنید.", reply_markup=get_skill_keyboard(is_editing=True))
        else:
            await message.answer("شما در حال حاضر مهارتی ثبت نکرده‌اید. مهارت‌های خود را انتخاب کنید و در پایان روی 'اتمام ویرایش مهارت‌ها' بزنید.", reply_markup=get_skill_keyboard(is_editing=True))
        return
    # --- پایان منطق اختصاصی مهارت‌ها ---


    # Refactor: Use a dispatch dictionary to avoid long if/elif chains
    # This makes the code cleaner, more maintainable, and easier to extend.
    EDIT_DISPATCH = {
        'full_name': (ResumeStates.full_name, "لطفاً نام و نام خانوادگی خود را وارد کنید (مثال: علی رضایی)", types.ReplyKeyboardRemove()),
        'username': (ResumeStates.username, "لطفاً آیدی تلگرام خود را وارد کنید (مثال: @alirezaei)", types.ReplyKeyboardRemove()),
        'study_status': (ResumeStates.study_status, "لطفاً وضعیت تحصیلی خود را انتخاب کنید.", get_study_status_keyboard()),
        'degree': (ResumeStates.degree, "لطفاً مقطع تحصیلی خود را انتخاب کنید.", get_degree_keyboard()),
        'major': (ResumeStates.major, "لطفاً رشته تحصیلی خود را انتخاب کنید.", get_major_keyboard()),
        'field_university': (ResumeStates.field_university, "لطفاً نام دانشگاه یا مؤسسه آموزشی آخرین محل تحصیل خود را وارد کنید:", types.ReplyKeyboardRemove()),
        'gpa': (ResumeStates.gpa, "لطفاً معدل کل خود را وارد کنید (فقط عدد، اعشاری مجاز است).", types.ReplyKeyboardRemove()),
        'location': (ResumeStates.location, "لطفاً شهر و آدرس دقیق محل سکونت خود را وارد کنید:", types.ReplyKeyboardRemove()),
        'phone_main': (ResumeStates.phone_main, "لطفاً شماره تلفن همراه ۱۱ رقمی خود را وارد کنید (شروع با 09).", types.ReplyKeyboardRemove()),
        'phone_emergency': (ResumeStates.phone_emergency, "لطفاً شماره تماس اضطراری ۱۱ رقمی را وارد کنید (شروع با 09).", types.ReplyKeyboardRemove()),
        'english_level': (ResumeStates.english_level, "لطفاً میزان تسلط خود به زبان انگلیسی را انتخاب کنید:", get_english_level_keyboard()),
        'work_history': (ResumeStates.work_history, "آیا سابقه کار مرتبط دارید؟", create_reply_keyboard(config.KEYBOARD_WORK_HISTORY_TEXTS)),
        'job_position': (ResumeStates.job_position, "لطفاً جایگاه شغلی مدنظر خود را انتخاب کنید.", create_reply_keyboard(config.KEYBOARD_JOB_POSITION_TEXTS)),
        'other_details': (ResumeStates.other_details, "در صورت داشتن توضیحات دیگر، لطفاً وارد کنید:", types.ReplyKeyboardRemove()),
        'training_request': (ResumeStates.training_request, "آیا تمایل به شرکت در دوره‌های آموزشی مرتبط دارید؟", create_reply_keyboard(config.KEYBOARD_TRAINING_REQUEST_TEXTS)),        
        'has_work_license': (ResumeStates.has_work_license, "آیا پروانه اشتغال به کار سازمان نظام مهندسی ساختمان دارید؟", create_reply_keyboard(["بله", "خیر"])),
        'work_license_city': (ResumeStates.work_license_city, "لطفاً شهر یا محل صدور پروانه را وارد کنید:", types.ReplyKeyboardRemove()),
    }

    if selected_key in EDIT_DISPATCH:
        target_state, prompt_text, reply_markup = EDIT_DISPATCH[selected_key]
        await state.set_state(target_state)
        await message.answer(prompt_text, reply_markup=reply_markup)
    else:
        # Fallback for fields not in the dispatch map (e.g., skills)
        await state.set_state(ResumeStates.edit_value)
        await message.answer(f"لطفاً مقدار جدید برای فیلد **{text}** را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())


@dp.callback_query(F.data == "skill_edit_finish")
async def callback_skill_edit_finish(callback: types.CallbackQuery, state: FSMContext) -> None:
    """هنگامی که کاربر در حالت ویرایش، دکمه اتمام ویرایش مهارت‌ها را می‌زند."""
    await callback.answer()
    await finish_single_edit(callback.message, state)


@dp.message(ResumeStates.edit_value)
async def handle_edit_value(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get('edit_field_name')
    if not field:
        await message.answer("خطا: فیلدی برای ویرایش انتخاب نشده است. از ابتدا تلاش کنید.")
        await state.set_state(ResumeStates.confirm_resume)
        return

    new_value = message.text
    # به‌روزرسانی مقدار فیلد در state
    await state.update_data(**{field: new_value})
    await persist_state_to_db(message.from_user.id, state)

    # بازگشت به منوی ویرایش
    await finish_single_edit(message, state)

# ... (ادامه کد: توابع notify_admin و هندلرهای ادمین) ...
@dp.message(F.text == "🏠 منوی اصلی")
async def admin_back_to_main(message: types.Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await message.answer("بازگشت به منوی اصلی.", reply_markup=get_main_keyboard(True))

# ... (بقیه هندلرهای ادمین بدون نیاز به تغییر ساختار کیبورد) ...

class AdminStates(StatesGroup):
    search_user = State()
    list_users = State()
    view_user = State()
    edit_select_field = State()
    edit_enter_value = State()
    delete_confirm = State()
    block_unblock = State()
    
# --- توابع کمکی ساخت کیبورد ---

def create_reply_keyboard(texts: list, one_time: bool = False) -> ReplyKeyboardMarkup:
    """ساخت ReplyKeyboardMarkup با تبدیل لیست رشته‌ای به KeyboardButton"""
    keyboard_rows = []
    cols = 2
    row = []
    for t in texts:
        row.append(KeyboardButton(text=t))
        if len(row) >= cols:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True, one_time_keyboard=one_time)

def get_admin_main_keyboard() -> ReplyKeyboardMarkup:
    """منوی اصلی پنل ادمین"""
    # toggle label based on per-admin setting if available
    keyboard_rows = []
    keyboard_rows.append([KeyboardButton(text="📋 لیست کاربران"), KeyboardButton(text="🔎 جستجوی کاربر")])
    keyboard_rows.append([KeyboardButton(text="📊 آمار کلی"), KeyboardButton(text="📤 دریافت اکسل")])
    keyboard_rows.append([KeyboardButton(text="📥 پشتیبان‌گیری"), KeyboardButton(text="📄 مشاهده لاگ")])
    # Add toggle button placeholder; actual label is handled by a dedicated handler
    keyboard_rows.append([KeyboardButton(text="🔁 نمایش حذف‌شده‌ها"), KeyboardButton(text="🏠 منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_user_actions_keyboard(user_id: int, is_blocked: bool) -> ReplyKeyboardMarkup:
    """کیبورد اقدامات ادمین روی کاربر خاص"""
    block_status = "✅ آنبلاک" if is_blocked else "🚫 بلاک"
    keyboard_rows = [
        [KeyboardButton(text="✏️ ویرایش اطلاعات"), KeyboardButton(text="🗑️ حذف کاربر"), KeyboardButton(text="📂 دریافت نمونه کار")],
        [KeyboardButton(text=block_status)],
        [KeyboardButton(text="🔙 بازگشت به جستجو")],
        [KeyboardButton(text="بازگشت به صفحه اصلی")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_user_fields_keyboard():
    """کیبورد فیلدهای قابل ویرایش"""
    # Build an edit keyboard using Persian labels from config.FIELD_LABELS
    labels = []
    for key, label in config.FIELD_LABELS.items():
        if key in ("register_date", "file_path"):
            continue
        labels.append((key, label))

    keyboard_rows = []
    cols = 2
    row = []
    for _, label in labels:
        row.append(KeyboardButton(text=label))
        if len(row) >= cols:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    # add confirm and cancel buttons similar to user edit menu
    keyboard_rows.append([KeyboardButton(text="تایید ویرایش"), KeyboardButton(text="انصراف")])

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True, one_time_keyboard=True)


def is_valid_phone(phone: str) -> bool:
    return re.fullmatch(r"09\d{9}", phone.strip())

def format_resume_data(data: dict) -> str:
    """فرمت‌دهی اطلاعات رزومه برای نمایش با HTML-escaping برای جلوگیری از خطاهای parse entities."""
    def safe(v):
        if v is None:
            return "ندارد"
        if isinstance(v, (list, dict)):
            return html.escape(str(v))
        return html.escape(str(v))

    # normalize skills (DB may contain JSON string or already a list)
    skills = data.get('skills', [])
    if isinstance(skills, str):
        try:
            skills = json.loads(skills)
        except Exception:
            skills = []

    if isinstance(skills, list) and skills:
        skills_lines = []
        for s in skills:
            if isinstance(s, dict):
                name = safe(s.get('name', 'N/A'))
                level = safe(s.get('level', 'N/A'))
                skills_lines.append(f"• {name}: {level}")
            else:
                skills_lines.append(html.escape(str(s)))
        skills_text = "\n".join(skills_lines)
    else:
        skills_text = "ندارد"

    user_id = html.escape(str(data.get('user_id', 'N/A')))
    username = html.escape(str(data.get('username', 'N/A')))
    register_date = html.escape(str(data.get('register_date', 'N/A')))

    # Build message using all configured RESUME_FIELDS to ensure nothing is missed
    # Prepend the exact acceptance line requested by admin
    text_lines = ["(⚠️ قوانین توسط کاربر پذیرفته شده است ✅)", f"<b>👤 اطلاعات کامل کاربر</b>", "---", f"<b>🆔 آیدی عددی</b>: <code>{user_id}</code>", f"<b>@ یوزرنیم</b>: @{username}", f"<b>🗓 تاریخ ثبت</b>: {register_date}", "---"]

    for idx, field in enumerate(config.RESUME_FIELDS, start=1):
        label = config.FIELD_LABELS.get(field, field)
        if field == 'skills':
            value = skills_text
        elif field == 'file_path':
            value = f"<code>{html.escape(str(data.get(field, 'ندارد')))}</code>"
        else:
            value = safe(data.get(field))

        text_lines.append(f"<b>{idx}. {label}</b>: {value}")

    return "\n".join(text_lines)


# --- توابع ادمین: نوتیفیکیشن و مشاهده ---

async def notify_admin(data: dict):
    """(مورد ۷: اعلان ثبت جدید) ارسال نوتیفیکیشن به ادمین پس از تکمیل رزومه"""
    message_text = config.ADMIN_NOTIFICATION_TEMPLATE.format(
        full_name=data.get('full_name', 'N/A'),
        username=data.get('username', 'N/A'),
        datetime=data.get('register_date', 'N/A')
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="مشاهده رزومه کامل", callback_data=f"view_resume_{data['user_id']}")]
    ])
    
    try:
        # send to all configured admins
        for admin_id in config.ADMIN_IDS:
            await bot.send_message(
                admin_id,
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        db.log("ADMIN", f"Admin notification sent for user {data['user_id']} to admins: {config.ADMIN_IDS}")
    except Exception as e:
        db.log("ERROR", f"Failed to send admin notification: {e}")


@dp.callback_query(F.data.startswith("view_resume_"))
async def admin_view_resume_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """هندلر دکمه 'مشاهده رزومه کامل' در نوتیفیکیشن"""
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    
    await callback.answer("درحال بارگذاری...")
    # edit the admin notification message to indicate the resume is being viewed
    try:
        await callback.message.edit_text("🔎 درخواست نمایش رزومه دریافت شد. دکمه حذف شد.")
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    user_id = int(callback.data.split('_')[-1])
    
    user_data = db.get_resume_data(user_id)
    if not user_data:
        await bot.send_message(callback.from_user.id, "کاربر با این آیدی پیدا نشد.", reply_markup=get_admin_main_keyboard())
        return

    # ذخیره آیدی کاربر برای اقدامات بعدی
    await state.set_state(AdminStates.view_user)
    await state.update_data(target_user_id=user_id)

    # determine block status from DB
    is_blocked = bool(int(user_data.get('is_blocked') or 0)) if user_data else False

    # (مورد ۲: نمایش اطلاعات کامل)
    text = format_resume_data(user_data)

    await bot.send_message(
        callback.from_user.id,
        text,
        reply_markup=get_user_actions_keyboard(user_id, is_blocked),
        parse_mode=ParseMode.HTML
    )


# --- FSM هندلرهای رزومه (همان کدهای قبلی که درست شده‌اند) ---
# ... (تمام هندلرهای ResumeStates تا process_training_request در اینجا قرار می‌گیرند) ...


# Note: training_request handler was moved earlier to include a confirmation step
# The real handler is defined above near the membership/confirmation logic.


# ===============================================
#           ADMIN PANEL HANDLERS (موارد ۱ تا ۱۰)
# ===============================================

@dp.message(F.text == config.KEYBOARD_ADMIN_TEXTS[0])
@dp.message(F.text == "/admin")
async def admin_panel_handler(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    # build main keyboard and update toggle label dynamically
    show_deleted = admin_show_deleted.get(message.from_user.id, False)
    kb = get_admin_main_keyboard()
    # update the toggle button text to reflect current state
    toggle_text = "🔁 نمایش حذف‌شده‌ها: روشن" if show_deleted else "🔁 نمایش حذف‌شده‌ها: خاموش"
    # replace second-to-last row first button
    try:
        kb.keyboard[-1][0] = KeyboardButton(text=toggle_text)
    except Exception:
        pass
    await message.answer("**⚙️ پنل مدیریت ربات**\n"
                         "لطفاً گزینه مورد نظر خود را انتخاب کنید.",
                         reply_markup=kb)


@dp.message(F.text == "🔁 نمایش حذف‌شده‌ها")
async def admin_toggle_show_deleted(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    current = admin_show_deleted.get(message.from_user.id, False)
    admin_show_deleted[message.from_user.id] = not current
    await message.answer(f"وضعیت نمایش حذف‌شده‌ها اکنون {'روشن' if not current else 'خاموش'} شد.")
    # re-open admin panel to show updated label
    await admin_panel_handler(message, state)


@dp.message(F.text == "📋 لیست کاربران")
async def admin_list_users_handler(message: types.Message, state: FSMContext) -> None:
    """Show paginated list of users (16 per page: 2 columns x 8 rows)."""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    # first page
    limit = 16
    offset = 0
    # respect per-admin show_deleted toggle
    show_deleted = admin_show_deleted.get(message.from_user.id, False)
    rows, total = db.search_resumes(term="", limit=limit, offset=offset, filters={'_include_deleted': show_deleted})

    if not rows:
        await message.answer("هیچ کاربری برای نمایش وجود ندارد.", reply_markup=get_admin_main_keyboard())
        return

    # build inline keyboard with 2 columns
    kb_rows = []
    row = []
    for uid, full_name, username, reg in rows:
        label = f"{full_name} | @{username}" if username else f"{full_name} | {uid}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"admin_view_{uid}"))
        if len(row) >= 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton(text="⟨ قبلی", callback_data="admin_list_prev"))
    if offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ⟩", callback_data="admin_list_next"))
    if nav_row:
        kb_rows.append(nav_row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    # store pagination state
    await state.set_state(AdminStates.list_users)
    await state.update_data(admin_list_offset=offset, admin_list_limit=limit, admin_list_total=total)

    await message.answer(f"نمایش کاربران ({min(offset+1, total)} - {min(offset+limit, total)} از {total}):", reply_markup=None)
    await message.answer("لطفاً روی یک کاربر کلیک کنید تا مشخصات وی نمایش داده شود.", reply_markup=keyboard)

# --- بازگشت به منوی اصلی ---
@dp.message(F.text == "🏠 منوی اصلی")
async def admin_back_to_main_user(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await message.answer("بازگشت به منوی اصلی کاربر.", reply_markup=get_main_keyboard(True))

@dp.message(F.text == "🔙 بازگشت به جستجو", AdminStates.view_user)
@dp.message(F.text == "🔙 بازگشت به کاربر", AdminStates.edit_select_field)
@dp.message(F.text == "🔙 بازگشت به کاربر", AdminStates.edit_enter_value)
async def admin_back_to_search(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.set_state(AdminStates.search_user)
    await message.answer("لطفاً عبارت جستجوی جدید را وارد کنید.", reply_markup=types.ReplyKeyboardRemove())


@dp.message(F.text == "بازگشت", AdminStates.search_user)
async def admin_cancel_search(message: types.Message, state: FSMContext) -> None:
    """Handler for admin pressing 'بازگشت' while in search state: return to admin main menu."""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await message.answer("بازگشت به منوی مدیریت.", reply_markup=get_admin_main_keyboard())


@dp.message(F.text == "بازگشت به صفحه اصلی", AdminStates.view_user)
async def admin_return_main_from_view(message: types.Message, state: FSMContext) -> None:
    """Allow admin to return to admin main keyboard from a user view."""
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await message.answer("بازگشت به منوی اصلی ادمین.", reply_markup=get_admin_main_keyboard())


# --- 1. جستجوی کاربر ---
@dp.message(F.text == "🔎 جستجوی کاربر")
async def admin_start_search(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.search_user)
    # Provide a simple reply keyboard with a cancel/back option so admin can abort search
    back_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="بازگشت")]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("لطفاً نام کامل، بخشی از نام یا یوزرنیم کاربر را وارد کنید:", reply_markup=back_kb)

@dp.message(AdminStates.search_user)
async def admin_process_search(message: types.Message, state: FSMContext) -> None:
    term = message.text
    results = db.get_user_by_search_term(term) # نیاز به پیاده‌سازی در database.py
    
    if not results:
        await message.answer("کاربری با این مشخصات پیدا نشد.")
        return
        
    if len(results) == 1:
        # اگر فقط یک نتیجه باشد، مستقیم به نمایش اطلاعات می‌رویم
        user_id = results[0][0]
        user_data = db.get_resume_data(user_id)
        
        await state.set_state(AdminStates.view_user)
        await state.update_data(target_user_id=user_id)
        
        await message.answer(
            format_resume_data(user_data),
            reply_markup=get_user_actions_keyboard(user_id, False), # فرض بر آنبلاک بودن
            parse_mode=ParseMode.HTML
        )
    else:
        # اگر چند نتیجه باشد، لیست نمایش داده می‌شود
        search_results = "\n".join([f"🆔 {uid} | @{username} | {name}" for uid, name, username in results])
        await message.answer(
            f"چندین کاربر پیدا شد. لطفاً آیدی تلگرام عددی (مانند `123456`) یا یوزرنیم (مانند `@user`) را دقیق وارد کنید تا اطلاعات کامل نمایش داده شود.\n\n"
            f"**نتایج:**\n{search_results}"
        )


# bot.py (فقط هندلر ادمین مربوط به اکسل)

# --- 3. دریافت اکسل ---
@dp.message(F.text == "📤 دریافت اکسل")
async def admin_export_excel(message: types.Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    await message.answer("درحال ساخت فایل اکسل. لطفاً منتظر بمانید...")
    
    success, file_path = db.export_to_excel() # فراخوانی تابع اصلاح شده در database.py
    
    if success:
        # First attempt to send the file. Only treat this as a send-failure
        # if the send itself raises an exception. Cleanup (file removal)
        # is handled separately so failures during os.remove don't
        # mistakenly report a send error to the admin.
        try:
            await bot.send_document(
                message.from_user.id,
                FSInputFile(file_path),
                caption="✅ فایل اکسل بروز شده‌ی رزومه‌ها"
            )
            db.log("ADMIN", f"Admin exported Excel file and send succeeded.")
        except Exception as e:
            db.log("ERROR", f"Failed to send Excel file: {e}")
            # Provide the admin a helpful message but include the path so they
            # can retrieve it manually if needed.
            await message.answer(f"❌ فایل اکسل ساخته شد، اما ارسال آن با خطا مواجه شد. مسیر فایل: {file_path}")
        else:
            # Try to remove the temporary file; log but do not surface
            # filesystem errors to the admin as send was successful.
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    db.log("ADMIN", f"Temporary excel file removed: {file_path}")
            except Exception as e:
                db.log("ERROR", f"Failed to remove temporary excel file {file_path}: {e}")
    else:
        await message.answer(f"❌ خطای اکسپورت: {file_path}")

@dp.message(F.text == "📥 پشتیبان‌گیری")
async def admin_backup(message: types.Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    await message.answer("درحال تهیه پشتیبان...")
    
    # ارسال فایل دیتابیس (db.sqlite3)
    try:
        await bot.send_document(
            message.from_user.id,
            FSInputFile(config.DATABASE_NAME),
            caption="بکاپ فایل دیتابیس"
        )
        db.log("ADMIN", f"Admin requested database backup.")
    except Exception as e:
        await message.answer(f"❌ خطای ارسال دیتابیس: {e}")

    # ارسال فایل لاگ (logs.txt)
    try:
        await bot.send_document(
            message.from_user.id,
            FSInputFile(config.LOG_FILE),
            caption="بکاپ فایل لاگ"
        )
        db.log("ADMIN", f"Admin requested log file backup.")
    except Exception as e:
        await message.answer(f"❌ خطای ارسال لاگ: {e}")

    # ساخت و ارسال اکسل (مورد ۳)
    await admin_export_excel(message)


# --- 4. آمار کلی ---
@dp.message(F.text == "📊 آمار کلی")
async def admin_get_stats(message: types.Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
    
    today_date_str = datetime.now().strftime("%Y-%m-%d")
    total_users, today_users = db.get_stats(today_date_str) # نیاز به پیاده‌سازی در database.py

    await message.answer(
        f"**📊 آمار کلی ربات**\n"
        f"---"
        f"**تعداد کل رزومه‌ها**: {total_users}\n"
        f"**تعداد رزومه‌های امروز**: {today_users}\n"
        f"---"
    )

# --- 10. لاگ فعالیت‌ها ---
@dp.message(F.text == "📄 مشاهده لاگ")
async def admin_view_logs(message: types.Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    logs = db.get_all_logs() # نیاز به پیاده‌سازی در database.py
    
    if not logs:
        await message.answer("فایل لاگ خالی است.")
        return
        
    log_text = "\n".join([f"[{ts}] ({lvl}) {msg}" for _, ts, lvl, msg in logs])
    
    # ارسال لاگ در یک فایل متنی برای جلوگیری از طولانی شدن پیام
    log_file_path = "temp_logs.txt"
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write(log_text)
        
    await bot.send_document(
        message.from_user.id,
        FSInputFile(log_file_path),
        caption="آخرین لاگ‌های فعالیت ربات (۵۰۰ خط آخر)"
    )
    os.remove(log_file_path) # حذف فایل موقت
    db.log("ADMIN", f"Admin viewed logs.")


# --- 6. ویرایش اطلاعات ---
@dp.message(F.text == "✏️ ویرایش اطلاعات", AdminStates.view_user)
async def admin_start_edit(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    await state.set_state(AdminStates.edit_select_field)
    await message.answer(
        "لطفاً **فیلد** مورد نظر برای ویرایش را انتخاب کنید:", 
        reply_markup=get_user_fields_keyboard()
    )

@dp.message(AdminStates.edit_select_field)
async def admin_select_field_to_edit(message: types.Message, state: FSMContext) -> None:
    """Handle admin selection in the edit-fields menu.

    Supports:
    - Selecting a Persian-labeled field to edit -> routes to value entry
    - 'تایید ویرایش' -> finish editing and return to user actions
    - 'انصراف' -> cancel editing and return to user actions
    """
    if message.from_user.id not in config.ADMIN_IDS:
        return

    text = message.text.strip()

    # special actions
    if text == "انصراف":
        data = await state.get_data()
        user_id = data.get('target_user_id')
        await state.set_state(AdminStates.view_user)
        await message.answer("ویرایش لغو شد.", reply_markup=get_user_actions_keyboard(user_id, False))
        return

    if text == "تایید ویرایش":
        data = await state.get_data()
        user_id = data.get('target_user_id')
        await state.set_state(AdminStates.view_user)
        user_data = db.get_resume_data(user_id)
        is_blocked = bool(int(user_data.get('is_blocked') or 0)) if user_data else False
        await message.answer("تغییرات ذخیره شد.", reply_markup=get_user_actions_keyboard(user_id, is_blocked))
        return

    # Map Persian label back to internal field key
    selected_key = None
    for key, label in config.FIELD_LABELS.items():
        if label == text:
            selected_key = key
            break

    if not selected_key:
        await message.answer("فیلد نامعتبر. لطفاً یکی از فیلدهای نمایش‌داده‌شده را انتخاب کنید.")
        return

    await state.update_data(edit_field_name=selected_key)
    await state.set_state(AdminStates.edit_enter_value)
    await message.answer(
        f"لطفاً مقدار جدید برای فیلد **{text}** را وارد کنید:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@dp.message(AdminStates.edit_enter_value)
async def admin_enter_new_value(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return

    data = await state.get_data()
    user_id = data.get('target_user_id')
    field_name = data.get('edit_field_name')
    new_value = message.text

    if not user_id or not field_name:
        await message.answer("خطای سیستمی در فرآیند ویرایش.")
        await state.set_state(AdminStates.search_user)
        return

    # fetch old value for audit
    user_data = db.get_resume_data(user_id) or {}
    old_value = user_data.get(field_name)

    # save
    success = db.update_user_field(user_id, field_name, new_value)
    if success:
        # log admin action
        db.log_admin_action(message.from_user.id, user_id, 'update', field_name, str(old_value), str(new_value))
        # Escape user-provided values to prevent markdown parsing errors
        safe_field_name = markdown_decoration.quote(field_name)
        safe_new_value = markdown_decoration.quote(new_value)
        await message.answer(f"✅ فیلد **{safe_field_name}** با موفقیت به **{safe_new_value}** تغییر یافت.")
        # return to edit-fields menu so admin can continue editing
        await state.set_state(AdminStates.edit_select_field)
        await state.update_data(target_user_id=user_id)
        await message.answer("ویرایش انجام شد. فیلد دیگری می‌خواهید ویرایش کنید؟", reply_markup=get_user_fields_keyboard())
    else:
        await message.answer("❌ خطا در به‌روزرسانی دیتابیس.")
        # on failure, go back to view
        user_data = db.get_resume_data(user_id)
        is_blocked = bool(int(user_data.get('is_blocked') or 0)) if user_data else False
        await state.set_state(AdminStates.view_user)
        await state.update_data(target_user_id=user_id)
        await message.answer(format_resume_data(user_data), reply_markup=get_user_actions_keyboard(user_id, is_blocked), parse_mode=ParseMode.HTML)


@dp.message(F.text == "📂 دریافت نمونه کار", AdminStates.view_user)
async def admin_get_work_samples(message: types.Message, state: FSMContext) -> None:
    """هندلر برای ارسال نمونه کارهای کاربر به ادمین."""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    data = await state.get_data()
    user_id = data.get('target_user_id')
    if not user_id:
        await message.answer("خطای سیستمی: آیدی کاربر یافت نشد. لطفاً دوباره جستجو کنید.", reply_markup=get_admin_main_keyboard())
        await state.clear()
        return

    user_data = db.get_resume_data(user_id)
    uploaded_files_json = user_data.get('uploaded_files')

    file_paths = []
    if uploaded_files_json:
        try:
            file_paths = json.loads(uploaded_files_json)
        except (json.JSONDecodeError, TypeError):
            file_paths = []

    if not file_paths:
        await message.answer("این کاربر نمونه کاری ارسال نکرده است.")
    else:
        await message.answer(f"درحال ارسال {len(file_paths)} فایل نمونه کار...")
        sent_count = 0
        for path in file_paths:
            if os.path.exists(path):
                try:
                    await bot.send_document(message.from_user.id, FSInputFile(path))
                    sent_count += 1
                except Exception as e:
                    await message.answer(f"خطا در ارسال فایل: `{path}`\n`{e}`")
                    db.log("ERROR", f"Admin failed to get work sample {path} for user {user_id}: {e}")
            else:
                await message.answer(f"فایل در مسیر زیر یافت نشد (احتمالا حذف شده است):\n`{path}`")
        await message.answer(f"✅ {sent_count} فایل با موفقیت ارسال شد.")

    await message.answer("برای بازگشت، دکمه زیر را بزنید.", reply_markup=get_user_actions_keyboard(user_id, bool(user_data.get('is_blocked', 0))))

@dp.callback_query(F.data.startswith("admin_view_"))
async def admin_search_view_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    await callback.answer()
    user_id = int(callback.data.split('_')[-1])
    user_data = db.get_resume_data(user_id)
    if not user_data:
        await callback.message.answer("کاربر با این آیدی پیدا نشد.")
        return

    await state.set_state(AdminStates.view_user)
    await state.update_data(target_user_id=user_id)
    is_blocked = bool(int(user_data.get('is_blocked') or 0)) if user_data else False
    await callback.message.answer(format_resume_data(user_data), reply_markup=get_user_actions_keyboard(user_id, is_blocked), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "admin_search_next" )
async def admin_search_next(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    term = data.get('admin_search_term', '')
    offset = data.get('admin_search_offset', 0)
    limit = data.get('admin_search_limit', 5)
    new_offset = offset + limit
    rows, total = db.search_resumes(term, limit=limit, offset=new_offset)
    # update state
    await state.update_data(admin_search_offset=new_offset)

    kb_rows = []
    for uid, full_name, username, reg in rows:
        label = f"🆔 {uid} | @{username} | {full_name}"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_view_{uid}")])

    nav_row = []
    if new_offset > 0:
        nav_row.append(InlineKeyboardButton(text="⟨ قبلی", callback_data="admin_search_prev"))
    if new_offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ⟩", callback_data="admin_search_next"))
    if nav_row:
        kb_rows.append(nav_row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await callback.message.edit_text(f"نتایج جستجو ({new_offset+1}-{min(new_offset+limit, total)} از {total}):")
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        # fallback: send new message
        await callback.message.answer(f"نتایج جستجو ({new_offset+1}-{min(new_offset+limit, total)} از {total}):", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_list_next")
async def admin_list_next(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    offset = data.get('admin_list_offset', 0)
    limit = data.get('admin_list_limit', 16)
    total = data.get('admin_list_total', 0)
    new_offset = offset + limit
    show_deleted = admin_show_deleted.get(callback.from_user.id, False)
    rows, total = db.search_resumes(term="", limit=limit, offset=new_offset, filters={'_include_deleted': show_deleted})
    # update state
    await state.update_data(admin_list_offset=new_offset, admin_list_total=total)

    kb_rows = []
    row = []
    for uid, full_name, username, reg in rows:
        label = f"{full_name} | @{username}" if username else f"{full_name} | {uid}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"admin_view_{uid}"))
        if len(row) >= 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    nav_row = []
    if new_offset > 0:
        nav_row.append(InlineKeyboardButton(text="⟨ قبلی", callback_data="admin_list_prev"))
    if new_offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ⟩", callback_data="admin_list_next"))
    if nav_row:
        kb_rows.append(nav_row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await callback.message.edit_text(f"نمایش کاربران ({new_offset+1}-{min(new_offset+limit, total)} از {total}):")
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        await callback.message.answer(f"نمایش کاربران ({new_offset+1}-{min(new_offset+limit, total)} از {total}):", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_list_prev")
async def admin_list_prev(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    offset = data.get('admin_list_offset', 0)
    limit = data.get('admin_list_limit', 16)
    total = data.get('admin_list_total', 0)
    new_offset = max(0, offset - limit)
    show_deleted = admin_show_deleted.get(callback.from_user.id, False)
    rows, total = db.search_resumes(term="", limit=limit, offset=new_offset, filters={'_include_deleted': show_deleted})
    await state.update_data(admin_list_offset=new_offset, admin_list_total=total)

    kb_rows = []
    row = []
    for uid, full_name, username, reg in rows:
        label = f"{full_name} | @{username}" if username else f"{full_name} | {uid}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"admin_view_{uid}"))
        if len(row) >= 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    nav_row = []
    if new_offset > 0:
        nav_row.append(InlineKeyboardButton(text="⟨ قبلی", callback_data="admin_list_prev"))
    if new_offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ⟩", callback_data="admin_list_next"))
    if nav_row:
        kb_rows.append(nav_row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await callback.message.edit_text(f"نمایش کاربران ({new_offset+1}-{min(new_offset+limit, total)} از {total}):")
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        await callback.message.answer(f"نمایش کاربران ({new_offset+1}-{min(new_offset+limit, total)} از {total}):", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_search_prev" )
async def admin_search_prev(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    term = data.get('admin_search_term', '')
    offset = data.get('admin_search_offset', 0)
    limit = data.get('admin_search_limit', 5)
    new_offset = max(0, offset - limit)
    rows, total = db.search_resumes(term, limit=limit, offset=new_offset)
    await state.update_data(admin_search_offset=new_offset)

    kb_rows = []
    for uid, full_name, username, reg in rows:
        label = f"🆔 {uid} | @{username} | {full_name}"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_view_{uid}")])

    nav_row = []
    if new_offset > 0:
        nav_row.append(InlineKeyboardButton(text="⟨ قبلی", callback_data="admin_search_prev"))
    if new_offset + limit < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ⟩", callback_data="admin_search_next"))
    if nav_row:
        kb_rows.append(nav_row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    try:
        await callback.message.edit_text(f"نتایج جستجو ({new_offset+1}-{min(new_offset+limit, total)} از {total}):")
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        await callback.message.answer(f"نتایج جستجو ({new_offset+1}-{min(new_offset+limit, total)} از {total}):", reply_markup=keyboard)


# --- 5. حذف کاربر ---
@dp.message(F.text == "🗑️ حذف کاربر", AdminStates.view_user)
async def admin_start_delete(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    user_data = db.get_resume_data(user_id)
    
    await state.set_state(AdminStates.delete_confirm)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"حذف کاربر {user_id}"), KeyboardButton(text="لغو")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    
    await message.answer(
        f"⚠️ **اخطار حذف!**\n"
        f"آیا مطمئن هستید که می‌خواهید کاربر **{user_data.get('full_name')}** با آیدی `{user_id}` را حذف کنید؟ این عمل غیرقابل بازگشت است.",
        reply_markup=keyboard
    )

@dp.message(AdminStates.delete_confirm)
async def admin_confirm_delete(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    
    if message.text == f"حذف کاربر {user_id}":
        # perform soft-delete and log
        ok = db.soft_delete_user(user_id, message.from_user.id)
        if ok:
            await message.answer(f"✅ کاربر با آیدی `{user_id}` با موفقیت حذف (soft-delete) شد.", reply_markup=get_admin_main_keyboard())
        else:
            await message.answer(f"❌ خطا در حذف کاربر {user_id}.", reply_markup=get_admin_main_keyboard())
        await state.set_state(None)
    elif message.text == "لغو":
        await message.answer("عملیات حذف لغو شد.", reply_markup=get_admin_main_keyboard())
        await state.set_state(None)
    else:
        await message.answer("ورودی نامعتبر. لطفاً یکی از دکمه‌های بالا را انتخاب کنید.")


# --- 9. بلاک/آنبلاک کاربر ---
@dp.message(F.text.in_(["🚫 بلاک", "✅ آنبلاک"]), AdminStates.view_user)
async def admin_block_unblock(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    action = message.text

    # منطق بلاک/آنبلاک (نیاز به فیلد is_blocked در دیتابیس)
    is_blocked = (action == "🚫 بلاک")
    
    # فرض بر این است که تابع update_user_field می‌تواند فیلد is_blocked را هم تنظیم کند.
    # باید در database.py یک فیلد is_blocked به جدول اضافه کنید.
    db.update_user_field(user_id, 'is_blocked', 1 if is_blocked else 0) 
    
    status_text = "بلاک" if is_blocked else "آنبلاک"
    await message.answer(f"✅ کاربر با آیدی `{user_id}` با موفقیت **{status_text}** شد.")
    db.log("ADMIN", f"User {user_id} was {status_text}ed by admin.")
    
    # بازگشت به نمایش کاربر
    user_data = db.get_resume_data(user_id)
    # آپدیت کیبورد با وضعیت جدید (اینجا فرض می‌شود وضعیت بلاک از دیتابیس خوانده شود)
    await message.answer(
        format_resume_data(user_data),
        reply_markup=get_user_actions_keyboard(user_id, is_blocked), 
        parse_mode=ParseMode.HTML
    )

# --- اجرای ربات ---

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        db.close()
        print("Bot stopped and database connection closed.")