import sqlite3
from passlib.hash import bcrypt

# تعيين إيميلات ASCII سهلة + إعادة تعيين كلمة المرور 123456
mapping = [
    ("هشام محمود عمران",       "t01@darien.local"),
    ("محمد إبراهيم أبو سيف",   "t02@darien.local"),
    ("عبدالله زهير كيلاني",     "t03@darien.local"),
    ("محمد عادل أبو خليفه",     "t04@darien.local"),
    ("مصطفي نصر عبدالسميع",     "t05@darien.local"),
    ("محمود السيد ملش",         "t06@darien.local"),
    ("صلاح الغمري",             "t07@darien.local"),
    ("هبه عبدالفتاح صيام",      "t08@darien.local"),
    ("عبدالله علي عبدالباري",   "t09@darien.local"),
]

conn = sqlite3.connect("grades.db")
cur  = conn.cursor()

fixed = 0
for name, email in mapping:
    cur.execute(
        "UPDATE users SET email=?, password_hash=? WHERE full_name=? AND role='teacher'",
        (email, bcrypt.hash("123456"), name)
    )
    fixed += cur.rowcount

conn.commit()

print(f"Updated {fixed} teacher accounts.")
print("Current teacher logins:")
for row in cur.execute("SELECT full_name, email FROM users WHERE role='teacher' ORDER BY full_name"):
    print(f" - {row[0]}  ->  {row[1]}")

conn.close()
