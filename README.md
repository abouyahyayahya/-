# مركز دارين التعليمي — حزمة تطبيق الدرجات (Streamlit)

## التشغيل على Windows (PowerShell)
1) فك الضغط إلى مثلًا: `D:\darien_appp\darien_app`
2) افتح **Windows PowerShell** أو **Windows Terminal**.
3) انتقل للمجلد:
```powershell
cd "D:\darien_appp\darien_app"
```
4) شغّل السكربت (يعالج الترميز، ينشئ بيئة افتراضية، يثبّت المتطلبات، ثم يشغّل التطبيق):
```powershell
.un.ps1
```
5) افتح الرابط الذي يظهر لك من Streamlit.

## حسابات افتراضية
- **مدير** (يُنشأ تلقائيًا إن لم يوجد):  
  البريد: `admin@darien.local`، كلمة المرور: `admin`
- **المعلمون** (من البذر): كلمة مرور افتراضية: `123456`

## المزايا المضمّنة
- إعداد قاعدة البيانات SQLite تلقائيًا.
- زر رصد يومي + رصد صف كامل للمعلم.
- عمودان للمصروفات: **سداد الدراسة / سداد النقل** (القيم: سدد / لم يسدد بعد).
- ترتيب الطلاب أبجديًا داخل كل صف.
- شريط متحرك RTL أعلى الصفحة يعرض المركز + المدير + المعلمين/موادهم/أيامهم.
- واجهة عربية بالكامل.

## مصادر موثوقة
- Streamlit: https://docs.streamlit.io/
- pandas: https://pandas.pydata.org/docs/
- Altair: https://altair-viz.github.io/
- SQLite SQL: https://www.sqlite.org/lang.html
- Passlib (bcrypt): https://passlib.readthedocs.io/ و https://pypi.org/project/bcrypt/
- CSS Animations (MDN): https://developer.mozilla.org/docs/Web/CSS/CSS_animations
