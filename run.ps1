\
try { chcp 65001 > $null } catch {}
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

if (!(Test-Path ".\.venv\Scripts\Activate.ps1")) {
  python -m venv .venv
}
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

streamlit run app.py
