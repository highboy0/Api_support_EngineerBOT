# bot.py
import asyncio
import re
import os
import json
from datetime import datetime

# --- ایمپورت‌های aiogram ---
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup 
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, KeyboardButton, ReplyKeyboardMarkup
from aiogram.client.default import DefaultBotProperties # برای رفع خطای TypeError در تعریف Bot

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
    training_request = State()

    finished = State()

# --- توابع کمکی ساخت کیبورد (رفع خطای ValidationError) ---

def create_reply_keyboard(texts: list, one_time: bool = False) -> ReplyKeyboardMarkup:
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
    # ساخت دکمه اصلی
    main_button = [KeyboardButton(text=config.KEYBOARD_MAIN_TEXTS[0])]

    keyboard_rows = [main_button]
    
    # اضافه کردن دکمه ادمین (Admin Panel)
    if is_admin:
        admin_button = KeyboardButton(text=config.KEYBOARD_ADMIN_TEXTS[0])
        keyboard_rows.append([admin_button]) 
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder="منوی اصلی..."
    )

def get_skill_keyboard() -> InlineKeyboardMarkup:
    # این کیبورد Inline است و نیازی به تبدیل ندارد
    kb = []
    for row in config.KEYBOARD_SKILLS[:-1]:
        kb.append([InlineKeyboardButton(text=s, callback_data=f"skill_{s}") for s in row])
    
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="مرحله بعد", callback_data="worksample_skip")]
    ])
    return kb

def is_valid_phone(phone: str) -> bool:
    return re.fullmatch(r"09\d{9}", phone.strip())

# --- هندلر کاربر: شروع و منوی اصلی ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    # هنگام استارت، متن طولانی شرایط را نمایش بده و درخواست تایید کن
    is_admin = message.from_user.id == config.ADMIN_ID
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
    is_admin = callback.from_user.id == config.ADMIN_ID
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

    await state.set_state(ResumeStates.study_status)
    await message.answer(
        "**۲. وضعیت تحصیلی**\n"
        "لطفاً وضعیت تحصیلی خود را انتخاب کنید.",
        reply_markup=create_reply_keyboard(config.KEYBOARD_STUDY_STATUS_TEXTS)
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

@dp.message(ResumeStates.study_status, F.text.in_(config.KEYBOARD_STUDY_STATUS_TEXTS))
async def process_study_status(message: types.Message, state: FSMContext) -> None:
    await state.update_data(study_status=message.text)
    await persist_state_to_db(message.from_user.id, state)
    
    await state.set_state(ResumeStates.degree)
    await message.answer(
        "**۳. مقطع تحصیلی**\n"
        "لطفاً مقطع تحصیلی خود را انتخاب کنید.",
        reply_markup=create_reply_keyboard(config.KEYBOARD_DEGREE_TEXTS)
    )

@dp.message(ResumeStates.degree, F.text.in_(config.KEYBOARD_DEGREE_TEXTS))
async def process_degree(message: types.Message, state: FSMContext) -> None:
    await state.update_data(degree=message.text)
    await persist_state_to_db(message.from_user.id, state)
    # اکنون رشته تحصیلی را از لیست انتخابی بپرس
    await state.set_state(ResumeStates.major)
    await message.answer(
        "**۴. رشته تحصیلی**\n"
        "لطفاً رشته تحصیلی خود را انتخاب کنید.\n\n"
        "نکته: پس از انتخاب رشته، لطفاً نام دانشگاه یا مؤسسه آموزشی آخرین محل تحصیل را وارد کنید.",
        reply_markup=get_major_keyboard()
    )

# bot.py (بخش هندلرهای FSM)

# ... (ادامه هندلرهای قبلی) ...

@dp.message(ResumeStates.degree, F.text.in_(config.KEYBOARD_DEGREE_TEXTS))
async def process_degree(message: types.Message, state: FSMContext) -> None:
    await state.update_data(degree=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    
    # اکنون رشته تحصیلی را از لیست انتخابی بپرس
    await state.set_state(ResumeStates.major)
    await message.answer(
        "**۴. رشته تحصیلی**\n"
        "لطفاً رشته تحصیلی خود را انتخاب کنید.\n\n"
        "نکته: پس از انتخاب رشته، لطفاً نام دانشگاه یا مؤسسه آموزشی آخرین محل تحصیل را وارد کنید.",
        reply_markup=get_major_keyboard()
    )

# --- اضافه شدن هندلر گمشده: ۴. رشته تحصیلی و دانشگاه ---
@dp.message(ResumeStates.field_university)
async def process_field_university(message: types.Message, state: FSMContext) -> None:
    await state.update_data(field_university=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    
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
    await state.update_data(major=major)
    await persist_state_to_db(callback.from_user.id, state)

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
    await state.update_data(skills=[]) # آماده‌سازی لیست مهارت‌ها
    # رفتن به مرحله انتخاب میزان تسلط زبان انگلیسی قبل از شروع مهارت‌ها
    await state.set_state(ResumeStates.english_level)
    await message.answer(
        "**۹. میزان تسلط به زبان انگلیسی**\n"
        "لطفاً میزان تسلط خود به زبان انگلیسی را انتخاب کنید.",
        reply_markup=get_english_level_keyboard()
    )


# --- لوپ مهارت‌ها (Skill Loop Handlers) ---

@dp.callback_query(ResumeStates.skills_start, F.data.startswith("skill_"))
async def process_skill_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    # امن‌تر کردن پارس کردن callback data: بقیه رشته بعد از پیش‌وند را بگیریم
    skill_action = callback.data[len("skill_"):]
    
    if skill_action == "continue":
        user_data = await state.get_data()
        db.save_resume_data(callback.from_user.id, user_data)
        
        await state.set_state(ResumeStates.work_sample_upload)
        await bot.send_message(
            callback.from_user.id,
            "**۱۰. آپلود نمونه کار**\n"
            f"لطفاً نمونه کار خود را آپلود کنید (حداکثر **{config.MAX_FILE_SIZE_MB} مگابایت**، فرمت: PDF, DOCX, ZIP, JPG, PNG).\n"
            "**توجه**: فایل خود را به صورت سند (Document) ارسال کنید."
            ,
            reply_markup=get_skip_worksample_keyboard()
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
        reply_markup=get_skill_keyboard()
    )


@dp.callback_query(F.data.startswith("english_"))
async def process_english_level(callback: types.CallbackQuery, state: FSMContext) -> None:
    """پردازش انتخاب میزان تسلط انگلیسی و ادامه به مرحله مهارت‌ها"""
    await callback.answer()
    level = callback.data[len("english_"):]
    await state.update_data(english_level=level)
    await persist_state_to_db(callback.from_user.id, state)

    await state.set_state(ResumeStates.skills_start)
    await bot.send_message(
        callback.from_user.id,
        "**۱۰. مهارت‌های نرم‌افزاری**\n"
        "لطفاً مهارت‌های خود را از لیست زیر انتخاب کنید و سپس سطح خود را مشخص نمایید.\n"
        "پس از اتمام، روی **ادامه به مرحله بعد** کلیک کنید.",
        reply_markup=get_skill_keyboard()
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
    save_path = os.path.join(
        config.UPLOADS_DIR, 
        f"resume_{message.from_user.id}_{timestamp}{file_extension}"
    )

    try:
        file = await bot.get_file(file_info.file_id)
        await bot.download_file(file.file_path, save_path)
        
        await state.update_data(file_path=save_path)
        await persist_state_to_db(message.from_user.id, state)
        db.log("INFO", f"User {message.from_user.id} uploaded file to: {save_path}")
        
        await state.set_state(ResumeStates.work_history)
        await message.answer(
            "**۱۱. سابقه کار**\n"
            "آیا سابقه کار مرتبط دارید؟",
            reply_markup=create_reply_keyboard(config.KEYBOARD_WORK_HISTORY_TEXTS)
        )

    except Exception as e:
        db.log("ERROR", f"File download failed for user {message.from_user.id}: {e}")
        await message.answer("❌ خطایی در آپلود فایل رخ داد. لطفاً دوباره تلاش کنید.")
        await state.set_state(ResumeStates.work_sample_upload)


@dp.callback_query(F.data == "worksample_skip")
async def worksample_skip_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """پردازش دکمه 'مرحله بعد' در صفحه آپلود نمونه‌کار برای عبور از این مرحله."""
    await callback.answer()
    await state.set_state(ResumeStates.work_history)
    db.log("INFO", f"User {callback.from_user.id} skipped work sample upload.")
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
    
    await state.set_state(ResumeStates.job_position)
    await message.answer(
        "**۱۲. جایگاه مدنظر شغلی طبق توانایی شما**\n"
        "لطفاً جایگاه شغلی مدنظر خود را انتخاب کنید.",
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
            "**۱۲. جایگاه مدنظر شغلی طبق توانایی شما**\n"
            "لطفاً جایگاه شغلی مدنظر خود را انتخاب کنید.",
            reply_markup=create_reply_keyboard(config.KEYBOARD_JOB_POSITION_TEXTS)
        )
        return
    await message.answer("لطفاً از دکمه‌های تعیین شده استفاده کنید.")

@dp.message(ResumeStates.job_position, F.text.in_(config.KEYBOARD_JOB_POSITION_TEXTS))
async def process_job_position(message: types.Message, state: FSMContext) -> None:
    await state.update_data(job_position=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    
    await state.set_state(ResumeStates.other_details)
    await message.answer(
        "**۱۳. توضیحات دیگر**\n"
        "اگر توضیح دیگری دارید که فکر می‌کنید می‌تواند در پذیرش شما موثر باشد، وارد کنید (اختیاری).",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(ResumeStates.other_details)
async def process_other_details(message: types.Message, state: FSMContext) -> None:
    await state.update_data(other_details=message.text)
    user_data = await state.get_data()
    db.save_resume_data(message.from_user.id, user_data)
    
    await state.set_state(ResumeStates.training_request)
    await message.answer(
        "**۱۴. درخواست آموزش**\n"
        "آیا تمایل به شرکت در دوره‌های آموزشی مرتبط دارید؟",
        reply_markup=create_reply_keyboard(config.KEYBOARD_TRAINING_REQUEST_TEXTS)
    )

# --- مرحله ۱۵ و ۱۶: تکمیل رزومه و نوتیفیکیشن ادمین ---

@dp.message(ResumeStates.training_request, F.text.in_(config.KEYBOARD_TRAINING_REQUEST_TEXTS))
async def process_training_request(message: types.Message, state: FSMContext) -> None:
    await state.update_data(training_request=message.text)
    
    # Ensure final state is persisted and include user_id for admin notification
    await persist_state_to_db(message.from_user.id, state)
    user_data = await state.get_data()
    user_data['user_id'] = message.from_user.id # برای نوتیفیکیشن ادمین
    # save again to ensure user_id is present in stored record
    db.save_resume_data(message.from_user.id, user_data)
    
    await state.set_state(ResumeStates.finished)
    
    # پیام موفقیت آمیز
    await message.answer(
        config.SUCCESS_MESSAGE,
        reply_markup=get_main_keyboard(message.from_user.id == config.ADMIN_ID)
    )
    db.log("SUCCESS", f"Resume successfully submitted by User ID: {message.from_user.id}")
    await state.clear()
    
    # نوتیفیکیشن به ادمین (مرحله ۱۶)
    await notify_admin(user_data)

# ... (ادامه کد: توابع notify_admin و هندلرهای ادمین) ...
@dp.message(F.text == "🏠 منوی اصلی")
async def admin_back_to_main(message: types.Message) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
    await message.answer("بازگشت به منوی اصلی.", reply_markup=get_main_keyboard(True))

# ... (بقیه هندلرهای ادمین بدون نیاز به تغییر ساختار کیبورد) ...

class AdminStates(StatesGroup):
    search_user = State()
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

def get_main_keyboard(is_admin) -> ReplyKeyboardMarkup:
    main_button = [KeyboardButton(text=config.KEYBOARD_MAIN_TEXTS[0])]
    keyboard_rows = [main_button]
    if is_admin:
        admin_button = KeyboardButton(text=config.KEYBOARD_ADMIN_TEXTS[0])
        keyboard_rows.append([admin_button]) 
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True, input_field_placeholder="منوی اصلی...")

def get_admin_main_keyboard() -> ReplyKeyboardMarkup:
    """منوی اصلی پنل ادمین"""
    keyboard_rows = [
        [KeyboardButton(text="🔎 جستجوی کاربر"), KeyboardButton(text="📊 آمار کلی")],
        [KeyboardButton(text="📤 دریافت اکسل"), KeyboardButton(text="📥 پشتیبان‌گیری")],
        [KeyboardButton(text="📄 مشاهده لاگ"), KeyboardButton(text="🏠 منوی اصلی")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_user_actions_keyboard(user_id: int, is_blocked: bool) -> ReplyKeyboardMarkup:
    """کیبورد اقدامات ادمین روی کاربر خاص"""
    block_status = "✅ آنبلاک" if is_blocked else "🚫 بلاک"
    keyboard_rows = [
        [KeyboardButton(text="✏️ ویرایش اطلاعات"), KeyboardButton(text="🗑️ حذف کاربر")],
        [KeyboardButton(text=block_status)],
        [KeyboardButton(text="🔙 بازگشت به جستجو")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_user_fields_keyboard():
    """کیبورد فیلدهای قابل ویرایش"""
    fields = config.RESUME_FIELDS.copy()
    fields.remove('register_date')
    fields.remove('file_path')
    
    keyboard_rows = []
    for i in range(0, len(fields), 2):
        row = [KeyboardButton(text=fields[i])]
        if i + 1 < len(fields):
            row.append(KeyboardButton(text=fields[i+1]))
        keyboard_rows.append(row)
    keyboard_rows.append([KeyboardButton(text="🔙 بازگشت به کاربر")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)


def is_valid_phone(phone: str) -> bool:
    return re.fullmatch(r"09\d{9}", phone.strip())

def format_resume_data(data: dict) -> str:
    """فرمت‌دهی اطلاعات رزومه برای نمایش"""
    skills = data.get('skills', [])
    if isinstance(skills, str):
        try:
            skills = json.loads(skills)
        except:
            skills = []

    skills_text = "\n".join([f"    • {s.get('name', 'N/A')}: {s.get('level', 'N/A')}" for s in skills]) if skills else "ندارد"

    text = f"""
**👤 اطلاعات کامل کاربر**
---
**🆔 آیدی تلگرام**: `{data.get('user_id', 'N/A')}`
**@ یوزرنیم**: @{data.get('username', 'N/A')}
**🗓 تاریخ ثبت**: {data.get('register_date', 'N/A')}
---
**۱. نام کامل**: {data.get('full_name', 'N/A')}
**۲. وضعیت تحصیلی**: {data.get('study_status', 'N/A')}
**۳. مقطع**: {data.get('degree', 'N/A')}
**۴. رشته/دانشگاه**: {data.get('field_university', 'N/A')}
    **۵. معدل**: {data.get('gpa', 'N/A')}
**۶. تسلط زبان انگلیسی**: {data.get('english_level', 'N/A')}
**۷. محل سکونت**: {data.get('location', 'N/A')}
**۷. تلفن اصلی**: {data.get('phone_main', 'N/A')}
**۸. تلفن اضطراری**: {data.get('phone_emergency', 'N/A')}
---
**۹. مهارت‌ها**:
{skills_text}
---
**۱۰. مسیر فایل نمونه کار**: `{data.get('file_path', 'ندارد')}`
**۱۱. سابقه کار**: {data.get('work_history', 'N/A')}
**۱۲. جایگاه مدنظر**: {data.get('job_position', 'N/A')}
**۱۳. توضیحات دیگر**: {data.get('other_details', 'ندارد')}
**۱۴. درخواست آموزش**: {data.get('training_request', 'N/A')}
"""
    return text


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
        await bot.send_message(
            config.ADMIN_ID,
            message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        db.log("ADMIN", f"Admin notification sent for user {data['user_id']}")
    except Exception as e:
        db.log("ERROR", f"Failed to send admin notification: {e}")


@dp.callback_query(F.data.startswith("view_resume_"))
async def admin_view_resume_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """هندلر دکمه 'مشاهده رزومه کامل' در نوتیفیکیشن"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("شما دسترسی ادمین ندارید.", show_alert=True)
        return
    
    await callback.answer("درحال بارگذاری...")
    user_id = int(callback.data.split('_')[-1])
    
    user_data = db.get_resume_data(user_id)
    if not user_data:
        await bot.send_message(callback.from_user.id, "کاربر با این آیدی پیدا نشد.", reply_markup=get_admin_main_keyboard())
        return

    # ذخیره آیدی کاربر برای اقدامات بعدی
    await state.set_state(AdminStates.view_user)
    await state.update_data(target_user_id=user_id)
    
    # (مورد ۲: نمایش اطلاعات کامل)
    text = format_resume_data(user_data)
    
    await bot.send_message(
        callback.from_user.id,
        text,
        reply_markup=get_user_actions_keyboard(user_id, False) # فرض بر آنبلاک بودن
    )


# --- FSM هندلرهای رزومه (همان کدهای قبلی که درست شده‌اند) ---
# ... (تمام هندلرهای ResumeStates تا process_training_request در اینجا قرار می‌گیرند) ...


# --- مرحله ۱۵ و ۱۶: تکمیل رزومه و نوتیفیکیشن ادمین ---

@dp.message(ResumeStates.training_request, F.text.in_(config.KEYBOARD_TRAINING_REQUEST_TEXTS))
async def process_training_request(message: types.Message, state: FSMContext) -> None:
    await state.update_data(training_request=message.text)
    
    user_data = await state.get_data()
    user_data['user_id'] = message.from_user.id
    db.save_resume_data(message.from_user.id, user_data)
    
    await state.set_state(ResumeStates.finished)
    
    await message.answer(
        config.SUCCESS_MESSAGE,
        reply_markup=get_main_keyboard(message.from_user.id == config.ADMIN_ID)
    )
    db.log("SUCCESS", f"Resume successfully submitted by User ID: {message.from_user.id}")
    await state.clear()
    
    # اطمینان از ارسال نوتیفیکیشن (مورد ۱)
    await notify_admin(user_data)


# ===============================================
#           ADMIN PANEL HANDLERS (موارد ۱ تا ۱۰)
# ===============================================

@dp.message(F.text == config.KEYBOARD_ADMIN_TEXTS[0])
@dp.message(F.text == "/admin")
async def admin_panel_handler(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await message.answer("**⚙️ پنل مدیریت ربات**\n"
                         "لطفاً گزینه مورد نظر خود را انتخاب کنید.",
                         reply_markup=get_admin_main_keyboard())

# --- بازگشت به منوی اصلی ---
@dp.message(F.text == "🏠 منوی اصلی")
async def admin_back_to_main_user(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await message.answer("بازگشت به منوی اصلی کاربر.", reply_markup=get_main_keyboard(True))

@dp.message(F.text == "🔙 بازگشت به جستجو", AdminStates.view_user)
@dp.message(F.text == "🔙 بازگشت به کاربر", AdminStates.edit_select_field)
@dp.message(F.text == "🔙 بازگشت به کاربر", AdminStates.edit_enter_value)
async def admin_back_to_search(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.set_state(AdminStates.search_user)
    await message.answer("لطفاً عبارت جستجوی جدید را وارد کنید.", reply_markup=types.ReplyKeyboardRemove())


# --- 1. جستجوی کاربر ---
@dp.message(F.text == "🔎 جستجوی کاربر")
async def admin_start_search(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
    await state.clear()
    await state.set_state(AdminStates.search_user)
    await message.answer("لطفاً نام کامل، بخشی از نام یا یوزرنیم کاربر را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())

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
            reply_markup=get_user_actions_keyboard(user_id, False) # فرض بر آنبلاک بودن
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
    if message.from_user.id != config.ADMIN_ID:
        return
        
    await message.answer("درحال ساخت فایل اکسل. لطفاً منتظر بمانید...")
    
    success, file_path = db.export_to_excel() # فراخوانی تابع اصلاح شده در database.py
    
    if success:
        try:
            await bot.send_document(
                message.from_user.id,
                FSInputFile(file_path),
                caption="✅ فایل اکسل بروز شده‌ی رزومه‌ها"
            )
            os.remove(file_path) # حذف فایل موقت پس از ارسال
            db.log("ADMIN", f"Admin exported Excel file.")
        except Exception as e:
            db.log("ERROR", f"Failed to send Excel file: {e}")
            await message.answer("❌ فایل اکسل ساخته شد، اما ارسال آن با خطا مواجه شد.")
    else:
        await message.answer(f"❌ خطای اکسپورت: {file_path}")

@dp.message(F.text == "📥 پشتیبان‌گیری")
async def admin_backup(message: types.Message) -> None:
    if message.from_user.id != config.ADMIN_ID:
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
    if message.from_user.id != config.ADMIN_ID:
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
    if message.from_user.id != config.ADMIN_ID:
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
    if message.from_user.id != config.ADMIN_ID:
        return
        
    await state.set_state(AdminStates.edit_select_field)
    await message.answer(
        "لطفاً **فیلد** مورد نظر برای ویرایش را انتخاب کنید:", 
        reply_markup=get_user_fields_keyboard()
    )

@dp.message(AdminStates.edit_select_field, F.text.in_(config.RESUME_FIELDS))
async def admin_select_field_to_edit(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
        
    field_name = message.text
    await state.update_data(edit_field_name=field_name)
    await state.set_state(AdminStates.edit_enter_value)
    
    await message.answer(
        f"لطفاً **مقدار جدید** برای فیلد **{field_name}** را وارد کنید:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(AdminStates.edit_enter_value)
async def admin_enter_new_value(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    field_name = data.get('edit_field_name')
    new_value = message.text
    
    if not user_id or not field_name:
        await message.answer("خطای سیستمی در فرآیند ویرایش.")
        await state.set_state(AdminStates.search_user)
        return
        
    # ذخیره در دیتابیس
    success = db.update_user_field(user_id, field_name, new_value) # نیاز به پیاده‌سازی در database.py
    
    if success:
        await message.answer(f"✅ فیلد **{field_name}** با موفقیت به **{new_value}** تغییر یافت.")
    else:
        await message.answer("❌ خطا در به‌روزرسانی دیتابیس.")

    # بازگشت به نمایش کاربر
    user_data = db.get_resume_data(user_id)
    await state.set_state(AdminStates.view_user)
    await message.answer(
        format_resume_data(user_data),
        reply_markup=get_user_actions_keyboard(user_id, False) 
    )


# --- 5. حذف کاربر ---
@dp.message(F.text == "🗑️ حذف کاربر", AdminStates.view_user)
async def admin_start_delete(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
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
    if message.from_user.id != config.ADMIN_ID:
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    
    if message.text == f"حذف کاربر {user_id}":
        db.delete_user(user_id) # نیاز به پیاده‌سازی در database.py
        await message.answer(f"✅ کاربر با آیدی `{user_id}` با موفقیت حذف شد.", reply_markup=get_admin_main_keyboard())
        await state.set_state(None)
    elif message.text == "لغو":
        await message.answer("عملیات حذف لغو شد.", reply_markup=get_admin_main_keyboard())
        await state.set_state(None)
    else:
        await message.answer("ورودی نامعتبر. لطفاً یکی از دکمه‌های بالا را انتخاب کنید.")


# --- 9. بلاک/آنبلاک کاربر ---
@dp.message(F.text.in_(["🚫 بلاک", "✅ آنبلاک"]), AdminStates.view_user)
async def admin_block_unblock(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id != config.ADMIN_ID:
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
        reply_markup=get_user_actions_keyboard(user_id, is_blocked) 
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


    