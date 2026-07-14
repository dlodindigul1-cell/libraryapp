"""
sheets_service.py
------------------------------------------------------------
நூலகர் விடுப்பு மேலாண்மை — Google Apps Script Code.gs-ன்
server-side functions-ஐ Python-க்கு port செய்யப்பட்ட பதிப்பு.

Google Sheets-ஐ browser session இல்லாமல் (Service Account மூலம்)
நேரடியாக read/write செய்கிறோம் — இதனால்தான் multi-Google-login
mobile பிரச்சனை முழுசா தீரும்.
------------------------------------------------------------
"""

import os
import json
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

# ------------------------------------------------------------
# அமைப்புகள் (Config) — எல்லாமே environment variable-ல் இருந்து
# ------------------------------------------------------------
SPREADSHEET_ID   = os.environ["SPREADSHEET_ID"]
SHEET_NAME_MASTER = os.environ.get("SHEET_NAME_MASTER", "MASTER")
SHEET_NAME_ENTRY  = os.environ.get("SHEET_NAME_ENTRY", "LEAVE_ENTRY")
SHEET_NAME_RH     = os.environ.get("SHEET_NAME_RH", "RH DATES")

ENTRY_HEADERS = [
    "நூலகர் எண்", "நூலகர் பெயர்", "தேதி",
    "விடுப்பு வகை", "தேர்வு", "நாட்கள்",
    "PERIOD KEY", "நூலகம் பெயர்", "நூலக வகை",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None


def _get_credentials():
    """GOOGLE_SERVICE_ACCOUNT_JSON env var-ல் இருந்து service account key படிக்கும்."""
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(raw)
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def get_client():
    global _client
    if _client is None:
        _client = gspread.authorize(_get_credentials())
    return _client


def get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        _spreadsheet = get_client().open_by_key(SPREADSHEET_ID)
    return _spreadsheet


def _sheet(name):
    return get_spreadsheet().worksheet(name)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _s(v):
    """None-ஐ காலி string ஆக மாற்றி, trim செய்யும்."""
    return "" if v is None else str(v).strip()


DATE_PATTERNS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y",
]


def _parse_any_date(raw):
    """Sheet cell-ல் இருந்து வரும் தேதியை dd/mm/yyyy string ஆக normalize செய்யும்."""
    raw = _s(raw)
    if not raw:
        return ""
    for fmt in DATE_PATTERNS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw  # already dd/mm/yyyy or unrecognised — return as-is


def period_key_from_cell(val):
    """'2026-05' / '2026-5' / dd-mm-yyyy வகையான cell values-ஐ 'yyyy-mm' ஆக மாற்றும்."""
    raw = _s(val)
    if not raw:
        return ""
    # already looks like yyyy-mm or yyyy-m
    m = re.match(r"^(\d{4})-(\d{1,2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}"
    # dd/mm/yyyy style date -> yyyy-mm
    d = _parse_any_date(raw)
    m2 = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d)
    if m2:
        return f"{m2.group(3)}-{m2.group(2)}"
    return raw


# ------------------------------------------------------------
# getAllEmployees
# MASTER: Col B(1)=library, C(2)=empId, D(3)=empName, E(4)=type, G(6)=email
# ------------------------------------------------------------
def get_all_employees():
    try:
        data = _sheet(SHEET_NAME_MASTER).get_all_values()
        result = []
        for row in data[1:]:
            emp_id = _s(row[2]) if len(row) > 2 else ""
            emp_name = _s(row[3]) if len(row) > 3 else ""
            if not emp_id or not emp_name:
                continue
            result.append({
                "id": emp_id,
                "name": emp_name,
                "library": _s(row[1]) if len(row) > 1 else "",
                "type": _s(row[4]) if len(row) > 4 else "",
                "email": _s(row[6]) if len(row) > 6 else "",
            })

        def rank(name):
            return 0 if re.match(r"^[a-zA-Z]", name) else 1

        result.sort(key=lambda e: (rank(e["name"]), e["name"].lower()))
        return result
    except Exception:
        return []


# ------------------------------------------------------------
# lookupEmployeeByQuery
# ------------------------------------------------------------
def lookup_employee_by_query(q):
    try:
        data = _sheet(SHEET_NAME_MASTER).get_all_values()
        q_low = _s(q).lower()
        matches = []
        for row in data[1:]:
            emp_id = _s(row[2]) if len(row) > 2 else ""
            emp_name = _s(row[3]) if len(row) > 3 else ""
            id_match = emp_id.lower().startswith(q_low)
            name_match = len(q_low) >= 3 and q_low in emp_name.lower()
            if id_match or name_match:
                matches.append({
                    "id": emp_id,
                    "name": emp_name,
                    "library": _s(row[1]) if len(row) > 1 else "",
                    "type": _s(row[4]) if len(row) > 4 else "",
                    "email": _s(row[6]) if len(row) > 6 else "",
                })
        if not matches:
            return {"found": False}
        if len(matches) == 1:
            return {"found": True, "exact": True, **matches[0]}
        return {"found": True, "exact": False, "matches": matches}
    except Exception as e:
        return {"found": False, "error": str(e)}


# ------------------------------------------------------------
# getPermissionCount / checkPermissionLimit
# LEAVE_ENTRY: A(0)=empId, D(3)=leaveType, G(6)=periodKey
# ------------------------------------------------------------
def get_permission_count(emp_id, period_key):
    data = _sheet(SHEET_NAME_ENTRY).get_all_values()
    clean_emp_id = _s(emp_id)
    clean_period = period_key_from_cell(period_key)
    count = 0
    for row in data[1:]:
        row_emp_id = _s(row[0]) if len(row) > 0 else ""
        row_type = _s(row[3]).upper() if len(row) > 3 else ""
        row_period = period_key_from_cell(row[6]) if len(row) > 6 else ""
        if row_emp_id == clean_emp_id and row_type == "P" and row_period == clean_period:
            count += 1
    return count


def check_permission_limit(emp_id, period_key):
    count = get_permission_count(emp_id, period_key)
    return {"count": count, "exceeded": count >= 2}


# ------------------------------------------------------------
# getUsedLeave
# ------------------------------------------------------------
def get_used_leave(emp_id, leave_code):
    try:
        data = _sheet(SHEET_NAME_ENTRY).get_all_values()
        clean_emp_id = _s(emp_id)
        code = _s(leave_code).upper()
        total = 0.0
        for row in data[1:]:
            row_emp_id = _s(row[0]) if len(row) > 0 else ""
            row_type = _s(row[3]).upper() if len(row) > 3 else ""
            try:
                row_days = float(row[5]) if len(row) > 5 and row[5] != "" else 0
            except ValueError:
                row_days = 0
            if row_emp_id == clean_emp_id and row_type == code:
                total += row_days
        return {"empId": clean_emp_id, "leaveCode": code, "used": total}
    except Exception as e:
        return {"empId": emp_id, "leaveCode": leave_code, "used": 0, "error": str(e)}


# ------------------------------------------------------------
# ensureHeaders
# ------------------------------------------------------------
def ensure_headers(sheet):
    first_row = sheet.row_values(1)
    if not first_row or all(c == "" for c in first_row):
        sheet.update("A1", [ENTRY_HEADERS])
        sheet.format("A1:I1", {
            "backgroundColor": {"red": 0.10, "green": 0.31, "blue": 0.48},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
            "horizontalAlignment": "CENTER",
        })
        sheet.freeze(rows=1)


# ------------------------------------------------------------
# addLeaveRows
# rows: [{A,B,C,D,E,F,G,H,I}, ...]  (JSON keys அப்படியே GAS-ல் இருந்தது போல்)
# ------------------------------------------------------------
def add_leave_rows(rows):
    try:
        if not rows:
            return {"success": False, "error": "வரிசைகள் இல்லை"}

        sheet = _sheet(SHEET_NAME_ENTRY)
        ensure_headers(sheet)

        perm_tracker = {}
        out_rows = []

        for r in rows:
            if r.get("D") == "P":
                emp_id = _s(r.get("A"))
                period_key = period_key_from_cell(r.get("G"))
                key = f"{emp_id}_{period_key}"
                if key not in perm_tracker:
                    perm_tracker[key] = get_permission_count(emp_id, period_key)

                if perm_tracker[key] < 2:
                    r["D"] = "P"
                    r["F"] = 0
                else:
                    r["D"] = "CL"
                    r["E"] = "AN"
                    r["F"] = 0.5
                perm_tracker[key] += 1

            out_rows.append([
                r.get("A", ""), r.get("B", ""), r.get("C", ""),
                r.get("D", ""), r.get("E", ""), r.get("F", ""),
                r.get("G", ""), r.get("H", ""), r.get("I", ""),
            ])

        sheet.append_rows(out_rows, value_input_option="USER_ENTERED")
        return {"success": True, "added": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------
# getTodayLeaveStaff
# ------------------------------------------------------------
def get_today_leave_staff():
    try:
        data = _sheet(SHEET_NAME_ENTRY).get_all_values()
        today_str = datetime.now().strftime("%d/%m/%Y")
        result = []
        for row in data[1:]:
            emp_name = _s(row[1]) if len(row) > 1 else ""
            leave_type = _s(row[3]).upper() if len(row) > 3 else ""
            session = _s(row[4]).upper() if len(row) > 4 else ""
            days = row[5] if len(row) > 5 else ""
            library = _s(row[7]) if len(row) > 7 else ""
            row_date = _parse_any_date(row[2]) if len(row) > 2 else ""

            if not emp_name or not leave_type:
                continue
            if row_date == today_str:
                result.append({
                    "librarian": emp_name, "library": library,
                    "leaveType": leave_type, "session": session, "days": days,
                })
        return result
    except Exception:
        return []


# ------------------------------------------------------------
# getEmployeeLeaveHistory
# ------------------------------------------------------------
def get_employee_leave_history(emp_id):
    try:
        data = _sheet(SHEET_NAME_ENTRY).get_all_values()
        clean_emp_id = _s(emp_id)
        records = []
        for row in data[1:]:
            row_emp_id = _s(row[0]) if len(row) > 0 else ""
            if row_emp_id != clean_emp_id:
                continue
            leave_type = _s(row[3]).upper() if len(row) > 3 else ""
            session = _s(row[4]).upper() if len(row) > 4 else ""
            try:
                days = float(row[5]) if len(row) > 5 and row[5] != "" else 0
            except ValueError:
                days = 0
            date_str = _parse_any_date(row[2]) if len(row) > 2 else ""
            if not date_str or not leave_type:
                continue
            records.append({"date": date_str, "leaveType": leave_type, "session": session, "days": days})
        return records
    except Exception:
        return []


# ------------------------------------------------------------
# checkDuplicateLeave
# ------------------------------------------------------------
def check_duplicate_leave(emp_id, date_str, new_session):
    try:
        data = _sheet(SHEET_NAME_ENTRY).get_all_values()
        clean_emp_id = _s(emp_id)
        new_session = _s(new_session).upper()
        for row in data[1:]:
            row_emp_id = _s(row[0]) if len(row) > 0 else ""
            if row_emp_id != clean_emp_id:
                continue
            row_date = _parse_any_date(row[2]) if len(row) > 2 else ""
            if row_date != date_str:
                continue
            exist_session = _s(row[4]).upper() if len(row) > 4 else ""
            exist_type = _s(row[3]).upper() if len(row) > 3 else ""

            if exist_session == "FULL":
                return {"duplicate": True, "session": "FULL",
                        "message": f"❌ {date_str} தேதிக்கு ஏற்கனவே முழு நாள் விடுப்பு ({exist_type}) பதிவு செய்யப்பட்டுள்ளது."}
            if exist_session == "FN" and new_session in ("FN", "FULL"):
                return {"duplicate": True, "session": "FN",
                        "message": f"⚠️ {date_str} தேதிக்கு முற்பகல் (FN) விடுப்பு ({exist_type}) ஏற்கனவே பதிவாகியுள்ளது.\nபிற்பகல் (AN) விடுப்பு மட்டுமே பதிவு செய்யலாம்."}
            if exist_session == "AN" and new_session in ("AN", "FULL"):
                return {"duplicate": True, "session": "AN",
                        "message": f"⚠️ {date_str} தேதிக்கு பிற்பகல் (AN) விடுப்பு ({exist_type}) ஏற்கனவே பதிவாகியுள்ளது.\nமுற்பகல் (FN) விடுப்பு மட்டுமே பதிவு செய்யலாம்."}
        return {"duplicate": False}
    except Exception as e:
        return {"duplicate": False, "error": str(e)}


# ------------------------------------------------------------
# getRHDates / checkRHDate
# RH DATES: A(0)=date, B(1)=day, C(2)=func, row3 onwards
# ------------------------------------------------------------
def get_rh_dates():
    try:
        sheet = get_spreadsheet().worksheet(SHEET_NAME_RH)
        data = sheet.get_all_values()
        result = []
        for row in data[2:]:  # row 3 onwards
            raw = row[0] if len(row) > 0 else ""
            day = _s(row[1]) if len(row) > 1 else ""
            func = _s(row[2]) if len(row) > 2 else ""
            if not raw:
                continue
            result.append({"date": _parse_any_date(raw), "day": day, "func": func})
        return result
    except Exception:
        return []


def check_rh_date(date_str):
    try:
        for item in get_rh_dates():
            if item["date"] == date_str:
                return {"allowed": True, "func": item["func"], "day": item["day"]}
        return {"allowed": False}
    except Exception as e:
        return {"allowed": False, "error": str(e)}
