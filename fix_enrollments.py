import sqlite3
from contextlib import closing

# خريطة: المادة -> اسم المعلّم (بالضبط كما في البذرة)
DEFAULT = {
    "رياضيات": "محمد إبراهيم أبو سيف",
    "عربي":    "محمد عادل أبو خليفه",
    "علوم":    "عبدالله زهير كيلاني",
    "انجليزي": "محمود السيد ملش",
    "دراسات":  "صلاح الغمري",
    "أصول دين":"عبدالله علي عبدالباري",
}

def get_id(cur, q, p=()):
    cur.execute(q, p); r = cur.fetchone()
    return r[0] if r else None

with sqlite3.connect("grades.db") as conn, closing(conn.cursor()) as cur:
    # احصاءات قبل
    cur.execute("SELECT COUNT(*) FROM enrollments"); before = cur.fetchone()[0]

    # لو الطلاب 0، غالباً لم تُزرع البيانات — نزرعها الآن
    cur.execute("SELECT COUNT(*) FROM students"); scount = cur.fetchone()[0]
    if scount == 0:
        try:
            from darien_seed import ensure_darien_seed
            ensure_darien_seed(conn)
            print("تم زرع البيانات (طلاب/معلمون/مواد).")
        except Exception as e:
            print("تعذر زرع البيانات تلقائيًا:", e)

    # اجلب كل الطلاب
    students = [r[0] for r in cur.execute("SELECT id FROM students")]

    created = 0
    for subj, tname in DEFAULT.items():
        sid = get_id(cur, "SELECT id FROM subjects WHERE name=?", (subj,))
        tid = get_id(cur, "SELECT id FROM users WHERE full_name=? AND role='teacher'", (tname,))
        if not sid or not tid:
            print(f"[تحذير] لم أجد {'المادة' if not sid else 'المعلّم'} لـ: {subj} -> {tname}")
            continue
        for stu in students:
            cur.execute("SELECT 1 FROM enrollments WHERE student_id=? AND subject_id=?", (stu, sid))
            if not cur.fetchone():
                cur.execute("INSERT INTO enrollments(student_id,subject_id,teacher_id) VALUES (?,?,?)",
                            (stu, sid, tid))
                created += 1

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM enrollments"); after = cur.fetchone()[0]
    print(f"enrollments قبل: {before} / بعد: {after} (+{after - before} إضافات، منها {created} جديدة)")

    # اعرض ملخصًا لكل معلّم وعدد صفوفه (حسب الطلاب)
    print("\nملخص لكل معلّم (عدد الطلاب المرتبطين به في أي مادة):")
    for row in cur.execute("""
        SELECT u.full_name, COUNT(DISTINCT s.id)
        FROM enrollments e
        JOIN users u ON u.id=e.teacher_id
        JOIN students s ON s.id=e.student_id
        WHERE u.role='teacher'
        GROUP BY u.id
        ORDER BY u.full_name
    """):
        print(f" - {row[0]}: {row[1]} طالب")
