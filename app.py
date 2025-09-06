# -*- coding: utf-8 -*-
import os, sqlite3, math, statistics as stats
from contextlib import closing
import datetime as dt
import pandas as pd
import streamlit as st
import altair as alt
from passlib.hash import bcrypt

# ===================== إعداد آمن لقراءة الإعدادات =====================

def get_setting(key, default=None):
    """اقرأ من متغيرات البيئة أولًا، ثم من st.secrets بدون إسقاط التطبيق."""
    v = os.getenv(key)
    if v:
        return v
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

DB_PATH = get_setting("GRADES_DB_PATH", "/opt/render/project/src/grades.db")
UNIFIED_PASSWORD = get_setting("DARIEN_UNIFIED_PASSWORD", "123456")
WHATSAPP_E164 = get_setting("WHATSAPP_E164", "+201015477265")
BACKEND_URL = get_setting("BACKEND_URL", "")  # اختياري
OWNER_EMAIL = get_setting("OWNER_EMAIL", None)       # لتهيئة المالك
OWNER_PASSWORD = get_setting("OWNER_PASSWORD", None) # لتهيئة المالك

QURAN_YT = "https://www.youtube.com/embed/m7tva04iQv4?autoplay=1&mute=1&loop=1&playlist=m7tva04iQv4"

st.set_page_config(page_title="📊 تطبيق الدرجات — متعدد المراكز", page_icon="📊", layout="wide")

# ===================== بذرة اختيارية =====================
try:
    from darien_seed import ensure_darien_seed, render_marquee as seed_render_marquee
except Exception:
    ensure_darien_seed = None
    seed_render_marquee = None

# ===================== أدوات DB =====================

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn


def has_column(conn, table, col):
    q = "PRAGMA table_info(%s)" % table
    with closing(conn.cursor()) as cur:
        cur.execute(q)
        return any(r[1] == col for r in cur.fetchall())


def ensure_schema_and_migrations(conn):
    """إنشاء/ترقية المخطط: دعم تعدد المراكز، جداول الحصص، مخطط الدرجات، وحقول min/max للدرجات، وجدول المالكين."""
    with closing(conn.cursor()) as cur:
        # المالكين (Super Admins)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL DEFAULT 'مالك التطبيق',
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            """
        )

        # مراكز
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS centers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                address TEXT,
                phone TEXT
            );
            """
        )

        # الجداول الأساسية
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','teacher')),
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                class_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                grade_date TEXT NOT NULL,
                score REAL NOT NULL,
                note TEXT,
                note_teacher TEXT,
                note_parent TEXT,
                note_admin TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                att_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present','absent_excused','absent_unexcused')),
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS student_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS guardian_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS guardian_student (
                guardian_id INTEGER NOT NULL REFERENCES guardian_accounts(id) ON DELETE CASCADE,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                PRIMARY KEY (guardian_id, student_id)
            );
            """
        )

        # إضافة center_id للجداول إن لم يوجد
        tables_to_center = [
            "users", "students", "subjects", "enrollments", "grades", "attendance", "student_accounts"
        ]
        for t in tables_to_center:
            if not has_column(conn, t, "center_id"):
                cur.execute(f"ALTER TABLE {t} ADD COLUMN center_id INTEGER DEFAULT 1")

        # min/max للدرجات
        if not has_column(conn, "grades", "min_score"):
            cur.execute("ALTER TABLE grades ADD COLUMN min_score REAL")
        if not has_column(conn, "grades", "max_score"):
            cur.execute("ALTER TABLE grades ADD COLUMN max_score REAL")

        # جداول الحصص
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                center_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                day_of_week INTEGER NOT NULL,  -- 0=Mon .. 6=Sun
                start_time TEXT NOT NULL,
                end_time   TEXT NOT NULL
            );
            """
        )

        # مخطط الدرجات
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS grading_scheme (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                center_id INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                subject_id INTEGER,
                min_score REAL NOT NULL DEFAULT 0,
                max_score REAL NOT NULL DEFAULT 100,
                excellent_cut REAL,
                high_cut REAL,
                average_cut REAL
            );
            """
        )

        # فهارس
        cur.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_users_center ON users(center_id);
            CREATE INDEX IF NOT EXISTS idx_students_center ON students(center_id);
            CREATE INDEX IF NOT EXISTS idx_subjects_center ON subjects(center_id);
            CREATE INDEX IF NOT EXISTS idx_enroll_center ON enrollments(center_id);
            CREATE INDEX IF NOT EXISTS idx_grades_center ON grades(center_id);
            CREATE INDEX IF NOT EXISTS idx_lessons_center ON lessons(center_id);
            CREATE INDEX IF NOT EXISTS idx_scheme_center ON grading_scheme(center_id);
            """
        )
        conn.commit()

        # مركز افتراضي + إسناد center_id=1
        cur.execute("SELECT COUNT(*) FROM centers")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO centers(name) VALUES ('مركز دارين التعليمي')")
            conn.commit()

        # تأكد أن كل السجلات لها center_id
        for t in tables_to_center:
            cur.execute(f"UPDATE {t} SET center_id=1 WHERE center_id IS NULL")
        conn.commit()

        # تهيئة مالك التطبيق إن لم يوجد
        cur.execute("SELECT COUNT(*) FROM owners")
        if cur.fetchone()[0] == 0:
            email = OWNER_EMAIL or "owner@darien.local"
            pw = OWNER_PASSWORD or "owner"
            cur.execute("INSERT INTO owners(full_name,email,password_hash) VALUES (?,?,?)",
                        ("مالك التطبيق", email, bcrypt.hash(pw)))
            conn.commit()


def get_current_center_id(conn):
    if "center_id" not in st.session_state:
        with closing(conn.cursor()) as cur:
            cur.execute("SELECT id FROM centers ORDER BY id LIMIT 1")
            st.session_state["center_id"] = cur.fetchone()[0]
    return st.session_state["center_id"]

# ===================== تنسيق عام =====================

def render_global_style():
    st.markdown(
        """
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
    <link href=\"https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap\" rel=\"stylesheet\">
    <style>
      html, body, [data-testid=\"stAppViewContainer\"] { direction: rtl !important; font-family: \"Cairo\", system-ui, -apple-system, \"Segoe UI\", \"Noto Kufi Arabic\", Arial, sans-serif !important; }
      h1, h2, h3, h4, h5, h6, label, .st-emotion-cache-1cypcdb { color: #111827; }
      .darien-card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
      .wa-fab{ position: fixed; right: 16px; top: 120px; z-index: 9999; background: #25D366; color: #fff; padding: 12px 16px; border-radius: 999px; box-shadow: 0 6px 16px rgba(0,0,0,.12); text-decoration: none; font-weight: 700; }
      .badge-qual{ display:inline-block; background:#eef2ff; color:#1e40af; padding:2px 8px; border-radius:12px; margin-inline-start:8px; }
      .darien-marquee-wrap{ direction: rtl; overflow: hidden; white-space: nowrap; border: 1px solid #e5e7eb; background: #ffffff; border-radius: 12px; padding: 8px 0; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
      .darien-marquee{ display: inline-block; padding-inline-start: 100%; animation: darien-scroll 240s linear infinite; font-weight: 600; color: #0D1117; }
      @keyframes darien-scroll { 0% { transform: translateX(0%); } 100% { transform: translateX(-100%); } }
    </style>
    """,
        unsafe_allow_html=True,
    )

render_global_style()

# ===================== إنشاء/ترحيل المخطط =====================
conn = get_conn()
ensure_schema_and_migrations(conn)

# مدير افتراضي إن لم يوجد (للمركز 1)
with closing(conn.cursor()) as cur:
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users(full_name,email,role,password_hash,center_id) VALUES (?,?,?,?,1)",
            ("المدير", "admin@darien.local", "admin", bcrypt.hash("admin")),
        )
        conn.commit()

# ===================== أدوات مساعدة =====================

def qualitative_label(score, class_avg=None, class_std=None):
    if class_avg is not None and class_std is not None and class_std > 0:
        if score >= class_avg + class_std: return "متفوق"
        if score >= class_avg: return "مرتفع"
        if score >= class_avg - class_std: return "متوسط"
        return "منخفض"
    if score >= 90: return "متفوق"
    if score >= 75: return "مرتفع"
    if score >= 50: return "متوسط"
    return "منخفض"


def user_by_email(conn, email, center_id):
    with closing(conn.cursor()) as cur:
        cur.execute(
            "SELECT id, full_name, email, role, password_hash FROM users WHERE email=? AND center_id=?",
            (email, center_id),
        )
        r = cur.fetchone()
    if r:
        return {"id": r[0], "full_name": r[1], "email": r[2], "role": r[3], "password_hash": r[4]}
    return None

# ===================== شريط التحفيز + واتساب =====================
MOTIV = [f"عبارة تحفيزية تربوية رقم {i} — اجتهد اليوم لتتقدم غدًا." for i in range(1, 301)]

def render_marquee_base():
    text = "  •  ".join(MOTIV)
    st.markdown(
        f"""
    <div class=\"darien-marquee-wrap\">
      <div class=\"darien-marquee\">{text}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_whatsapp_fab():
    st.markdown(
        f"""
      <a class=\"wa-fab\" href=\"https://wa.me/{WHATSAPP_E164.lstrip('+')}\" target=\"_blank\" title=\"التواصل عبر واتساب\">
        التظلّم عبر واتساب
      </a>
    """,
        unsafe_allow_html=True,
    )

# ===================== اختيار المركز =====================

def sidebar_center_selector(conn):
    centers = pd.read_sql_query("SELECT id, name FROM centers ORDER BY name", conn)
    if centers.empty:
        st.sidebar.error("لا توجد مراكز.")
        return 1
    if "center_id" not in st.session_state:
        st.session_state["center_id"] = int(centers.iloc[0,0])
    mapping = dict(zip(centers["name"], centers["id"]))
    current = st.session_state["center_id"]
    sel = st.sidebar.selectbox("🧭 اختر المركز", centers["name"], index=list(centers["id"]).index(current))
    st.session_state["center_id"] = mapping[sel]
    return mapping[sel]

# ===================== تسجيل الدخول =====================

def login_any(conn, center_id):
    st.subheader("تسجيل الدخول")
    email = st.text_input("البريد الإلكتروني", key="login_email")
    password = st.text_input("كلمة المرور", type="password", key="login_password")

    if password and not st.session_state.get("quran_muted_started"):
        st.components.v1.html(
            f'<iframe width="0" height="0" src="{QURAN_YT}" frameborder="0" allow="autoplay" style="display:none"></iframe>',
            height=0,
        )
        st.session_state["quran_muted_started"] = True

    if st.button("دخول", type="primary", key="login_button"):
        # 0) مالك التطبيق أولاً (لا يعتمد على center_id)
        with closing(conn.cursor()) as cur:
            cur.execute("SELECT id, full_name, email, password_hash FROM owners WHERE email=?", (email.strip(),))
            ow = cur.fetchone()
        if ow and bcrypt.verify(password, ow[3]):
            return {"kind": "owner", "id": ow[0], "full_name": ow[1], "email": ow[2], "role": "owner"}

        # 1) مستخدم (معلم/مدير) ضمن المركز المحدّد
        u = user_by_email(conn, email.strip(), center_id)
        if u:
            if u["role"] == "admin":
                if bcrypt.verify(password, u["password_hash"]):
                    return {"kind": "user", **{k: u[k] for k in ("id","full_name","email","role")}}
            else:  # teacher
                if password == UNIFIED_PASSWORD or bcrypt.verify(password, u["password_hash"]):
                    return {"kind": "user", **{k: u[k] for k in ("id","full_name","email","role")}}

        # 2) طالب ضمن نفس المركز
        with closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT sa.id, sa.student_id, s.full_name, sa.email, sa.password_hash
                FROM student_accounts sa JOIN students s ON s.id=sa.student_id
                WHERE sa.email=? AND sa.center_id=?
                """,
                (email.strip(), center_id),
            )
            srow = cur.fetchone()
        if srow and (password == UNIFIED_PASSWORD or bcrypt.verify(password, srow[4])):
            return {"kind":"student","account_id":srow[0],"student_id":srow[1],"full_name":srow[2],"email":srow[3],"role":"student"}

        st.error("بيانات الدخول غير صحيحة")
    return None

# ===================== إدارة كمالك (Owners) =====================

def owner_panel(conn):
    st.header("🏢 إدارة المراكز (خاص بالمالك)")
    # إدارة المراكز
    centers = pd.read_sql_query("SELECT id, name, address, phone FROM centers ORDER BY id", conn)
    edited = st.data_editor(centers, use_container_width=True, num_rows="dynamic", disabled=["id"], key="edit_centers")
    if st.button("حفظ تعديلات المراكز"):
        old = centers.set_index("id")
        new = edited.set_index("id")
        for cid in new.index:
            if cid in old.index:
                if not (old.loc[cid] == new.loc[cid]).all():
                    conn.execute("UPDATE centers SET name=?, address=?, phone=? WHERE id=?", (new.loc[cid,"name"], new.loc[cid,"address"], new.loc[cid,"phone"], int(cid)))
            else:
                conn.execute("INSERT INTO centers(name,address,phone) VALUES (?,?,?)", (new.loc[cid,"name"], new.loc[cid,"address"], new.loc[cid,"phone"]))
        removed = set(old.index) - set(new.index)
        for cid in removed:
            conn.execute("DELETE FROM centers WHERE id=?", (int(cid),))
        conn.commit(); st.success("تم حفظ المراكز")

    st.markdown("---")
    st.subheader("👤 إنشاء مدير لمركز")
    centers2 = pd.read_sql_query("SELECT id, name FROM centers ORDER BY name", conn)
    if centers2.empty:
        st.info("أضف مركزًا أولًا")
    else:
        c = st.selectbox("المركز", centers2["id"], format_func=lambda i: centers2.set_index('id').loc[i,'name'])
        name = st.text_input("اسم المدير")
        email = st.text_input("إيميل المدير")
        pw = st.text_input("كلمة المرور", type="password")
        if st.button("إنشاء حساب المدير"):
            try:
                conn.execute(
                    "INSERT INTO users(full_name,email,role,password_hash,center_id) VALUES (?,?,?,?,?)",
                    (name.strip(), email.strip(), "admin", bcrypt.hash(pw if pw else UNIFIED_PASSWORD), int(c)),
                )
                conn.commit(); st.success("تم إنشاء حساب المدير")
            except sqlite3.IntegrityError:
                st.error("هذا البريد مستخدم بالفعل")

# ===================== إدارة المخطط: الطلاب/المعلمين/المواد/الحصص/مخطط الدرجات =====================

def admin_edit_students(conn, center_id):
    st.markdown("### 👥 إدارة الطلاب")
    df = pd.read_sql_query("SELECT id, full_name, class_name FROM students WHERE center_id=? ORDER BY class_name, full_name", conn, params=[center_id])
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", disabled=["id"], key=f"edit_students_{center_id}")
    if st.button("حفظ تعديلات الطلاب"):
        old = df.set_index("id"); new = edited.set_index("id")
        for sid in new.index:
            if sid in old.index:
                if not (old.loc[sid] == new.loc[sid]).all():
                    conn.execute("UPDATE students SET full_name=?, class_name=? WHERE id=? AND center_id=?", (new.loc[sid,"full_name"], new.loc[sid,"class_name"], int(sid), center_id))
            else:
                conn.execute("INSERT INTO students(full_name, class_name, center_id) VALUES (?,?,?)", (new.loc[sid,"full_name"], new.loc[sid,"class_name"], center_id))
        removed = set(old.index) - set(new.index)
        for sid in removed:
            conn.execute("DELETE FROM students WHERE id=? AND center_id=?", (int(sid), center_id))
        conn.commit(); st.success("تم حفظ تعديلات الطلاب")


def admin_edit_teachers(conn, center_id):
    st.markdown("### 🧑‍🏫 إدارة المعلمين")
    df = pd.read_sql_query("SELECT id, full_name, email FROM users WHERE role='teacher' AND center_id=? ORDER BY full_name", conn, params=[center_id])
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", disabled=["id"], key=f"edit_teachers_{center_id}")
    if st.button("حفظ تعديلات المعلمين"):
        old = df.set_index("id"); new = edited.set_index("id")
        for tid in new.index:
            if tid in old.index:
                if not (old.loc[tid] == new.loc[tid]).all():
                    conn.execute("UPDATE users SET full_name=?, email=? WHERE id=? AND center_id=?", (new.loc[tid,"full_name"], new.loc[tid,"email"], int(tid), center_id))
            else:
                pw_hash = bcrypt.hash(UNIFIED_PASSWORD)
                conn.execute("INSERT INTO users(full_name,email,role,password_hash,center_id) VALUES (?,?,?,?,?)", (new.loc[tid,"full_name"], new.loc[tid,"email"], "teacher", pw_hash, center_id))
        removed = set(old.index) - set(new.index)
        for tid in removed:
            conn.execute("DELETE FROM users WHERE id=? AND center_id=? AND role='teacher'", (int(tid), center_id))
        conn.commit(); st.success("تم حفظ تعديلات المعلمين")


def admin_edit_subjects(conn, center_id):
    st.markdown("### 📚 إدارة المواد")
    df = pd.read_sql_query("SELECT id, name FROM subjects WHERE center_id=? ORDER BY name", conn, params=[center_id])
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", disabled=["id"], key=f"edit_subjects_{center_id}")
    if st.button("حفظ تعديلات المواد"):
        old = df.set_index("id"); new = edited.set_index("id")
        for sid in new.index:
            if sid in old.index:
                if not (old.loc[sid] == new.loc[sid]).all():
                    conn.execute("UPDATE subjects SET name=? WHERE id=? AND center_id=?", (new.loc[sid,"name"], int(sid), center_id))
            else:
                conn.execute("INSERT INTO subjects(name, center_id) VALUES (?,?)", (new.loc[sid,"name"], center_id))
        removed = set(old.index) - set(new.index)
        for sid in removed:
            conn.execute("DELETE FROM subjects WHERE id=? AND center_id=?", (int(sid), center_id))
        conn.commit(); st.success("تم حفظ تعديلات المواد")


def admin_manage_lessons(conn, center_id):
    st.markdown("### 🗓️ جداول الحصص والمواعيد")
    days = ["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]

    studs_classes = pd.read_sql_query("SELECT DISTINCT class_name FROM students WHERE center_id=? ORDER BY class_name", conn, params=[center_id])
    subs = pd.read_sql_query("SELECT id, name FROM subjects WHERE center_id=? ORDER BY name", conn, params=[center_id])
    teach = pd.read_sql_query("SELECT id, full_name FROM users WHERE role='teacher' AND center_id=? ORDER BY full_name", conn, params=[center_id])

    with st.form("add_lesson"):
        c = st.selectbox("الصف/الفصل", studs_classes["class_name"]) if not studs_classes.empty else st.text_input("الصف/الفصل")
        subj = st.selectbox("المادة", subs["id"], format_func=lambda i: subs.set_index('id').loc[i,'name']) if not subs.empty else st.number_input("معرّف المادة", step=1)
        t = st.selectbox("المعلم", teach["id"], format_func=lambda i: teach.set_index('id').loc[i,'full_name']) if not teach.empty else st.number_input("معرّف المعلّم", step=1)
        d = st.selectbox("اليوم", list(range(7)), format_func=lambda i: days[i])
        start = st.time_input("من")
        end = st.time_input("إلى")
        if st.form_submit_button("إضافة/حجز الحصّة"):
            conn.execute(
                "INSERT INTO lessons(center_id,class_name,subject_id,teacher_id,day_of_week,start_time,end_time) VALUES (?,?,?,?,?,?,?)",
                (center_id, c, int(subj), int(t), int(d), start.strftime('%H:%M'), end.strftime('%H:%M')),
            )
            conn.commit(); st.success("تمت إضافة الحصة")

    st.markdown("#### الحصص المسجلة")
    df = pd.read_sql_query(
        """
        SELECT l.id, l.class_name AS "الصف", s.name AS "المادة", u.full_name AS "المعلم",
               l.day_of_week AS "اليوم", l.start_time AS "من", l.end_time AS "إلى"
        FROM lessons l JOIN subjects s ON s.id=l.subject_id JOIN users u ON u.id=l.teacher_id
        WHERE l.center_id=? ORDER BY l.class_name, l.day_of_week, l.start_time
        """,
        conn,
        params=[center_id],
    )
    st.dataframe(df, use_container_width=True)


def admin_manage_grading_scheme(conn, center_id):
    st.markdown("### 🧮 مخطط الدرجات (حد أدنى/أقصى وعتبات نوعية)")
    classes = pd.read_sql_query("SELECT DISTINCT class_name FROM students WHERE center_id=? ORDER BY class_name", conn, params=[center_id])
    subs = pd.read_sql_query("SELECT id, name FROM subjects WHERE center_id=? ORDER BY name", conn, params=[center_id])
    with st.form("scheme"):
        c = st.selectbox("الصف", classes["class_name"]) if not classes.empty else st.text_input("الصف")
        subj = st.selectbox("المادة (اختياري)", [None] + subs["id"].tolist(), format_func=lambda i: "— كل المواد —" if i is None else subs.set_index('id').loc[i,'name']) if not subs.empty else None
        min_s = st.number_input("الدرجة الدنيا", value=0.0, step=0.5)
        max_s = st.number_input("الدرجة العظمى", value=100.0, step=0.5)
        excellent = st.number_input("حد 'متفوق' %", value=90.0, step=1.0)
        high = st.number_input("حد 'مرتفع' %", value=75.0, step=1.0)
        avg = st.number_input("حد 'متوسط' %", value=50.0, step=1.0)
        if st.form_submit_button("حفظ/تحديث المخطط"):
            conn.execute(
                "INSERT INTO grading_scheme(center_id,class_name,subject_id,min_score,max_score,excellent_cut,high_cut,average_cut) VALUES (?,?,?,?,?,?,?,?)",
                (center_id, c, None if subj is None else int(subj), float(min_s), float(max_s), float(excellent), float(high), float(avg)),
            )
            conn.commit(); st.success("تم حفظ المخطط")

    st.markdown("#### المخططات المسجلة")
    df = pd.read_sql_query(
        "SELECT id, class_name AS 'الصف', subject_id AS 'مادة#', min_score AS 'الدنيا', max_score AS 'العظمى', excellent_cut AS '%متفوق', high_cut AS '%مرتفع', average_cut AS '%متوسط' FROM grading_scheme WHERE center_id=? ORDER BY class_name, subject_id",
        conn,
        params=[center_id],
    )
    st.dataframe(df, use_container_width=True)

# ===================== لوحات واجهة الاستخدام =====================

def honor_board_top10(conn, center_id, class_name=None, subject_id=None, date_iso=None):
    where = "WHERE g.center_id=?"; params = [center_id]
    if class_name: where += " AND s.class_name=?"; params.append(class_name)
    if subject_id: where += " AND g.subject_id=?"; params.append(subject_id)
    if date_iso: where += " AND g.grade_date=?" ; params.append(date_iso)
    q = f"""
    SELECT s.full_name AS student, s.class_name AS class, g.subject_id, sub.name AS subject, g.grade_date, g.score
    FROM grades g JOIN students s ON s.id=g.student_id JOIN subjects sub ON sub.id=g.subject_id
    {where} ORDER BY g.score DESC
    """
    df = pd.read_sql_query(q, conn, params=params)
    if df.empty: return df
    n = len(df); k = max(1, math.ceil(n * 0.10))
    return df.head(k)


def admin_panel(conn, center_id):
    tabs = st.tabs(["👥 الطلاب","📚 المواد","🧑‍🏫 المعلمون","🔗 التعيينات","🗓️ الحصص","🧮 مخطط الدرجات","📈 التقارير","🏅 المجتهدون"])
    with tabs[0]:
        order = st.selectbox("طريقة الفرز", ["الصف ثم الاسم","الاسم","الصف فقط","أحدث إضافة"], index=0)
        order_sql = {"الصف ثم الاسم": "ORDER BY class_name, full_name","الاسم": "ORDER BY full_name","الصف فقط": "ORDER BY class_name","أحدث إضافة": "ORDER BY id DESC"}[order]
        df_students = pd.read_sql_query(f"SELECT id AS 'رقم', full_name AS 'الاسم الكامل', class_name AS 'الصف' FROM students WHERE center_id=? {order_sql}", conn, params=[center_id])
        st.dataframe(df_students, use_container_width=True)
        st.markdown("---"); admin_edit_students(conn, center_id)
    with tabs[1]: admin_edit_subjects(conn, center_id)
    with tabs[2]: admin_edit_teachers(conn, center_id)
    with tabs[3]:
        st.markdown("**تعيين طالب ↔ مادة ↔ معلّم**")
        studs = pd.read_sql_query("SELECT id, full_name, class_name FROM students WHERE center_id=? ORDER BY class_name, full_name", conn, params=[center_id])
        subs  = pd.read_sql_query("SELECT id, name FROM subjects WHERE center_id=? ORDER BY name", conn, params=[center_id])
        teach = pd.read_sql_query("SELECT id, full_name, email FROM users WHERE role='teacher' AND center_id=? ORDER BY full_name", conn, params=[center_id])
        if studs.empty or subs.empty or teach.empty:
            st.info("أضف طلاب/مواد/معلمين أولاً.")
        else:
            sid = st.selectbox("طالب", studs["id"], format_func=lambda i: f"{studs.set_index('id').loc[i,'full_name']} - {studs.set_index('id').loc[i,'class_name']}")
            subid= st.selectbox("مادة", subs["id"], format_func=lambda i: subs.set_index('id').loc[i,'name'])
            tid  = st.selectbox("معلّم", teach["id"], format_func=lambda i: f"{teach.set_index('id').loc[i,'full_name']} ({teach.set_index('id').loc[i,'email']})")
            if st.button("تعيين"):
                conn.execute("INSERT INTO enrollments(student_id,subject_id,teacher_id,center_id) VALUES (?,?,?,?)", (int(sid), int(subid), int(tid), center_id))
                conn.commit(); st.success("تم التعيين")
        st.markdown("**التعيينات الحالية**")
        q = """
        SELECT e.id AS "#", s.full_name AS "الطالب", s.class_name AS "الصف", sub.name AS "المادة", u.full_name AS "المعلم"
        FROM enrollments e JOIN students s ON s.id=e.student_id JOIN subjects sub ON sub.id=e.subject_id JOIN users u ON u.id=e.teacher_id
        WHERE e.center_id=? ORDER BY "الصف", "الطالب", "المادة"
        """
        st.dataframe(pd.read_sql_query(q, conn, params=[center_id]), use_container_width=True)
    with tabs[4]: admin_manage_lessons(conn, center_id)
    with tabs[5]: admin_manage_grading_scheme(conn, center_id)
    with tabs[6]:
        c1,c2 = st.columns(2)
        fd = c1.date_input("من تاريخ", value=None); td = c2.date_input("إلى تاريخ", value=None)
        params=[center_id]; where="WHERE g.center_id=?"
        if fd: where += " AND g.grade_date >= ?"; params.append(fd.isoformat())
        if td: where += " AND g.grade_date <= ?"; params.append(td.isoformat())
        q = f"""
        SELECT g.id AS "#", g.grade_date AS "التاريخ", s.full_name AS "الطالب", s.class_name AS "الصف", sub.name AS "المادة",
               u.full_name AS "المعلم", g.score AS "الدرجة", g.min_score AS "الدنيا", g.max_score AS "العظمى",
               g.note AS "ملاحظة للطالب", g.note_teacher AS "ملاحظة للمعلم", g.note_parent AS "ملاحظة لولي الأمر", g.note_admin AS "ملاحظة للمدير"
        FROM grades g JOIN students s ON s.id=g.student_id JOIN subjects sub ON sub.id=g.subject_id JOIN users u ON u.id=g.teacher_id
        {where} ORDER BY g.grade_date DESC
        """
        df = pd.read_sql_query(q, conn, params=params)
        st.dataframe(df, use_container_width=True)
    with tabs[7]:
        classes = pd.read_sql_query("SELECT DISTINCT class_name FROM students WHERE center_id=? ORDER BY class_name", conn, params=[center_id])
        subs = pd.read_sql_query("SELECT id, name FROM subjects WHERE center_id=? ORDER BY name", conn, params=[center_id])
        if classes.empty or subs.empty:
            st.info("أضف طلابًا وموادًا أولًا.")
        else:
            c = st.selectbox("اختر الصف", classes["class_name"]) 
            s = st.selectbox("اختر المادة", subs["id"], format_func=lambda i: subs.set_index('id').loc[i,'name'])
            d = st.date_input("اختر التاريخ", value=dt.date.today())
            df = honor_board_top10(conn, center_id, c, int(s), d.isoformat())
            if df.empty:
                st.info("لا بيانات لهذا الاختيار.")
            else:
                df.rename(columns={"student":"الطالب","class":"الصف","subject":"المادة","grade_date":"التاريخ","score":"الدرجة"}, inplace=True)
                st.dataframe(df[["الطالب","الصف","المادة","التاريخ","الدرجة"]], use_container_width=True)

# ===================== لوحة المعلّم =====================

def teacher_daily_panel(conn, center_id, user):
    st.subheader("🗓️ إدخال الدرجات اليومية")
    teacher_classes = pd.read_sql_query(
        """
        SELECT DISTINCT s.class_name
        FROM enrollments e JOIN students s ON s.id = e.student_id
        WHERE e.teacher_id = ? AND e.center_id=?
        ORDER BY s.class_name
    """, conn, params=[user["id"], center_id])
    if teacher_classes.empty:
        st.info("لم يتم تعيين أي صفوف لك بعد."); return

    selected_class = st.selectbox("اختر الصف", options=teacher_classes["class_name"])
    class_students = pd.read_sql_query(
        """
        SELECT s.id, s.full_name
        FROM enrollments e JOIN students s ON s.id = e.student_id
        WHERE e.teacher_id = ? AND s.class_name = ? AND e.center_id=?
        ORDER BY s.full_name
    """, conn, params=[user["id"], selected_class, center_id])
    if class_students.empty:
        st.info("لا يوجد طلاب معينون لك في هذا الصف."); return

    sid = st.selectbox("اختر الطالب", options=class_students["id"], format_func=lambda i: class_students.set_index('id').loc[i, 'full_name'])
    avail_subjects = pd.read_sql_query(
        """
        SELECT sub.id, sub.name
        FROM enrollments e JOIN subjects sub ON e.subject_id = sub.id
        WHERE e.teacher_id = ? AND e.student_id = ? AND e.center_id=?
        ORDER BY sub.name
    """, conn, params=[user["id"], int(sid), center_id])
    if avail_subjects.empty:
        st.info("لا توجد مواد معينة لهذا الطالب."); return

    subid = st.selectbox("المادة", options=avail_subjects["id"], format_func=lambda i: avail_subjects.set_index('id').loc[i,'name'])

    # مخطط درجات للصف/المادة (إن وجد)
    scheme = pd.read_sql_query(
        """
        SELECT min_score, max_score, excellent_cut, high_cut, average_cut
        FROM grading_scheme
        WHERE center_id=? AND class_name=? AND (subject_id IS NULL OR subject_id=?)
        ORDER BY subject_id NULLS FIRST LIMIT 1
        """,
        conn, params=[center_id, selected_class, int(subid)])
    default_min = float(scheme.iloc[0,0]) if not scheme.empty else 0.0
    default_max = float(scheme.iloc[0,1]) if not scheme.empty else 100.0

    gdate = st.date_input("تاريخ اليوم", value=dt.date.today())
    min_val = st.number_input("الدرجة الدنيا", min_value=0.0, max_value=10000.0, step=0.5, value=default_min)
    max_val = st.number_input("الدرجة العظمى", min_value=0.0, max_value=10000.0, step=0.5, value=default_max)
    score = st.number_input("الدرجة", min_value=min_val, max_value=max_val, step=0.5)
    note  = st.text_area("ملاحظة للطالب (اختياري)")
    note_p= st.text_input("ملاحظة لوليّ الأمر (اختياري)")
    note_a= st.text_input("ملاحظة للمدير (اختياري)")

    saved_row = st.empty()

    if st.button("حفظ الدرجة", type="primary"):
        conn.execute(
            """
            INSERT INTO grades(student_id,subject_id,teacher_id,grade_date,score,note,note_teacher,note_parent,note_admin,min_score,max_score,center_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (int(sid), int(subid), int(user["id"]), gdate.isoformat(), float(score), note, note, note_p, note_a, float(min_val), float(max_val), center_id),
        )
        conn.commit()

        percent = None
        if max_val is not None and max_val > min_val:
            percent = (float(score) - float(min_val)) / (float(max_val) - float(min_val)) * 100.0
        if percent is not None and not scheme.empty and all(pd.notna(scheme.iloc[0,2:5])):
            exc, high, avg = map(float, scheme.iloc[0,2:5])
            if percent >= exc: qlabel = "متفوق"
            elif percent >= high: qlabel = "مرتفع"
            elif percent >= avg: qlabel = "متوسط"
            else: qlabel = "منخفض"
        else:
            scores_df = pd.read_sql_query(
                "SELECT g.score FROM grades g JOIN students s ON s.id=g.student_id WHERE s.class_name=? AND g.subject_id=? AND g.grade_date=? AND g.center_id=?",
                conn, params=[selected_class, int(subid), gdate.isoformat(), center_id])
            scores = scores_df["score"].tolist()
            avg_v = stats.mean(scores) if scores else None
            std_v = stats.pstdev(scores) if len(scores) > 1 else None
            qlabel = qualitative_label(float(score), avg_v, std_v)

        sname = class_students.set_index('id').loc[int(sid),'full_name']
        subname = avail_subjects.set_index('id').loc[int(subid),'name']
        show = pd.DataFrame([{ "رقم الطالب": int(sid), "اسم الطالب": sname, "الصف": selected_class, "المادة": subname, "التاريخ": gdate.isoformat(), "الدرجة": float(score), "الدنيا": float(min_val), "العظمى": float(max_val), "التقييم النوعي": qlabel }])
        saved_row.dataframe(show, use_container_width=True)
        st.success(f"تم حفظ الدرجة. <span class='badge-qual'>{qlabel}</span>", icon="✅")

    st.divider(); st.subheader("درجاتي الأخيرة")
    df = pd.read_sql_query(
        """
        SELECT g.id AS "#", g.grade_date AS "التاريخ", s.full_name AS "الطالب", sub.name AS "المادة",
               g.score AS "الدرجة", g.min_score AS "الدنيا", g.max_score AS "العظمى", g.note AS "الملاحظات"
        FROM grades g JOIN students s ON s.id=g.student_id JOIN subjects sub ON sub.id=g.subject_id
        WHERE g.teacher_id=? AND g.center_id=? ORDER BY g.grade_date DESC, g.id DESC LIMIT 200
    """, conn, params=[user["id"], center_id])
    st.dataframe(df, use_container_width=True)
    render_whatsapp_fab()

# ===================== بوابة الطالب =====================

def student_portal(conn, center_id, user):
    st.subheader("🎓 بوابة الطالب — عرض الدرجات")
    kid = user["student_id"]
    df = pd.read_sql_query(
        """
        SELECT g.grade_date AS "التاريخ", sub.name AS "المادة", g.score AS "الدرجة",
               g.min_score AS "الدنيا", g.max_score AS "العظمى", g.note AS "ملاحظات المعلم"
        FROM grades g JOIN subjects sub ON sub.id=g.subject_id
        WHERE g.student_id=? AND g.center_id=? ORDER BY g.grade_date DESC
    """, conn, params=[int(kid), center_id])
    st.dataframe(df, use_container_width=True)
    render_whatsapp_fab()

# ===================== التشغيل =====================

st.title("📊 تطبيق الدرجات — متعدد المراكز")

center_id = sidebar_center_selector(conn)

# تهيئة (اختياري) عبر darien_seed إن وجد
if ensure_darien_seed:
    try:
        ensure_darien_seed(conn)
    except Exception:
        pass

# حسابات الطلاب الموحّدة عند الحاجة
with closing(conn.cursor()) as cur:
    cur.execute("SELECT id FROM students WHERE center_id=?", (center_id,))
    student_ids = [r[0] for r in cur.fetchall()]
for sid in student_ids:
    existing = pd.read_sql_query("SELECT id FROM student_accounts WHERE student_id=? AND center_id=?", conn, params=[sid, center_id])
    if existing.empty:
        email = f"student{sid}@darien.local"
        conn.execute("INSERT INTO student_accounts(student_id,email,password_hash,center_id) VALUES (?,?,?,?)", (sid, email, bcrypt.hash(UNIFIED_PASSWORD), center_id))
        conn.commit()

# شريط التحفيز
if seed_render_marquee:
    try:
        seed_render_marquee(conn)
    except Exception:
        render_marquee_base()
else:
    render_marquee_base()

if "user" not in st.session_state:
    u = login_any(conn, center_id)
    if u:
        st.session_state["user"] = u
        st.rerun()
    st.stop()

user = st.session_state["user"]

with st.sidebar:
    st.markdown(f"**مرحبًا، {user.get('full_name','')}**")
    st.caption(f"الدور: {user['role']} · 📧 {user.get('email','')}")
    if user.get("role") == "owner" and (OWNER_EMAIL is None or OWNER_PASSWORD is None):
        st.warning("⚠️ هذا حساب مالك افتراضي. يُنصح بضبط OWNER_EMAIL و OWNER_PASSWORD من إعدادات البيئة.")
    st.info(f"كلمة المرور الموحّدة (غير المدير): {UNIFIED_PASSWORD}")
    if st.button("تسجيل الخروج"):
        st.session_state.clear(); st.rerun()

# عرض اللوحات حسب الدور
if user["role"] == "owner":
    # المالك يرى لوحة المراكز + يستطيع التنقل بين المراكز وإدارة كل مركز عبر لوحة المدير
    owner_panel(conn)
    st.divider()
    st.subheader("إدارة مركز محدد")
    center_id = sidebar_center_selector(conn)
    admin_panel(conn, center_id)
elif user["role"] == "admin":
    admin_panel(conn, center_id)
elif user["role"] == "teacher":
    teacher_daily_panel(conn, center_id, user)
elif user["role"] == "student":
    student_portal(conn, center_id, user)
else:
    st.info("هذا الإصدار يركّز على لوحتي المدير والمعلّم والطالب.")
