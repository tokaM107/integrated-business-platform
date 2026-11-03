# Collecting the library database metadata (one click)

## What to copy to the library PC
These two files, together in one folder (a USB stick is fine; they are plain text):
- `COLLECT_METADATA.bat`
- `collect_metadata.ps1`

## What to do on the library PC
1. Log in to Windows with the same user that opens the library program (the one that connected successfully).
   SQL Server must be running (it is, if the library program works).
2. Open the folder you copied and **double-click `COLLECT_METADATA.bat`**.
   - If Windows shows "Windows protected your PC": *More info* → *Run anyway*.
   - A black window opens and prints lines for about 1–3 minutes. Do not close it.
3. Read the last lines in the window:
   - `SUCCESS: collection complete` → done.
   - `FAILURE: n step(s) failed` → take a photo of the window; bring the ZIP anyway (it holds the log).
4. The file to bring back is on the **Desktop**: `library_metadata_<date>_<time>.zip`. Its exact name is printed
   after "ZIP file to bring back:". Copy that one file to the USB stick. Nothing else is needed.
5. Press any key to close the window.

## What it does and does not do
- Reads only (SELECT): tables and columns, keys and indexes, row counts, the lookup codes (operation, status,
  payment and sales types, branches, stores, cash desks, doctors' codes and names), the text of the procedures,
  views and functions, counts of documents per code, and a few sample documents. It writes nothing.
- Masks phones, addresses, e-mails, passwords, card / insurance / national numbers, IPs, file paths, remarks and
  customer / vendor / user / employee names. It never reads the rows of the users, customers, employees, vendors,
  banks, logs or settings tables (only their column names).
- Asks for no password: it uses your Windows login. Nothing is sent anywhere; the ZIP stays on the Desktop.

## If it says "No SQL Server answered"
Open *Services* (Win+R, type `services.msc`), find *SQL Server (MSSQLSERVER)* or *SQL Server (SQLEXPRESS)*, make
sure it is *Running*, then double-click the `.bat` again. If the instance has another name, open
`COLLECT_METADATA.bat` with Notepad and add ` -Server ".\NAME"` at the end of the `powershell.exe` line.

---

# جمع بيانات قاعدة المكتبة (ضغطة واحدة)

**اللي تنسخيه على جهاز المكتبة:** الملفين `COLLECT_METADATA.bat` و `collect_metadata.ps1` في فولدر واحد (على فلاشة).

**اللي تعمليه هناك:**
1. ادخلي على ويندوز بنفس المستخدم اللي بيفتح برنامج المكتبة.
2. افتحي الفولدر و**اضغطي مرتين على `COLLECT_METADATA.bat`**. لو ظهرت رسالة حماية من ويندوز: *More info* ثم *Run anyway*. هتفتح شاشة سودا وتشتغل من دقيقة لتلات دقايق؛ ما تقفليهاش.
3. اقرأي آخر سطور: `SUCCESS` يعني تمام. `FAILURE` صوّري الشاشة وهاتي الملف برضه.
4. الملف اللي تجيبيه على **سطح المكتب** اسمه `library_metadata_<تاريخ>.zip` (اسمه بالظبط مكتوب بعد "ZIP file to bring back"). انسخيه على الفلاشة. مش محتاجين أي حاجة تانية.

البرنامج بيقرأ بس ولا بيكتب حاجة في القاعدة، ولا بيطلب باسورد، وبيخفي التليفونات والعناوين والأسماء الشخصية، ومفيش حاجة بتتبعت لأي مكان.
