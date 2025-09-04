# -*- coding: utf-8 -*-
import os, sqlite3, math
from contextlib import closing
import datetime as dt
import pandas as pd
import streamlit as st
import altair as alt
from passlib.hash import bcrypt

# محاولة استيراد البذرة + شريط المعلومات إن وُجد
try:
    from darien_seed import ensure_darien_seed, render_marquee as seed_render_marquee
except Exception:
    ensure_darien_seed = None
    seed_render_marquee = None

DB_PATH = os.environ.get("GRADES_DB_PATH", "grades.db")
UNIFIED_PASSWORD = os.environ.get("DARIEN_UNIFIED_PASSWORD", "123456")
WHATSAPP_E164 = "+201015477265"  # رقم واتساب المطلوب
QURAN_YT = "https://www.youtube.com/embed/m7tva04iQv4?autoplay=1&mute=1&loop=1&playlist=m7tva04iQv4"

st.set_page_config(page_title="📊 تطبيق الدرجات — مركز دارين التعليمي", page_icon="📊", layout="wide")

# --------------- تنسيق عام (خط واضح + RTL + تحسين الألوان) ---------------
def render_global_style():
    st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
      html, body, [data-testid="stAppViewContainer"] {
        direction: rtl !important;
        font-family: "Cairo", system-ui, -apple-system, "Segoe UI", "Noto Kufi Arabic", Arial, sans-serif !important;
      }
      h1, h2, h3, h4, h5, h6, label, .st-emotion-cache-1cypcdb {
        color: #111827;
      }
      .darien-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,.05);
      }
      .wa-fab{
          position: fixed; right: 16px; top: 120px; z-index: 9999;
          background: #25D366; color: #fff; padding: 12px 16px; border-radius: 999px;
          box-shadow: 0 6px 16px rgba(0,0,0,.12); text-decoration: none; font-weight: 700;
      }
      .badge-qual{ display:inline-block; background:#eef2ff; color:#1e40af; padding:2px 8px; border-radius:12px; margin-inline-start:8px; }
      .darien-marquee-wrap{
          direction: rtl; overflow: hidden; white-space: nowrap;
          border: 1px solid #e5e7eb; background: #ffffff; border-radius: 12px;
          padding: 8px 0; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.04);
      }
      .darien-marquee{
          display: inline-block; padding-inline-start: 100%;
          animation: darien-scroll 240s linear infinite; font-weight: 600; color: #0D1117;
      }
      @keyframes darien-scroll {
          0%   { transform: translateX(0%); }
          100% { transform: translateX(-100%); }
      }
    </style>
    """, unsafe_allow_html=True)

render_global_style()

# --------------- اتصال وقاعدة ---------------
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def ensure_base_schema(conn):
    with closing(conn.cursor()) as cur:
        cur.executescript(
        """
        PRAGMA foreign_keys = ON;

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

        CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id);
        CREATE INDEX IF NOT EXISTS idx_grades_subject ON grades(subject_id);
        CREATE INDEX IF NOT EXISTS idx_grades_date ON grades(grade_date);
        CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(att_date);
        CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
        """)
        conn.commit()

    # مدير افتراضي إذا لم يوجد
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users(full_name,email,role,password_hash) VALUES (?,?,?,?)",
                ("المدير", "admin@darien.local", "admin", bcrypt.hash("admin"))
            )
            conn.commit()

def ensure_min_accounts(conn):
    """تأمين وجود إيميلات وكلمات مرور موحّدة للطلاب (وإتاحتها للمعلمين عبر كلمة موحّدة)"""
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT id FROM students")
        student_ids = [r[0] for r in cur.fetchall()]

    for sid in student_ids:
        existing = pd.read_sql_query("SELECT id FROM student_accounts WHERE student_id=?", conn, params=[sid])
        if existing.empty:
            email = f"student{sid}@darien.local"
            conn.execute("INSERT INTO student_accounts(student_id,email,password_hash) VALUES (?,?,?)",
                         (sid, email, bcrypt.hash(UNIFIED_PASSWORD)))
    conn.commit()

# --------------- أدوات ---------------
def user_by_email(conn, email):
    with closing(conn.cursor()) as cur:
        cur.execute("SELECT id, full_name, email, role, password_hash FROM users WHERE email=?", (email,))
        r = cur.fetchone()
    if r:
        return {"id": r[0], "full_name": r[1], "email": r[2], "role": r[3], "password_hash": r[4]}
    return None

# --------------- تسجيل الدخول ---------------
def login_any(conn):
    st.subheader("تسجيل الدخول")
    email = st.text_input("البريد الإلكتروني", key="login_email")
    password = st.text_input("كلمة المرور", type="password", key="login_password")

    # تشغيل تلاوة القرآن (خفية) فور البدء بإدخال كلمة المرور
    if password:
        st.components.v1.html(f"""
        <iframe width="0" height="0" src="{QURAN_YT}" frameborder="0"
            allow="autoplay" allowfullscreen style="display:none"></iframe>
        """, height=0)

    if st.button("دخول", type="primary", key="login_button"):
        # 1) مستخدم (معلم/مدير)
        u = user_by_email(conn, email.strip())
        if u:
            if u["role"] == "admin":
                if bcrypt.verify(password, u["password_hash"]):
                    return {"kind":"user", **{k: u[k] for k in ("id","full_name","email","role")}}
            else:  # teacher
                if password == UNIFIED_PASSWORD or bcrypt.verify(password, u["password_hash"]):
                    return {"kind":"user", **{k: u[k] for k in ("id","full_name","email","role")}}
        # 2) طالب
        with closing(conn.cursor()) as cur:
            cur.execute("""SELECT sa.id, sa.student_id, s.full_name, sa.email, sa.password_hash
                           FROM student_accounts sa JOIN students s ON s.id=sa.student_id
                           WHERE sa.email=?""", (email,))
            s = cur.fetchone()
        if s:
            if password == UNIFIED_PASSWORD or bcrypt.verify(password, s[4]):
                return {"kind":"student","account_id":s[0],"student_id":s[1],
                        "full_name":s[2],"email":s[3],"role":"student"}
        st.error("بيانات الدخول غير صحيحة")
    return None

# --------------- تقييم نوعي ---------------
def qualitative_label(score, class_avg=None, class_std=None):
    if class_avg is not None and class_std is not None and class_std > 0:
        if score >= class_avg + class_std: return "متفوق"
        if score >= class_avg: return "مرتفع"
        if score >= class_avg - class_std: return "متوسط"
        return "منخفض"
    # بديل ثابت إن لا تتوفر إحصاءات
    if score >= 90: return "متفوق"
    if score >= 75: return "مرتفع"
    if score >= 50: return "متوسط"
    return "منخفض"

# --------------- لوحة الشرف (أعلى 10%) ---------------
def honor_board_top10(conn, class_name=None, subject_id=None, date_iso=None):
    where = "WHERE 1=1"
    params = []
    if class_name:
        where += " AND s.class_name=?"; params.append(class_name)
    if subject_id:
        where += " AND g.subject_id=?"; params.append(subject_id)
    if date_iso:
        where += " AND g.grade_date=?" ; params.append(date_iso)

    q = f"""
    SELECT s.full_name AS student, s.class_name AS class, g.subject_id, sub.name AS subject, g.grade_date, g.score
    FROM grades g JOIN students s ON s.id=g.student_id
    JOIN subjects sub ON sub.id=g.subject_id
    {where}
    ORDER BY g.score DESC
    """
    df = pd.read_sql_query(q, conn, params=params)
    if df.empty: return df

    # حد أعلى 10%
    n = len(df)
    k = max(1, math.ceil(n * 0.10))
    return df.head(k)

# --------------- شريط عبارات تحفيزية (300) ---------------
MOTIV = [f"عبارة تحفيزية تربوية رقم {i} — اجتهد اليوم لتتقدم غدًا." for i in range(1, 301)]

def render_marquee_base():
    text = "  •  ".join(MOTIV)
    st.markdown(f"""
    <div class="darien-marquee-wrap">
      <div class="darien-marquee">{text}</div>
    </div>
    """, unsafe_allow_html=True)

def render_whatsapp_fab():
    st.markdown(f"""
      <a class="wa-fab" href="https://wa.me/{WHATSAPP_E164.lstrip('+')}" target="_blank" title="التواصل عبر واتساب">
        التظلّم عبر واتساب
      </a>
    """, unsafe_allow_html=True)

# --------------- لوحات ---------------
def admin_panel(conn):
    tabs = st.tabs(["👥 الطلاب","📚 المواد","🧑‍🏫 المعلّمون والتعيينات","📈 التقارير","🏅 المجتهدون"])
    # الطلاب
    with tabs[0]:
        with st.container():
            st.markdown("**إضافة طالب**")
            c1, c2 = st.columns(2)
            with c1:
                n = st.text_input("اسم الطالب", key="admin_add_student_name")
            with c2:
                cl = st.text_input("الصف/الفصل", key="admin_add_student_class")
            if st.button("إضافة الطالب", key="admin_add_student_btn"):
                if n and cl:
                    conn.execute("INSERT INTO students(full_name,class_name) VALUES (?,?)", (n.strip(), cl.strip()))
                    conn.commit(); st.success("تمت إضافة الطالب"); st.rerun()
        st.markdown("---")
        df_students = pd.read_sql_query(
            "SELECT id AS 'رقم الطالب', full_name AS 'الاسم الكامل', class_name AS 'الصف' FROM students ORDER BY class_name, full_name", conn)
        st.dataframe(df_students, use_container_width=True)

    # المواد
    with tabs[1]:
        with st.container():
            sname = st.text_input("اسم المادة", key="admin_add_subject_name")
            if st.button("إضافة مادة", key="admin_add_subject_btn"):
                if sname:
                    try:
                        conn.execute("INSERT INTO subjects(name) VALUES (?)",(sname.strip(),)); conn.commit(); st.success("تمت إضافة المادة"); st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("المادة موجودة بالفعل")
        st.markdown("---")
        df_subjects = pd.read_sql_query("SELECT id AS 'المعرف', name AS 'اسم المادة' FROM subjects ORDER BY name", conn)
        st.dataframe(df_subjects, use_container_width=True)

    # المعلّمون والتعيينات
    with tabs[2]:
        st.markdown("**إضافة معلّم**")
        c1, c2 = st.columns(2)
        with c1:
            tname = st.text_input("اسم المعلّم", key="admin_add_teacher_name")
            temail= st.text_input("إيميل المعلّم", key="admin_add_teacher_email")
        with c2:
            tpass = st.text_input("كلمة مرور (اختياري، وإلا فالموحد)", type="password", key="admin_add_teacher_pass")
            if st.button("إنشاء حساب معلم", key="admin_add_teacher_btn"):
                if tname and temail:
                    try:
                        pw_hash = bcrypt.hash(tpass) if tpass else bcrypt.hash(UNIFIED_PASSWORD)
                        conn.execute("INSERT INTO users(full_name,email,role,password_hash) VALUES (?,?,? ,?)",
                                     (tname.strip(), temail.strip(), "teacher", pw_hash))
                        conn.commit(); st.success("تم إنشاء الحساب"); st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("البريد مستخدم من قبل")
        st.divider()
        st.markdown("**تعيين طالب ↔ مادة ↔ معلّم**")
        studs = pd.read_sql_query("SELECT id, full_name, class_name FROM students ORDER BY class_name, full_name", conn)
        subs  = pd.read_sql_query("SELECT id, name FROM subjects ORDER BY name", conn)
        teach = pd.read_sql_query("SELECT id, full_name, email FROM users WHERE role='teacher' ORDER BY full_name", conn)
        if studs.empty or subs.empty or teach.empty:
            st.info("أضف طلاب/مواد/معلمين أولاً.")
        else:
            sid = st.selectbox("طالب", studs["id"],
                               format_func=lambda i: f"{studs.set_index('id').loc[i,'full_name']} - {studs.set_index('id').loc[i,'class_name']}",
                               key="admin_assign_student")
            subid= st.selectbox("مادة", subs["id"],
                                format_func=lambda i: subs.set_index('id').loc[i,'name'],
                                key="admin_assign_subject")
            tid  = st.selectbox("معلّم", teach["id"],
                                format_func=lambda i: f"{teach.set_index('id').loc[i,'full_name']} ({teach.set_index('id').loc[i,'email']})",
                                key="admin_assign_teacher")
            if st.button("تعيين", key="admin_assign_btn"):
                conn.execute("INSERT INTO enrollments(student_id,subject_id,teacher_id) VALUES (?,?,?)",(int(sid),int(subid),int(tid)))
                conn.commit(); st.success("تم التعيين"); st.rerun()
        st.markdown("**التعيينات الحالية**")
        q = """
        SELECT e.id AS "معرف التعيين", s.full_name AS "الطالب", s.class_name AS "الصف", sub.name AS "المادة", u.full_name AS "المعلم"
        FROM enrollments e
        JOIN students s ON s.id=e.student_id
        JOIN subjects sub ON sub.id=e.subject_id
        JOIN users u ON u.id=e.teacher_id
        ORDER BY "الصف", "الطالب", "المادة"
        """
        st.dataframe(pd.read_sql_query(q, conn), use_container_width=True)

    # التقارير
    with tabs[3]:
        c1,c2 = st.columns(2)
        fd = c1.date_input("من تاريخ", value=None, key="admin_report_from_date")
        td = c2.date_input("إلى تاريخ", value=None, key="admin_report_to_date")
        params=[]; where="WHERE 1=1"
        if fd: where += " AND g.grade_date >= ?"; params.append(fd.isoformat())
        if td: where += " AND g.grade_date <= ?"; params.append(td.isoformat())
        q = f"""
        SELECT g.id AS "المعرف", g.grade_date AS "التاريخ", s.full_name AS "الطالب", s.class_name AS "الصف", sub.name AS "المادة",
               u.full_name AS "المعلم", g.score AS "الدرجة", g.note AS "ملاحظة للطالب",
               g.note_teacher AS "ملاحظة للمعلم", g.note_parent AS "ملاحظة لولي الأمر", g.note_admin AS "ملاحظة للمدير"
        FROM grades g
        JOIN students s ON s.id=g.student_id
        JOIN subjects sub ON sub.id=g.subject_id
        JOIN users u ON u.id=g.teacher_id
        {where}
        ORDER BY g.grade_date DESC
        """
        df = pd.read_sql_query(q, conn, params=params)
        st.dataframe(df, use_container_width=True)

    # المجتهدون
    with tabs[4]:
        st.markdown("**المجتهدون من أبنائنا (أعلى 10%)**")
        classes = pd.read_sql_query("SELECT DISTINCT class_name FROM students ORDER BY class_name", conn)
        subs = pd.read_sql_query("SELECT id, name FROM subjects ORDER BY name", conn)
        if classes.empty or subs.empty:
            st.info("أضف طلابًا وموادًا أولًا.")
        else:
            c = st.selectbox("اختر الصف", classes["class_name"], key="honor_class")
            s = st.selectbox("اختر المادة", subs["id"], key="honor_subject",
                             format_func=lambda i: subs.set_index('id').loc[i,'name'])
            d = st.date_input("اختر التاريخ", value=dt.date.today(), key="honor_date")
            df = honor_board_top10(conn, c, int(s), d.isoformat())
            if df.empty:
                st.info("لا بيانات لهذا الاختيار.")
            else:
                df.rename(columns={"student":"الطالب","class":"الصف","subject":"المادة","grade_date":"التاريخ","score":"الدرجة"}, inplace=True)
                st.dataframe(df[["الطالب","الصف","المادة","التاريخ","الدرجة"]], use_container_width=True)

# --------------- لوحة المعلّم (يومي فقط) ---------------
def teacher_daily_panel(conn, user):
    st.subheader("🗓️ إدخال الدرجات اليومية")

    # صفوف المعلم
    teacher_classes = pd.read_sql_query("""
        SELECT DISTINCT s.class_name
        FROM enrollments e JOIN students s ON s.id = e.student_id
        WHERE e.teacher_id = ?
        ORDER BY s.class_name
    """, conn, params=[user["id"]])
    if teacher_classes.empty:
        st.info("لم يتم تعيين أي صفوف لك بعد.")
        return

    selected_class = st.selectbox("اختر الصف", options=teacher_classes["class_name"], key="daily_select_class")

    # طلاب الصف المختار
    class_students = pd.read_sql_query("""
        SELECT s.id, s.full_name
        FROM enrollments e JOIN students s ON s.id = e.student_id
        WHERE e.teacher_id = ? AND s.class_name = ? ORDER BY s.full_name
    """, conn, params=[user["id"], selected_class])
    if class_students.empty:
        st.info("لا يوجد طلاب معينون لك في هذا الصف.")
        return

    sid = st.selectbox(
        "اختر الطالب",
        options=class_students["id"],
        format_func=lambda i: class_students.set_index('id').loc[i, 'full_name'],
        key="daily_select_student"
    )

    # مواد هذا الطالب مع هذا المعلم
    avail_subjects = pd.read_sql_query("""
        SELECT sub.id, sub.name
        FROM enrollments e JOIN subjects sub ON e.subject_id = sub.id
        WHERE e.teacher_id = ? AND e.student_id = ?
        ORDER BY sub.name
    """, conn, params=[user["id"], int(sid)])
    if avail_subjects.empty:
        st.info("لا توجد مواد معينة لهذا الطالب.")
        return

    subid = st.selectbox(
        "المادة",
        options=avail_subjects["id"],
        format_func=lambda i: avail_subjects.set_index('id').loc[i,'name'],
        key="daily_grading_subject"
    )

    gdate = st.date_input("تاريخ اليوم", value=dt.date.today(), key="daily_date")
    score = st.number_input("الدرجة", min_value=0.0, max_value=100.0, step=0.5, key="daily_score")
    note  = st.text_area("ملاحظة للطالب (اختياري)", key="daily_note_student")
    note_p= st.text_input("ملاحظة لوليّ الأمر (اختياري)", key="daily_note_parent")
    note_a= st.text_input("ملاحظة للمدير (اختياري)", key="daily_note_admin")

    saved_row = st.empty()

    if st.button("حفظ الدرجة", type="primary", key="daily_save_grade"):
        with closing(conn.cursor()) as cur:
            cur.execute("""INSERT INTO grades(student_id,subject_id,teacher_id,grade_date,score,note,note_teacher,note_parent,note_admin)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (int(sid), int(subid), int(user["id"]), gdate.isoformat(), float(score), note, note, note_p, note_a))
            conn.commit()

       # حساب متوسط/انحراف الصف لهذا التاريخ والمادة - بايثون بدل SQL
import statistics as stats

cls = selected_class
scores_q = """
SELECT g.score
FROM grades g JOIN students s ON s.id=g.student_id
WHERE s.class_name=? AND g.subject_id=? AND g.grade_date=?
"""
scores_df = pd.read_sql_query(scores_q, conn, params=[cls, int(subid), gdate.isoformat()])
scores = scores_df["score"].tolist()

avg_v = stats.mean(scores) if scores else None
std_v = stats.pstdev(scores) if len(scores) > 1 else None  # انحراف معياري سكاني
qlabel = qualitative_label(float(score), avg_v, std_v)

        # إظهار السطر فورًا
        sname = class_students.set_index('id').loc[int(sid),'full_name']
        subname = avail_subjects.set_index('id').loc[int(subid),'name']
        show = pd.DataFrame([{
            "رقم الطالب": int(sid),
            "اسم الطالب": sname,
            "الصف": selected_class,
            "المادة": subname,
            "التاريخ": gdate.isoformat(),
            "الدرجة": float(score),
            "التقييم النوعي": qlabel
        }])
        saved_row.dataframe(show, use_container_width=True)
        st.success(f"تم حفظ الدرجة. <span class='badge-qual'>{qlabel}</span>", icon="✅")

    st.divider()
    st.subheader("درجاتي الأخيرة")
    df = pd.read_sql_query("""
        SELECT g.id AS "المعرف", g.grade_date AS "التاريخ", s.full_name AS "الطالب", sub.name AS "المادة", g.score AS "الدرجة", g.note AS "الملاحظات"
        FROM grades g JOIN students s ON s.id=g.student_id JOIN subjects sub ON sub.id=g.subject_id
        WHERE g.teacher_id=? ORDER BY g.grade_date DESC, g.id DESC LIMIT 200
    """, conn, params=[user["id"]])
    st.dataframe(df, use_container_width=True)

    # زر واتساب عائم (تظلم)
    render_whatsapp_fab()

# --------------- بوابة الطالب (عرض فقط) ---------------
def student_portal(conn, user):
    st.subheader("🎓 بوابة الطالب — عرض الدرجات")
    kid = user["student_id"]
    df = pd.read_sql_query("""
        SELECT g.grade_date AS "التاريخ", sub.name AS "المادة", g.score AS "الدرجة", g.note AS "ملاحظات المعلم"
        FROM grades g JOIN subjects sub ON sub.id=g.subject_id
        WHERE g.student_id=? ORDER BY g.grade_date DESC
    """, conn, params=[int(kid)])
    st.dataframe(df, use_container_width=True)

    # زر واتساب عائم (تواصل/استفسار)
    render_whatsapp_fab()

# --------------- تنفيذ ---------------
conn = get_conn()
ensure_base_schema(conn)

# تهيئة (اختياري) عبر darien_seed إن وجد
if ensure_darien_seed:
    try:
        ensure_darien_seed(conn)
    except Exception:
        pass

ensure_min_accounts(conn)

st.title("📊 تطبيق الدرجات — مركز دارين التعليمي")

# شريط التحفيز
if seed_render_marquee:
    try:
        seed_render_marquee(conn)
    except Exception:
        render_marquee_base()
else:
    render_marquee_base()

if "user" not in st.session_state:
    u = login_any(conn)
    if u:
        st.session_state["user"] = u
        st.rerun()
    st.stop()

user = st.session_state["user"]

with st.sidebar:
    st.markdown(f"**مرحبًا، {user.get('full_name','')}**")
    st.caption(f"الدور: {user['role']} · 📧 {user.get('email','')}")
    st.info(f"كلمة المرور الموحّدة (غير المدير): {UNIFIED_PASSWORD}")
    if st.button("تسجيل الخروج", key="logout_button"):
        st.session_state.clear()
        st.rerun()

# عرض اللوحات حسب الدور
if user["role"] == "admin":
    admin_panel(conn)
elif user["role"] == "teacher":
    teacher_daily_panel(conn, user)
elif user["role"] == "student":
    student_portal(conn, user)
else:
    st.info("هذا الإصدار يركّز على لوحتي المدير والمعلّم والطالب.")
