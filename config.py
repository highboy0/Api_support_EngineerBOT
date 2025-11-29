# config.py
import os

# --- تنظیمات اصلی ---
TOKEN = "8401976510:AAEk_sXqK6hM6NkKvkIX00YMvrsWoPhDiyo"  # توکن ربات خود را اینجا قرار دهید
ADMIN_ID = 5884300880           # آیدی عددی ادمین
MAX_FILE_SIZE_MB = 200        
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
#SUPPORT_ID = 

# --- مسیرها ---
DATABASE_NAME = "db.sqlite3"
LOG_FILE = "logs.txt"
UPLOADS_DIR = "uploads"
EXCEL_OUTPUT = "resumes_export.xlsx"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- محتوای متنی ---
START_MESSAGE = (
    "🚀 به ربات جمع‌آوری رزومه خوش آمدید!  \n"
    "اینجا بهترین فرصت‌های شغلی در انتظار شماست!  \n"
    "لطفاً رزومه خود را با دقت تکمیل کنید."
)
SUCCESS_MESSAGE = (
    "✅ رزومه شما با موفقیت تکمیل و ارسال شد!  \n"
    "به زودی با شما تماس خواهیم گرفت.  \n"
    "موفق باشید! 🌟"
)
ADMIN_NOTIFICATION_TEMPLATE = (
    "🔔 رزومه جدید ثبت شد!\n"
    "**نام**: {full_name}\n"
    "**آیدی**: @{username}\n"
    "**زمان**: {datetime}"
)

# config.py (تغییرات)

# ... (بقیه متغیرهای قبلی) ...

# --- لیست‌های متنی کیبوردها (Text Lists) ---
# ... (بقیه لیست‌های قبلی) ...
KEYBOARD_ADMIN_OPTIONS = [
    ["🔎 جستجوی کاربر", "📊 آمار کلی"],
    ["📤 دریافت اکسل", "📥 پشتیبان‌گیری"],
    ["⚙️ منوی اصلی ادمین"]
]
KEYBOARD_ADMIN_MAIN = [
    ["🏠 منوی اصلی"]
]

KEYBOARD_USER_ACTIONS = [
    ["✏️ ویرایش اطلاعات", "🗑️ حذف کاربر"],
    ["🚫 بلاک/✅ آنبلاک"],
    ["🔙 بازگشت به جستجو"]
]

# --- نوتیفیکیشن و پیام‌های ادمین ---
ADMIN_NOTIFICATION_TEMPLATE = (
    "🔔 **{full_name}** رزومه جدید ثبت کرد!\n"
    "**آیدی تلگرام**: @{username}\n"
    "**زمان ثبت**: {datetime}"
)

# --- لیست‌های متنی کیبوردها (Text Lists) ---
KEYBOARD_MAIN_TEXTS = ["📄 ارسال رزومه"]
KEYBOARD_ADMIN_TEXTS = ["⚙️ پنل ادمین"]
KEYBOARD_STUDY_STATUS_TEXTS = ["فارغ‌التحصیل", "در حال تحصیل"]
KEYBOARD_DEGREE_TEXTS = ["کارشناسی", "ارشد", "دکتری"]
KEYBOARD_WORK_HISTORY_TEXTS = ["دارم", "ندارم"]
KEYBOARD_JOB_POSITION_TEXTS = ["کارشناس عادی", "کارشناس اجرایی"]
KEYBOARD_TRAINING_REQUEST_TEXTS = ["بله", "خیر"]

KEYBOARD_SKILLS = [
    ["GIS", "3D Max", "AutoCAD"],
    ["Metashape", "GIS Pro", "سایر مهارت‌ها"],
    ["ادامه به مرحله بعد"]
]
KEYBOARD_SKILL_LEVEL = [["مبتدی", "متوسط", "پیشرفته"]]

# داده‌های دیتابیس برای ذخیره‌ی ساختار
RESUME_FIELDS = [
    "full_name", "username", "study_status", "degree", "field_university", "gpa",
    "location", "phone_main", "phone_emergency", "skills", "work_history",
    "job_position", "other_details", "training_request", "file_path", "register_date"
]

SKILLS_LIST = ["GIS", "3D Max", "AutoCAD", "Metashape", "GIS Pro"]