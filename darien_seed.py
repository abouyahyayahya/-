# -*- coding: utf-8 -*-
# darien_seed.py — Darien Center seeding + RTL marquee (Arabic UI)

import sqlite3
from contextlib import closing
import pandas as pd
import streamlit as st

CENTER_NAME = "مركز دارين التعليمي"
ADMIN_NAME  = "أ/ عبد الله علي عبد الباري"

# --- المعلمون والمواد وأيام العمل ---
TEACHERS = [
    {"name": "هشام محمود عمران",       "subjects": ["رياضيات"],                  "days": "حد وأربع"},
    {"name": "محمد إبراهيم أبو سيف",   "subjects": ["رياضيات"],                  "days": "اتنين وخميس"},
    {"name": "عبدالله زهير كيلاني",     "subjects": ["علوم"],                     "days": "سبت وتلات"},
    {"name": "محمد عادل أبو خليفه",     "subjects": ["عربي"],                     "days": "سبت وتلات"},
    {"name": "مصطفي نصر عبدالسميع",     "subjects": ["عربي"],                     "days": "سبت وتلات"},
    {"name": "محمود السيد ملش",         "subjects": ["انجليزي"],                   "days": "اتنين وخميس"},
    {"name": "صلاح الغمري",             "subjects": ["دراسات"],                   "days": "حد وأربع"},
    {"name": "هبه عبدالفتاح صيام",      "subjects": ["انجليزي"],                   "days": "اتنين وخميس"},
    {"name": "عبدالله علي عبدالباري",   "subjects": ["عربي","رياضيات","أصول دين"], "days": "كل يوم"},
]

SUBJECTS = ["عربي","رياضيات","علوم","انجليزي","دراسات","أصول دين"]

# --- الطلاب حسب الصفوف ---
CLASSES = {
    "الصف الأول الابتدائي": """
إسراء مسعود محمد
شمس زغلول محمد
شهد محمد أحمد
روڤان زغلول كامل
مكه رمضان هنداوي
سما صيام تمراز
سجده محمد جابر
سندس محمد جابر
حبيبه أحمد طه
هنا ممدوح القراجي
مكه محمد أحمد
إيمان قدري جوده
سلمي هاني فوزي
جويريه هشام الصافي
ريم محمد السيد
محمد رمضان تمراز
محمد رضا أبوسعده
عمر حسام جمال
مراد محمد إبراهيم
""",
    "الصف الثاني الابتدائي": """
محمد شعبان تمراز
آدم ناجي النجار
ياسين شحته النجار
يوسف عادل كامل
يوسف محمود كامل
يوسف محمد عبدالنبي
عمر محمد محمود
أحمد محمد علي
ياسين رضا زيدان
حازم محمد عبدالسلام
حمزه إسماعيل توفيق
عز عبدالجليل علي
أنس محمد سعد
محمد علي مسعود
محمدأحمدعطيه
زين أحمد تمراز
مالك أيمن شوقي
محمد صبري سعد
فارس خميس حسن
رهف محمود محمد
ياسمين عبدالرؤوف عبدالسلام
هاجر أحمد النجار
مياده رجب تمراز
أشرقت يحي حسنين
أشرقت ماهر حسن
حنين عبد الدايم عطيه
مريم رضا صبري
فرح أيمن عبدالحليم
""",
    "الصف الثالث الابتدائي": """
عبدالله محمد عبدالعزيز
محمود محمد محمود
يوسف محمد بخاطره
فهد هشام فهمي
يوسف سعيد عادل
كريم وليد محمد
محمداكرامي سعيد
مازن محمد محمود
محمد شحته النجار
ريم محمد السيد
لؤلؤه محمد اسماعيل
إيلين رضا المهدي
رضوي سعيد جمعه
رودينا السيد علي
ساندي كارم عبدالجواد
آمال ماهر إبراهيم
رودينا محمود جمعه
مريم يوسف محمد
هنا محمد عبدالواحد
همس عبدالجليل علي
سلامحمد عبدالفتاح
سيلين يوسف توفيق
""",
    "الصف الرابع الابتدائي": """
محمد فريد الصعيدي
محمدحسام جمال
إبراهيم محمد ابراهيم
محمد حسن علي
محمد سامي جلال
محمد بدر جلال
ياسين محمد سليمان
عمار رمضان هنداوي
أحمد يحي حسنين
سعدإبراهيم حسنين
محمدرجب السيد
أحمد منصور سعد
عمر الصافي سعد
محمد رجب عبدالكريم
روان هاني محمد
منه مصطفي مرعي
ملك أحمد مختار
شاهندا أيمن كمال
هايا أحمد البغدادي
ملك محمد السيد
جني إبراهيم جمعه
آلاء أحمد النجار
ميار رمضان تمراز
ريماس محمد أحمد
جني أيمن أحمد
سماح إبراهيم محمود
حبيبه الصافي عيد
سهيله محمد محمد
روفيدا محمود محمد
بسنت محمود كامل
سجده أيمن شوقي
ملك جمعه السيد
جني جمال مسعود
أشرقت أحمد طه
سندس عمرومحمود
آلاء محمد جمعه
""",
    "الصف الخامس الابتدائي": """
عمر محمد سليمان
سيف وليد محمد
حازم عرفه عطيه
حسن أيمن حسن
يوسف السيد علي
محمد سعيد محمد
معتز مدحت مسعود
أحمد حسن علي
يوسف رمضان عيد
يوسف شعبان أبو سعده
حسن محمد حسن
يوسف علي مسعود
حسني أحمد محمد
محمد أحمد محمد
جمال ياسر صبور
مالك ياسر صبور
آدم خميس حسن
أنس محمد عبدالعزيز
يوسف محمد عبدالعزيز
يوسف محمود سعد
محمد رمضان عبدالله
محمود كامل صيام
أحمد نصر قمبر
عبدالرحمن عبدالله محمد
محمد ماهر إبراهيم
رودينا عادل محمد
أمنيه أشرف محمد
إسراء محمد علي
أروي رضا المهدي
حنين خالد عيد
فاطمه محمود حسن
نورهان عماد عبدالحليم
جنات عادل كامل
نرمين أيمن عبدالحليم
جهاد ممدوح مسعود
شروق الطاهر تمراز
روڤان سعيد خيري
فرحه توفيق سعد
سجده حسام عبدالعظيم
ريناد عبدالله عبدالوهاب
ياسمين صبري سعد
إسراء محمد زكريا
أيات أشرف كامل
هاجر يحي توفيق
أسماء إسماعيل توفيق
ساندي هشام الصافي
فريحه محمد عبدالنبي
شمس حسن غازي
""",
    "الصف السادس الابتدائي": """
مصطفي محمود محمد
عمر عبده علي
مازن مدحت مسعود
عبدالرحمن خالد البغدادي
آدم سامي محمد
عبدالرحمن شعبان أبو سعده
أحمد محمد المهدي
إسلام رجب تمراز
محمد خالد بخاطره
محمد رمضان الدراسي
كريم محمد رمضان
محمد بدر أبو سعده
محمود محمد أحمد
محمد أمير محمد
مهند جمعه السيد
محمد عبدالدايم عطيه
عمرأحمد فكيه
محمد منصور سعد
حلمي عمر أبو الخير
ساندي ناجي النجار
شهد أحمد مختار
أسماء حسني محمود
جني محمد محمود
نور محمد محمود
رودينا حسام جمال
شاهندا محمود سعد
ملك فريد الصعيدي
رودينا سعيد عبده
ميرنا حسن إبراهيم
منه حسن كامل
شروق محمد جابر
جني أشرف طه
منه عاطف محمد
مايا أحمد البغدادي
""",
    "الصف الأول الإعدادي": """
محمد خميس النجار
عبدالرحمن سعيد عادل
محمدفوقي خليفه
عمرو رمضان سعد
محمد حسن غازي
ياسين محمد محمد
أحمد محمد زكريا
آدم رضا المهدي
معاذ محمد المهدي
محمد علاء جلال
مصطفي رضا عبدالحميد
مريم أحمد النجار
جيلان أحمد كامل
أسماء بدر جلال
جنات علاء جلال
جنه علاء جلال
روضه حسن سعد
ريماس جمال عبدالحميد
ملك سمير حسن
عمر ماهر عادل
محمدأحمد محمد
محمد جمال مسعود
ماهر محمد حسن
إبراهيم رابح إبراهيم
محمد رضا صبري
نور الدين ضاحي
أحمدوليد محمد
كريم مصطفي رمضان
محمد خطاب سعد
محمد إبراهيم جمعه
فارس اكرامي سعيد
ملك عمرو محمد
حبيبه حسن النجار
توجان عادل كامل
رودينا محمود محمد
""",
    "الصف الثاني الإعدادي": """
زياد محمد محمد
محمد توفيق سعد
أحمد صيام تمراز
أحمد محمود سعد
ياسين إبراهيم صيام
يوسف كامل صيام
روان السيد النجار
إيمان مؤمن تمراز
أحمد ناجي النجار
أحمد عبده علي
زياد حلمي علي
يوسف الطاهر تمراز
سعيد عبدالله أحمد
كريم صبري تمراز
أحمد عيد خميس
""",
    "الصف الثالث الإعدادي": """
مازن حسن كامل
حسن محمد عبد المنعم
محمد أحمد شعبان
أميره فوقي خليفه
شمس أيمن قمبر
رنا أسامه عبدالمجيد
رودينا زغلول كامل
ملك رجب عبدالحميد
محمد نصر علي
أحمد حسام عبدالعظيم
حسن ماهر حسن
زياد حسن إبراهيم
رضوي عرفه عطيه
رحمه شعبان تمراز
هبة الله يحي توفيق
"""
}

NOISE = set(["تعليم","تعلييييم","تعليييييم","أزهر","أزهر ","تعليم "])

DEFAULT_TEACHER_FOR_SUBJECT = {
    "رياضيات": "محمد إبراهيم أبو سيف",
    "عربي":    "محمد عادل أبو خليفه",
    "علوم":    "عبدالله زهير كيلاني",
    "انجليزي": "محمود السيد ملش",
    "دراسات":  "صلاح الغمري",
    "أصول دين":"عبدالله علي عبدالباري",
}

def _get_id(conn, q, p=()):
    with closing(conn.cursor()) as cur:
        cur.execute(q, p); r = cur.fetchone()
        return r[0] if r else None

def ensure_darien_seed(conn):
    # مواد
    for s in SUBJECTS:
        sid = _get_id(conn, "SELECT id FROM subjects WHERE name=?", (s,))
        if not sid:
            conn.execute("INSERT INTO subjects(name) VALUES (?)", (s,))
    conn.commit()

    # معلمون (users.role='teacher') + جدول أسبوعي عام
    from passlib.hash import bcrypt
    for t in TEACHERS:
        email = f"{t['name']}.teacher@darien.local".replace(" ", "").replace("ـ","")
        tid = _get_id(conn, "SELECT id FROM users WHERE email=?", (email,))
        if not tid:
            conn.execute(
                "INSERT INTO users(full_name,email,role,password_hash) VALUES (?,?,?,?)",
                (t["name"], email, "teacher", bcrypt.hash("123456"))
            )
            tid = _get_id(conn, "SELECT id FROM users WHERE email=?", (email,))
        for subj in t["subjects"]:
            sid = _get_id(conn, "SELECT id FROM subjects WHERE name=?", (subj,))
            if sid:
                exists = _get_id(conn, """
                    SELECT id FROM weekly_schedule
                    WHERE class_name=? AND day_of_week=? AND subject_id=? AND teacher_id=?""",
                    ("كل الصفوف", t["days"], sid, tid)
                )
                if not exists:
                    conn.execute("""INSERT INTO weekly_schedule(class_name,day_of_week,subject_id,teacher_id)
                                    VALUES (?,?,?,?)""", ("كل الصفوف", t["days"], sid, tid))
    conn.commit()

    # المدير – لو مش موجود
    adm = _get_id(conn, "SELECT id FROM users WHERE role='admin'")
    if not adm:
        conn.execute(
            "INSERT INTO users(full_name,email,role,password_hash) VALUES (?,?,?,?)",
            (ADMIN_NAME, "admin@darien.local", "admin", bcrypt.hash("admin"))
        )
        conn.commit()

    # الطلاب بحسب الصفوف (مرتّبين أبجديًا) — لا نكرر لو موجودين
    existing = _get_id(conn, "SELECT COUNT(*) FROM students")
    if existing and existing > 0:
        return

    for class_name, block in CLASSES.items():
        names = [l.strip().replace("  "," ") for l in block.splitlines() if l.strip()]
        names = [n for n in names if n not in NOISE]
        names.sort()
        for full in names:
            conn.execute("INSERT INTO students(full_name,class_name) VALUES (?,?)", (full, class_name))
    conn.commit()

    # تعيين افتراضي: كل طالب ↔ مادة ↔ معلّم افتراضي
    students = pd.read_sql_query("SELECT id FROM students", conn)["id"].tolist()
    for subj, tname in DEFAULT_TEACHER_FOR_SUBJECT.items():
        sid = _get_id(conn, "SELECT id FROM subjects WHERE name=?", (subj,))
        tid = _get_id(conn, "SELECT id FROM users WHERE full_name=? AND role='teacher'", (tname,))
        if not sid or not tid:
            continue
        with closing(conn.cursor()) as cur:
            for stu in students:
                cur.execute("""SELECT 1 FROM enrollments WHERE student_id=? AND subject_id=?""", (stu, sid))
                if not cur.fetchone():
                    cur.execute("""INSERT INTO enrollments(student_id,subject_id,teacher_id) VALUES (?,?,?)""",
                                (stu, sid, tid))
        conn.commit()

def render_marquee(conn):
    # شريط متحرك RTL بطيء: المركز + المدير + المعلمون/موادهم/أيامهم
    teachers_bits = [f"{t['name']} — {' و '.join(t['subjects'])} — {t['days']}" for t in TEACHERS]
    teachers_str = " • ".join(teachers_bits)
    text = f"{CENTER_NAME} — المدير: {ADMIN_NAME} — المعلمون وموادهم وأيامهم: {teachers_str}"

    st.markdown("""
    <style>
    .darien-marquee-wrap{
        direction: rtl; overflow: hidden; white-space: nowrap;
        border: 1px solid #e5e7eb; background: #fff; border-radius: 12px;
        padding: 8px 0; margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }
    .darien-marquee{
        display: inline-block;
        padding-inline-start: 100%;
        animation: darien-scroll 60s linear infinite; /* بطيء */
        font-weight: 700; color: #0D1117;
    }
    @keyframes darien-scroll {
        0%   { transform: translateX(0%); }
        100% { transform: translateX(-100%); }
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="darien-marquee-wrap">
      <div class="darien-marquee">{text}</div>
    </div>
    """, unsafe_allow_html=True)

__all__ = ["ensure_darien_seed", "render_marquee"]
