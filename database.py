# database.py
import sqlite3
import json
import datetime
import pandas as pd
import config # وارد کردن کل ماژول config

class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(config.DATABASE_NAME)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        # جدول اصلی رزومه‌ها: ستون is_blocked برای قابلیت بلاک/آنبلاک اضافه شد
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS resumes (
                user_id INTEGER PRIMARY KEY,
                {', '.join([f'{field} TEXT' for field in config.RESUME_FIELDS])},
                is_admin_notified INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0
            )
        """)
        # جدول لاگ فعالیت‌ها
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                message TEXT
            )
        """)
        self.conn.commit()
        # Ensure all fields from config.RESUME_FIELDS exist as columns (migrate if needed)
        try:
            self.cursor.execute("PRAGMA table_info(resumes)")
            existing_cols = [row[1] for row in self.cursor.fetchall()]
            for field in config.RESUME_FIELDS:
                if field not in existing_cols:
                    self.cursor.execute(f"ALTER TABLE resumes ADD COLUMN {field} TEXT")
            self.conn.commit()
        except Exception:
            # If pragma/alter not supported or fails, ignore and continue (table already created earlier)
            pass

    def log(self, level, message):
        """ثبت رویداد در دیتابیس و فایل متنی"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
            (timestamp, level, message)
        )
        self.conn.commit()
        # ثبت در فایل متنی
        with open(config.LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

    def save_resume_data(self, user_id, data: dict):
        """ذخیره یا به‌روزرسانی اطلاعات رزومه کاربر"""
        # اگر فیلد مهارت‌ها لیست است، به JSON تبدیل شود
        if 'skills' in data and isinstance(data['skills'], list):
            data['skills'] = json.dumps(data['skills'], ensure_ascii=False)

        # برای جلوگیری از خطای SQL در صورت خالی بودن فیلدها، همیشه از لیست کامل فیلدها استفاده می‌کنیم
        fields = config.RESUME_FIELDS.copy()
        values = [data.get(k) for k in fields]

        field_placeholders = ', '.join(fields)
        value_placeholders = ', '.join(['?' for _ in fields])

        query = f"""
            INSERT OR REPLACE INTO resumes (user_id, {field_placeholders})
            VALUES (?, {value_placeholders})
        """

        # مقدمات پارامترها: user_id به عنوان اولین پارامتر
        params = (user_id, *values)
        self.cursor.execute(query, params)
        self.conn.commit()
        self.log("INFO", f"Resume data updated for User ID: {user_id}")
        
    def get_resume_data(self, user_id):
        """دریافت تمام اطلاعات یک کاربر"""
        self.cursor.execute("SELECT * FROM resumes WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        if row:
            columns = [col[0] for col in self.cursor.description]
            data = dict(zip(columns, row))
            if 'skills' in data and data['skills']:
                try:
                    data['skills'] = json.loads(data['skills'])
                except json.JSONDecodeError:
                    data['skills'] = []
            return data
        return None

    def get_resumes_for_export(self):
        self.cursor.execute("SELECT * FROM resumes")
        return self.cursor.fetchall(), [col[0] for col in self.cursor.description]
    
# database.py (فقط تابع export_to_excel اصلاح شده)

    def export_to_excel(self):
        """(مورد 3) تهیه خروجی اکسل از تمام رزومه‌ها"""
        rows, columns = self.get_resumes_for_export()
        if not rows:
            return False, "دیتابیس خالی است."
        
        df = pd.DataFrame(rows, columns=columns)
        
        if 'skills' in df.columns:
             # یک تابع کمکی برای تبدیل JSON امن تعریف می‌کنیم
             def format_skills(x):
                 if x and isinstance(x, str) and x.strip().startswith('['):
                     try:
                         skills_list = json.loads(x)
                         return "\n".join([f"{item['name']}: {item['level']}" for item in skills_list])
                     except json.JSONDecodeError:
                         return "خطای تبدیل JSON"
                 return x # برگرداندن مقدار اصلی در صورت خالی بودن، نبودن رشته یا خطا
                 
             df['skills'] = df['skills'].apply(format_skills)
        
        try:
            df.to_excel(config.EXCEL_OUTPUT, index=False, engine='openpyxl')
            self.log("INFO", f"Data exported to {config.EXCEL_OUTPUT}")
            return True, config.EXCEL_OUTPUT
        except Exception as e:
            self.log("ERROR", f"Failed to export Excel: {e}")
            return False, f"خطای سیستمی هنگام ساخت فایل اکسل: {e}"

    # ... (بقیه توابع DatabaseManager) ...

    # ===============================================
    #           توابع مورد نیاز پنل ادمین
    # ===============================================

    def get_user_by_search_term(self, term):
        """(مورد 1) جستجو بر اساس نام کامل، بخشی از نام یا یوزرنیم"""
        search_term = f'%{term.strip()}%'
        self.cursor.execute(
            "SELECT user_id, full_name, username FROM resumes WHERE full_name LIKE ? OR username LIKE ?",
            (search_term, search_term)
        )
        return self.cursor.fetchall() # (user_id, full_name, username)

    def get_stats(self, today_date_str):
        """(مورد 4) دریافت آمار کلی کاربران"""
        self.cursor.execute("SELECT COUNT(user_id) FROM resumes")
        total_users = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(user_id) FROM resumes WHERE register_date LIKE ?", (f'{today_date_str}%',))
        today_users = self.cursor.fetchone()[0]
        
        return total_users, today_users

    def delete_user(self, user_id):
        """(مورد 5) حذف کاربر از دیتابیس"""
        self.cursor.execute("DELETE FROM resumes WHERE user_id = ?", (user_id,))
        self.conn.commit()
        self.log("ADMIN", f"User {user_id} deleted from database.")
        
    def update_user_field(self, user_id, field_name, new_value):
        """(مورد 6 و 9) ویرایش یک فیلد خاص یا تغییر وضعیت بلاک/آنبلاک"""
        
        allowed_fields = config.RESUME_FIELDS + ['is_blocked', 'is_admin_notified']
        if field_name not in allowed_fields:
            self.log("ERROR", f"Attempted to update invalid field: {field_name}")
            return False
            
        # اگر فیلد مهارت‌ها بود، آن را به JSON تبدیل کن تا ساختار حفظ شود
        if field_name == 'skills':
            # در اینجا فرض بر این است که ادمین هنگام ویرایش، رشته JSON معتبری وارد می‌کند
            # یا منطق پیچیده‌تری در bot.py برای ویرایش مهارت‌ها در نظر گرفته شده است.
            # برای سادگی، اگر یک لیست بود به JSON تبدیل شود
            if isinstance(new_value, list):
                new_value = json.dumps(new_value, ensure_ascii=False)
        
        query = f"UPDATE resumes SET {field_name} = ? WHERE user_id = ?"
        self.cursor.execute(query, (new_value, user_id))
        self.conn.commit()
        self.log("ADMIN", f"User {user_id} field '{field_name}' updated to '{new_value}'.")
        return True

    def get_all_logs(self):
        """(مورد 10) دریافت آخرین لاگ‌های فعالیت"""
        self.cursor.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 500")
        return self.cursor.fetchall()
        
    def close(self):
        self.conn.close()