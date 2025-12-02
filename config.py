# config.py
import os
from dotenv import load_dotenv

# Load .env (if present)
load_dotenv()

# --- تنظیمات اصلی ---
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "8490115986:AAFC1N284kS1k0yRALylr4pBRAP5HJ1NCqo"

# Support multiple admin IDs via .env: set ADMIN_IDS="123,456" or ADMIN_ID="123"
_admins_env = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID")
ADMIN_IDS = []
if _admins_env:
    for part in _admins_env.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            ADMIN_IDS.append(int(part))
        except ValueError:
            # ignore invalid entries
            continue

# Fallback to a default admin if none provided
if not ADMIN_IDS:
    ADMIN_IDS = [5884300880]

# Backwards-compatible single ADMIN_ID (first in the list)
ADMIN_ID = ADMIN_IDS[0]
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
    "۱) سلام، من میلاد فیروزی هستم. به ربات ایران مهندس‌یار خوش‌آمدید.\n"
    "این ربات برای کمک به ساخت رزومه حرفه‌ای و شناسایی مهارت‌های شما طراحی شده است. امیدوارم تجربه‌ای مفید داشته باشید.\n\n"
    "۲) ⚠️این سامانه با هدف تسهیل فرآیند تدوین رزومه، ارزیابی اولیه مهارت‌ها و ایجاد بانک اطلاعاتی از نیروهای متخصص حوزه (شهرسازی,معماری,عمران و...) طراحی شده است. لطفاً پیش از ورود اطلاعات، موارد زیر را با دقت مطالعه فرمایید:\n\n"
    "1. اطلاعات واردشده توسط کاربر، صرفاً جهت ارائه خدمات رزومه‌سازی و تحلیل مهارت‌ها مورد استفاده قرار می‌گیرد.\n"
    "2. این سامانه هیچ‌گونه مسئولیت حقوقی یا اداری نسبت به صحت، دقت یا کامل‌بودن اطلاعات ارائه‌شده متقاضیان ندارد.\n"
    "3. تمام مسئولیت صحت اطلاعات ثبت‌شده بر عهده کاربر می باشد.\n"
    "4. ثبت اطلاعات در این سامانه به معنای قبول شرایط فوق و رضایت از نحوه استفاده از داده‌ها می‌باشد.\n\n"
    "⚜️در صورت موافقت با شرایط فوق، می‌توانید فرآیند رزومه‌سازی را آغاز نمایید."
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
KEYBOARD_DEGREE_TEXTS = ["کاردانی", "کارشناسی", "ارشد", "دکتری"]
KEYBOARD_MAJOR_TEXTS = ["شهرسازی","معماری","نقشه‌برداری","جغرافیای شهری","ممیزی املاک","عمران","GIS"]
KEYBOARD_WORK_HISTORY_TEXTS = ["دارم", "ندارم"]
KEYBOARD_JOB_POSITION_TEXTS = ["کارشناس", "کارشناس ارشد", "کارشناس اجرایی", "کارشناس طراحی"]
KEYBOARD_TRAINING_REQUEST_TEXTS = ["بله", "خیر"]

KEYBOARD_SKILLS = [
    ["GIS", "3D Max", "AutoCAD"],
    ["Metashape", "GIS Pro", "سایر مهارت‌ها"],
    ["ادامه به مرحله بعد"]
]
KEYBOARD_SKILL_LEVEL = [["مبتدی", "متوسط", "پیشرفته"]]

# داده‌های دیتابیس برای ذخیره‌ی ساختار (کلیدهای داخلی)
# افزودن فیلدهای مربوط به عضویت سازمانی تا در ذخیره‌سازی و اکسپورت لحاظ شوند
RESUME_FIELDS = [
    "full_name", "username", "study_status", "degree", "major", "field_university", "gpa",
    "location", "phone_main", "phone_emergency", "english_level", "skills", "work_history",
    "job_position", "other_details", "training_request", "file_path", "register_date",
    # membership-related fields
    "has_membership", "membership_org", "membership_number", "membership_city"
]


SKILLS_LIST = ["GIS", "3D Max", "AutoCAD", "Metashape", "GIS Pro"]

# Mapping of internal field keys to Persian display labels used in edit UI
FIELD_LABELS = {
    "full_name": "نام و نام خانوادگی",
    "username": "آیدی تلگرام",
    "study_status": "وضعیت تحصیلی",
    "degree": "مقطع تحصیلی",
    "major": "رشته تحصیلی",
    "field_university": "دانشگاه / مؤسسه",
    "gpa": "معدل کل",
    "location": "محل سکونت",
    "phone_main": "تلفن همراه",
    "phone_emergency": "تلفن اضطراری",
    "english_level": "تسلط زبان انگلیسی",
    "skills": "مهارت‌ها",
    "work_history": "سابقه کار",
    "job_position": "جایگاه مدنظر",
    "other_details": "توضیحات دیگر",
    "training_request": "درخواست آموزش",
    "file_path": "مسیر نمونه‌کار",
    "register_date": "تاریخ ثبت",
    # membership-related (added for edit capability)
    "has_membership": "عضویت سازمانی",
    "membership_org": "نام سازمان/انجمن",
    "membership_number": "شماره عضویت",
    "membership_city": "شهر صدور عضویت"
}

# نمایش فارسی ساختار رزومه بر اساس ترتیب `RESUME_FIELDS` (برای اکسپورت/نمایش)
# این لیست از `FIELD_LABELS` ساخته می‌شود تا همیشه برچسب‌های فارسی هم‌ردیف با کلیدها فراهم باشد
RESUME_FIELDS_PERSIAN = [FIELD_LABELS.get(k, k) for k in RESUME_FIELDS]