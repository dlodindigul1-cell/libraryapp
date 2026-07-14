"""
pettycash_service.py
------------------------------------------------------------
சில்லறை செலவினம் (Contingent) app — Phase 1 (Core Entry).
GAS Code.gs-ல் இருந்த functions-ன் Python port:
  getLibraryTypes, getLibrariesByType, getAllLibraryData,
  getEmailsForLibrary, getExistingContingentData,
  submitOrUpdateContingent, getLibraryCode, generateUniqueKey,
  getAvailableMonthsForLibrary
------------------------------------------------------------
"""

import os
import re
from io import BytesIO
from datetime import datetime, timedelta
from urllib.parse import quote

import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from sheets_service import _get_credentials  # ஒரே Service Account, எல்லா sheets/drive-க்கும்
from pdf_service import _html_to_pdf_bytes, TAMIL_FONT_FACE_CSS  # HTML → PDF, Tamil font embedding (Yearly Abstract reports-க்கும் இதே பயன்படுத்துகிறோம்)

# ------------------------------------------------------------
# Config (env vars)
# ------------------------------------------------------------
LIBRARY_DATA_SPREAD_ID   = os.environ["LIBRARY_DATA_SPREAD_ID"]
LIBRARY_DATA_SHEET_NAME  = os.environ.get("LIBRARY_DATA_SHEET_NAME", "Sheet1")

CONTINGENT_SHEET_ID      = os.environ["CONTINGENT_SHEET_ID"]
CONTINGENT_SHEET_NAME    = os.environ.get("CONTINGENT_SHEET_NAME", "contingent")

APPROVAL_PDF_FOLDER_ID   = os.environ.get("APPROVAL_PDF_FOLDER_ID", "")

RECEIPTS_SHEET_ID        = os.environ.get("RECEIPTS_SHEET_ID", "")
RECEIPTS_SHEET_NAME      = os.environ.get("RECEIPTS_SHEET_NAME", "Form responses 1")

BANK_SHEET_ID             = os.environ.get("BANK_SHEET_ID", "")
BANK_SHEET_NAME           = os.environ.get("BANK_SHEET_NAME", "FOR MOBILE APP")

ACK_PDF_FOLDER_ID         = os.environ.get("ACK_PDF_FOLDER_ID", "")

# --- நடப்பு ஆண்டு சுருக்கம் (Yearly Receipt/Expense Abstract) ---
# "receipt abstract" / "expense abstract" tabs ஏற்கனவே தயார் செய்யப்பட்டுள்ள
# Source Spreadsheet — contingent_code.txt (GAS)-ல் இருந்ததே default ஆக வைக்கப்பட்டுள்ளது.
ABSTRACT_SOURCE_SHEET_ID     = os.environ.get("ABSTRACT_SOURCE_SHEET_ID", "1FVWlKAywkMn7q7bAqQ3a8G6NlN_lvH3Ga6DA9MqRpwk")
ABSTRACT_RECEIPT_SHEET_NAME  = os.environ.get("ABSTRACT_RECEIPT_SHEET_NAME", "receipt abstract")
ABSTRACT_EXPENSE_SHEET_NAME  = os.environ.get("ABSTRACT_EXPENSE_SHEET_NAME", "expense abstract")

YEARLY_RECEIPT_FOLDER_ID = os.environ.get("YEARLY_RECEIPT_FOLDER_ID", "13P8qREf_XsD0p_J4w9ph7gbfNEhpkYyg")
YEARLY_EXPENSE_FOLDER_ID = os.environ.get("YEARLY_EXPENSE_FOLDER_ID", "115sLao9m1iUTfZtKcY5vi6wwlQ6cazlT")

_client = None
_drive = None


def get_client():
    global _client
    if _client is None:
        _client = gspread.authorize(_get_credentials())
    return _client


def get_drive():
    global _drive
    if _drive is None:
        _drive = build("drive", "v3", credentials=_get_credentials())
    return _drive


def _s(v):
    return "" if v is None else str(v).strip()


# ------------------------------------------------------------
# getLibraryTypes
# ------------------------------------------------------------
def get_library_types():
    return [
        "மாவட்ட மைய நூலகம்",
        "முழு நேர கிளை நூலகம்",
        "கிளை நூலகம்",
        "ஊர்ப்புற நூலகம்",
        "பகுதி நேர நூலகம்",
    ]


# ------------------------------------------------------------
# getLibrariesByType — LIBRARY_DATA sheet, A2:D175, D=type
# ------------------------------------------------------------
def get_libraries_by_type(lib_type):
    try:
        sh = get_client().open_by_key(LIBRARY_DATA_SPREAD_ID).worksheet(LIBRARY_DATA_SHEET_NAME)
        rows = sh.get("A2:D175")
        result = []
        for row in rows:
            row_type = _s(row[3]) if len(row) > 3 else ""
            if row_type == _s(lib_type):
                name = _s(row[0]) if len(row) > 0 else ""
                if name:
                    result.append(name)
        return result
    except Exception:
        return []


# ------------------------------------------------------------
# getAllLibraryData — A2:C175 (A=library, C=emails comma-separated)
# ------------------------------------------------------------
def get_all_library_data():
    try:
        sh = get_client().open_by_key(LIBRARY_DATA_SPREAD_ID).worksheet(LIBRARY_DATA_SHEET_NAME)
        rows = sh.get("A2:C175")
        result = []
        for row in rows:
            library = _s(row[0]) if len(row) > 0 else ""
            emails_str = _s(row[2]).lower() if len(row) > 2 else ""
            emails = [e.strip() for e in emails_str.split(",") if "@" in e.strip()]
            if library and emails:
                result.append({"library": library, "emails": emails})
        return result
    except Exception:
        return []


# ------------------------------------------------------------
# getEmailsForLibrary
# ------------------------------------------------------------
def get_emails_for_library(library_name):
    for item in get_all_library_data():
        if item["library"] == library_name:
            return {"success": True, "library": item["library"], "emails": item["emails"]}
    return {"success": False, "message": "நூலகம் கிடைக்கவில்லை அல்லது மின்னஞ்சல் இல்லை"}


# ------------------------------------------------------------
# getLibraryCode — A2:B175 (A=name, B=code)
# ------------------------------------------------------------
def get_library_code(library_name):
    try:
        sh = get_client().open_by_key(LIBRARY_DATA_SPREAD_ID).worksheet(LIBRARY_DATA_SHEET_NAME)
        rows = sh.get("A2:B175")
        for row in rows:
            name = _s(row[0]) if len(row) > 0 else ""
            code = _s(row[1]) if len(row) > 1 else ""
            if name == _s(library_name) and code:
                return code.upper()
        return None
    except Exception:
        return None


def generate_unique_key(library_code, month_year):
    if not library_code or not month_year:
        return ""
    clean = re.sub(r"[/-]", "", month_year)
    return f"{library_code}{clean}"


# ------------------------------------------------------------
# ROW_FIELDS — contingent sheet-ன் column order (A..) - GAS rowData-உடன் ஒத்துப்போகும்
# (timestamp column தனியா handle ஆகும்)
# ------------------------------------------------------------
ROW_FIELD_KEYS = [
    "loginEmail", "libraryType", "libraryName",
    "dailyThanthi", "hinduTamil", "dinamani", "theekathir", "tamilMurasu",
    "maalaiMalar", "maalaiMurasu", "theHindu", "indianExpress", "timesOfIndia",
    "deccanChronicle", "businessLine", "economicTimes",
    "partnerNameTamil", "partnerDays", "staffNameTamil", "staffDays",
    "partTimeStaffName", "partTimeStaffDays", "electricityBill",
    "rentOwnerName", "rentAmount", "phoneWifiAmount", "waterTax", "photocopyAmount",
    "busPurpose", "busDate", "busAmount",
    "travelPurpose", "travelDate", "travelAmount",
    "postalAmount",
    "registerItem", "registerAmount",
    "stationeryItem", "stationeryAmount",
    "electricalItem", "electricalAmount",
    "consumerItem", "consumerAmount",
    "otherExpense1Desc", "otherExpense1Amount",
    "otherExpense2Desc", "otherExpense2Amount",
]
# index-க்கு column எண் (0-based, timestamp=col0 சேர்த்து): row[4]=dailyThanthi முதல்...
# GAS-ல் row[4]..row[47] தான் ROW_FIELD_KEYS[3:] -க்கு ஒத்தது (0,1,2 = loginEmail/type/name)


# ------------------------------------------------------------
# getExistingContingentData — column indices GAS-ல் இருந்ததே அப்படியே
# ------------------------------------------------------------
DATA_FIELD_INDEX = {
    "dailyThanthi": 4, "hinduTamil": 5, "dinamani": 6, "theekathir": 7, "tamilMurasu": 8,
    "maalaiMalar": 9, "maalaiMurasu": 10, "theHindu": 11, "indianExpress": 12, "timesOfIndia": 13,
    "deccanChronicle": 14, "businessLine": 15, "economicTimes": 16,
    "partnerNameTamil": 17, "partnerDays": 18, "staffNameTamil": 19, "staffDays": 20,
    "partTimeStaffName": 21, "partTimeStaffDays": 22, "electricityBill": 23,
    "rentOwnerName": 24, "rentAmount": 25, "phoneWifiAmount": 26, "waterTax": 27, "photocopyAmount": 28,
    "busPurpose": 29, "busDate": 30, "busAmount": 31,
    "travelPurpose": 32, "travelDate": 33, "travelAmount": 34,
    "postalAmount": 35,
    "registerItem": 36, "registerAmount": 37,
    "stationeryItem": 38, "stationeryAmount": 39,
    "electricalItem": 40, "electricalAmount": 41,
    "consumerItem": 42, "consumerAmount": 43,
    "otherExpense1Desc": 44, "otherExpense1Amount": 45,
    "otherExpense2Desc": 46, "otherExpense2Amount": 47,
    "paper14": 50, "paper15": 51, "paper16": 52, "paper17": 53, "paper18": 54,
}


def _get_contingent_sheet():
    return get_client().open_by_key(CONTINGENT_SHEET_ID).worksheet(CONTINGENT_SHEET_NAME)


def get_existing_contingent_data(library_name, month_year):
    try:
        sh = _get_contingent_sheet()
        data = sh.get_all_values()
        target_lib = _s(library_name)
        target_my = _s(month_year)

        for i in range(1, len(data)):
            row = data[i]
            row_lib = _s(row[3]) if len(row) > 3 else ""
            row_my = _s(row[48]) if len(row) > 48 else ""
            if row_lib == target_lib and row_my == target_my:
                out = {}
                for key, idx in DATA_FIELD_INDEX.items():
                    val = row[idx] if len(row) > idx else ""
                    if key in ("rentOwnerName", "busPurpose", "busDate", "travelPurpose",
                               "travelDate", "registerItem", "stationeryItem",
                               "electricalItem", "consumerItem", "otherExpense1Desc",
                               "otherExpense2Desc", "partnerNameTamil", "staffNameTamil",
                               "partTimeStaffName"):
                        out[key] = val or ""
                    else:
                        try:
                            out[key] = float(val) if val not in ("", None) else 0
                        except ValueError:
                            out[key] = 0
                out["monthYear"] = target_my
                return {"success": True, "rowIndex": i + 1, "data": out}
        return {"success": False}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ------------------------------------------------------------
# submitOrUpdateContingent
# ------------------------------------------------------------
def _build_row(data, timestamp):
    def g(k, default=""):
        return data.get(k, default) if data.get(k) not in (None, "") else default

    return [
        timestamp,
        g("loginEmail"), g("libraryType"), _s(data.get("libraryName")),
        g("dailyThanthi", 0), g("hinduTamil", 0), g("dinamani", 0), g("theekathir", 0), g("tamilMurasu", 0),
        g("maalaiMalar", 0), g("maalaiMurasu", 0), g("theHindu", 0), g("indianExpress", 0), g("timesOfIndia", 0),
        g("deccanChronicle", 0), g("businessLine", 0), g("economicTimes", 0),
        g("partnerNameTamil"), g("partnerDays", 0), g("staffNameTamil"), g("staffDays", 0),
        g("partTimeStaffName"), g("partTimeStaffDays", 0), g("electricityBill", 0),
        g("rentOwnerName"), g("rentAmount", 0), g("phoneWifiAmount", 0), g("waterTax", 0), g("photocopyAmount", 0),
        g("busPurpose"), g("busDate"), g("busAmount", 0),
        g("travelPurpose"), g("travelDate"), g("travelAmount", 0),
        g("postalAmount", 0),
        g("registerItem"), g("registerAmount", 0),
        g("stationeryItem"), g("stationeryAmount", 0),
        g("electricalItem"), g("electricalAmount", 0),
        g("consumerItem"), g("consumerAmount", 0),
        g("otherExpense1Desc"), g("otherExpense1Amount", 0),
        g("otherExpense2Desc"), g("otherExpense2Amount", 0),
        _s(data.get("monthYear")),           # AW
        "",                                    # placeholder, uniqueKey column AY கீழே set ஆகும்
        g("paper14", 0), g("paper15", 0), g("paper16", 0), g("paper17", 0), g("paper18", 0),
    ]


def submit_or_update_contingent(data):
    try:
        library_name = _s(data.get("libraryName"))
        month_year = _s(data.get("monthYear"))

        if not library_name or not month_year:
            return {"success": False, "message": "நூலக பெயர் அல்லது மாதம்/வருடம் காலியாக உள்ளது"}

        library_code = get_library_code(library_name)
        if not library_code:
            return {"success": False, "message": f"நூலக குறியீடு கிடைக்கவில்லை: {library_name}"}

        unique_key = generate_unique_key(library_code, month_year)

        sh = _get_contingent_sheet()
        values = sh.get_all_values()

        existing_row_index = None
        for i in range(1, len(values)):
            row_key = _s(values[i][49]) if len(values[i]) > 49 else ""
            if row_key == unique_key:
                existing_row_index = i + 1
                break

        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        row_data = _build_row(data, timestamp)
        row_data[49] = unique_key  # AY column (0-based idx 49)

        if existing_row_index:
            end_col = chr(ord("A") + len(row_data) - 1)
            sh.update(f"A{existing_row_index}:{end_col}{existing_row_index}", [row_data],
                      value_input_option="USER_ENTERED")
            # BD/BE (columns 56,57 1-based) clear பண்ணுதல்
            try:
                sh.update(f"BD{existing_row_index}:BE{existing_row_index}", [["", ""]])
            except Exception:
                pass
            result_row = existing_row_index
            action = "updated"
        else:
            sh.append_row(row_data, value_input_option="USER_ENTERED")
            result_row = len(sh.get_all_values())
            action = "created"

        return {"success": True, "row": result_row, "action": action}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ------------------------------------------------------------
# getAvailableMonthsForLibrary — Drive folder-ல் PDF பட்டியல்
# ------------------------------------------------------------
def _normalize_library_name(s):
    s = _s(s)
    s = re.sub(r"^[^.]*\.", "", s)   # முதல் "." வரை உள்ள prefix நீக்கு
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def get_available_months_for_library(library_name):
    try:
        if not library_name:
            return {"success": False, "message": "நூலக பெயர் கிடைக்கவில்லை"}
        if not APPROVAL_PDF_FOLDER_ID:
            return {"success": False, "message": "APPROVAL_PDF_FOLDER_ID configured இல்லை"}

        target_name = _normalize_library_name(library_name)
        drive = get_drive()

        result = []
        page_token = None
        query = f"'{APPROVAL_PDF_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false"
        while True:
            resp = drive.files().list(
                q=query, fields="nextPageToken, files(id, name)",
                pageToken=page_token, pageSize=1000
            ).execute()
            for f in resp.get("files", []):
                file_name = f["name"]
                segments = file_name.split(" - ")
                name_part = _normalize_library_name(segments[0] if segments else "")
                if name_part == target_name:
                    month_year = ""
                    if len(segments) > 1:
                        month_year = re.sub(r"\.pdf$", "", segments[1], flags=re.IGNORECASE).strip()
                    result.append({"fileId": f["id"], "fileName": file_name, "monthYear": month_year})
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        def sort_key(item):
            parts = (item["monthYear"] or "0/0").split("/")
            try:
                m, y = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                m, y = 0, 0
            return (-y, -m)

        result.sort(key=sort_key)

        if not result:
            return {"success": False, "message": "இந்த நூலகத்திற்கு PDF கிடைக்கவில்லை"}
        return {"success": True, "months": result}
    except Exception as e:
        return {"success": False, "message": f"Server பிழை: {e}"}


# ------------------------------------------------------------
# shareApprovedExpenseMailByFileId / shareReceiptAcknowledgementByFileId
# இரண்டுமே ஒரே logic (Drive file-ஐ "anyone with link" ஆக்கி,
# loginEmail-க்கும் தனியா viewer access கொடுக்க முயற்சி) —
# ஒரே helper function-ஐ பகிர்ந்துகொள்கிறோம்.
# ------------------------------------------------------------
def _share_drive_file(login_email, file_id):
    if not file_id or not login_email:
        return {"success": False, "message": "கோப்பு ID அல்லது மின்னஞ்சல் கிடைக்கவில்லை"}
    try:
        drive = get_drive()
        drive.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"}
        ).execute()
        try:
            drive.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "user", "emailAddress": login_email},
                sendNotificationEmail=False,
            ).execute()
        except Exception:
            pass  # GAS-ல் safeAddViewer_ மாதிரியே — தோல்வியானாலும் தொடரும்

        meta = drive.files().get(fileId=file_id, fields="webViewLink").execute()
        return {
            "success": True,
            "message": "லிங்க் தயார் — கீழே கிளிக் செய்து PDF-ஐ பார்க்கலாம்",
            "fileId": file_id,
            "originalUrl": meta.get("webViewLink"),
            "url": meta.get("webViewLink"),
        }
    except Exception as e:
        return {"success": False, "message": f"Server பிழை: {e}"}


def share_approved_expense_mail_by_file_id(login_email, file_id):
    return _share_drive_file(login_email, file_id)


def share_receipt_acknowledgement_by_file_id(login_email, file_id):
    return _share_drive_file(login_email, file_id)


# ------------------------------------------------------------
# getAvailableMonthsForLibraryAcknowledgement
# கோப்பு பெயர்: "Acknowledgement_<code>.<libraryName>_<mm-yyyy>.pdf"
# ------------------------------------------------------------
def get_available_months_for_library_acknowledgement(library_name):
    try:
        if not library_name:
            return {"success": False, "message": "நூலக பெயர் கிடைக்கவில்லை"}
        if not ACK_PDF_FOLDER_ID:
            return {"success": False, "message": "ACK_PDF_FOLDER_ID configured இல்லை"}

        target_name = _normalize_library_name(library_name)
        drive = get_drive()

        result = []
        page_token = None
        query = f"'{ACK_PDF_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false"
        while True:
            resp = drive.files().list(
                q=query, fields="nextPageToken, files(id, name)",
                pageToken=page_token, pageSize=1000
            ).execute()
            for f in resp.get("files", []):
                file_name = f["name"]
                base_name = re.sub(r"\.pdf$", "", file_name, flags=re.IGNORECASE)
                first_us = base_name.find("_")
                last_us = base_name.rfind("_")
                if first_us == -1 or last_us == -1 or first_us == last_us:
                    continue
                middle = base_name[first_us + 1:last_us]
                raw_month_year = base_name[last_us + 1:].strip()
                name_part = _normalize_library_name(middle)
                if name_part == target_name:
                    result.append({
                        "fileId": f["id"],
                        "fileName": file_name,
                        "monthYear": raw_month_year.replace("-", "/"),
                    })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        def sort_key(item):
            parts = (item["monthYear"] or "0/0").split("/")
            try:
                m, y = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                m, y = 0, 0
            return (-y, -m)

        result.sort(key=sort_key)

        if not result:
            return {"success": False, "message": "இந்த நூலகத்திற்கு வரவு ஒப்புதல் PDF கிடைக்கவில்லை"}
        return {"success": True, "months": result}
    except Exception as e:
        return {"success": False, "message": f"Server பிழை: {e}"}


# ------------------------------------------------------------
# RECEIPTS (வரவினங்கள்) — RECEIPTS_SHEET_ID / "Form responses 1"
# Columns: F(5)=UTR, G(6)=Date, H..Q(7-16)=amounts, R(17)=Total,
#          S(18)=Visitors, T(19)=Issues, U(20)=Usage
# ------------------------------------------------------------
RECEIPT_AMOUNT_KEYS = [
    "deposit", "subscription", "lateFee", "bookFine", "oldPaperSale",
    "oldBookSale", "patron", "chiefPatron", "donor", "otherIncome",
]


def _get_receipts_sheet():
    return get_client().open_by_key(RECEIPTS_SHEET_ID).worksheet(RECEIPTS_SHEET_NAME)


def get_existing_receipt_by_utr(utr):
    try:
        sh = _get_receipts_sheet()
        data = sh.get_all_values()
        clean_utr = _s(utr)
        for i in range(1, len(data)):
            row = data[i]
            row_utr = _s(row[5]) if len(row) > 5 else ""
            if row_utr == clean_utr:
                def num(idx):
                    try:
                        return float(row[idx]) if len(row) > idx and row[idx] not in ("", None) else 0
                    except ValueError:
                        return 0
                return {
                    "success": True,
                    "rowIndex": i + 1,
                    "data": {
                        "utr": row_utr,
                        "date": row[6] if len(row) > 6 else "",
                        "deposit": num(7), "subscription": num(8), "lateFee": num(9),
                        "bookFine": num(10), "oldPaperSale": num(11), "oldBookSale": num(12),
                        "patron": num(13), "chiefPatron": num(14), "donor": num(15),
                        "otherIncome": num(16), "total": num(17),
                        "visitors": num(18), "issues": num(19), "usage": num(20),
                    },
                }
        return {"success": False}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _get_bank_sheet():
    return get_client().open_by_key(BANK_SHEET_ID).worksheet(BANK_SHEET_NAME)


def _sheet_serial_to_date(value):
    """Google Sheets date serial number (days since 1899-12-30) -> datetime.
    value ஒரு string date-ஆ இருந்தாலும் handle பண்ணும்."""
    if value in (None, ""):
        return None
    # Sheets serial number (எண்ணா இருந்தா)
    if isinstance(value, (int, float)):
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(value))
        except (OverflowError, ValueError):
            return None
    # String date — பல formats முயற்சி
    raw = str(value).strip()
    # numeric string (serial number text ஆக வந்தாலும்)
    try:
        serial = float(raw)
        return datetime(1899, 12, 30) + timedelta(days=serial)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def validate_payment_with_bank(utr_number):
    if not utr_number:
        return {"success": False, "message": "UTR எண் கொடுக்கப்படவில்லை"}
    try:
        sh = _get_bank_sheet()
        # B,C,D,E columns (Date, UTR, Amount, UsedLibrary) row 2 onwards
        # UNFORMATTED_VALUE — தேதி Sheets serial number-ஆக துல்லியமா கிடைக்கும்
        rows = sh.get("B2:E", value_render_option="UNFORMATTED_VALUE")
        clean_utr = _s(utr_number)

        today = datetime.now()
        current_month, current_year = today.month - 1, today.year  # 0-based like JS
        last_month, last_month_year = current_month - 1, current_year
        if last_month < 0:
            last_month, last_month_year = 11, current_year - 1

        for idx, row in enumerate(rows):
            date_raw = row[0] if len(row) > 0 else ""
            utr = _s(row[1]) if len(row) > 1 else ""
            amt = row[2] if len(row) > 2 else 0
            used_library = _s(row[3]) if len(row) > 3 else ""

            if utr != clean_utr:
                continue

            txn_date = _sheet_serial_to_date(date_raw)

            if txn_date is not None:
                txn_month, txn_year = txn_date.month - 1, txn_date.year
                if (txn_year < last_month_year) or (txn_year == last_month_year and txn_month < last_month):
                    return {"success": False,
                            "message": "⚠️ இன்னும் அலுவலகத்தால் கடந்த மாத வங்கி அறிக்கை பதிவேற்றம் செய்யப்படவில்லை தயவு செய்து காத்திருக்கவும்"}

            if used_library:
                return {"success": False,
                        "message": f"❌ {used_library} இந்த UTR எண்ணை பயன்படுத்தியுள்ளார். சரிபார்க்கவும் அல்லது அலுவலகத்தை தொடர்பு கொள்ளவும்."}

            if txn_date is None:
                return {"success": False, "message": "இந்த UTR-ன் தேதியை படிக்க முடியவில்லை. Bank sheet-ல் Date column format-ஐ சரிபார்க்கவும்."}

            return {
                "success": True,
                "date": txn_date.strftime("%Y-%m-%d"),   # HTML date input-க்கு கட்டாயம் இந்த format தேவை
                "amount": float(amt) if amt not in ("", None) else 0,
                "row": idx + 2,
            }

        return {"success": False, "message": "இந்த UTR Bank Sheet-ல் இல்லை"}
    except Exception as e:
        return {"success": False, "message": f"Server பிழை: {e}"}


def lock_utr_to_library(utr_number, data):
    try:
        sh = _get_bank_sheet()
        rows = sh.get("C2:C")
        clean_utr = _s(utr_number)
        for idx, row in enumerate(rows):
            utr = _s(row[0]) if row else ""
            if utr == clean_utr:
                row_num = idx + 2
                values = [
                    data.get("libraryName", ""),
                    data.get("deposit", 0), data.get("subscription", 0), data.get("lateFee", 0),
                    data.get("bookFine", 0), data.get("oldPaperSale", 0), data.get("oldBookSale", 0),
                    data.get("patron", 0), data.get("chiefPatron", 0), data.get("donor", 0),
                    data.get("otherIncome", 0), data.get("total", 0),
                    data.get("visitors", 0), data.get("issues", 0), data.get("usage", 0),
                ]
                sh.update(f"E{row_num}:S{row_num}", [values], value_input_option="USER_ENTERED")
                return {"success": True}
        return {"success": False}
    except Exception:
        return {"success": False}


def save_or_update_receipt(data):
    try:
        sh = _get_receipts_sheet()
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        utr = _s(data.get("utr"))

        month_year = _s(data.get("monthYear"))
        if not month_year:
            now = datetime.now()
            month_year = f"{now.month:02d}/{now.year}"
        unique_key = f"{_s(data.get('libraryName'))}_{month_year}"
        if not utr:
            utr = unique_key

        total = sum(float(data.get(k, 0) or 0) for k in RECEIPT_AMOUNT_KEYS)
        data["total"] = total

        row_data = [
            timestamp, data.get("loginEmail", ""), data.get("libraryType", ""), "",
            data.get("libraryName", ""), utr, data.get("date", ""),
            data.get("deposit", 0), data.get("subscription", 0), data.get("lateFee", 0),
            data.get("bookFine", 0), data.get("oldPaperSale", 0), data.get("oldBookSale", 0),
            data.get("patron", 0), data.get("chiefPatron", 0), data.get("donor", 0),
            data.get("otherIncome", 0), total,
            data.get("visitors", 0), data.get("issues", 0), data.get("usage", 0),
        ]

        existing = get_existing_receipt_by_utr(utr) if utr else {"success": False}

        if existing.get("success"):
            row_index = existing["rowIndex"]
            end_col = chr(ord("A") + len(row_data) - 1)
            sh.update(f"A{row_index}:{end_col}{row_index}", [row_data], value_input_option="USER_ENTERED")
            result_row = row_index
            action = "updated"
        else:
            sh.append_row(row_data, value_input_option="USER_ENTERED")
            result_row = len(sh.get_all_values())
            action = "created"

        if data.get("utr"):
            lock_utr_to_library(data.get("utr"), data)

        return {"success": True, "row": result_row, "action": action, "total": total}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ==================== நடப்பு ஆண்டு சுருக்கம் (Yearly Abstract) ====================
# GAS-ல் sendYearlyReceiptAbstract() / sendYearlyExpenseAbstract()-ன் Python port.
# ஏற்கனவே கணக்கிடப்பட்டுள்ள "receipt abstract" / "expense abstract" tabs-ஐ
# ABSTRACT_SOURCE_SHEET_ID-ல் இருந்து படித்து, நூலக பெயர் வாரியாக filter
# செய்து, HTML அட்டவணையாக உருவாக்கி PDF-ஆக Drive-ல் சேமிக்கிறோம்
# (GAS-ல் SpreadsheetApp export URL trick பயன்படுத்தப்பட்டது — service
# account context-ல் அது சிக்கலானது என்பதால், pdf_service.py-ல் ஏற்கனவே
# இருக்கும் அதே xhtml2pdf HTML→PDF வழியை பயன்படுத்துகிறோம்).

def _current_fiscal_year_label():
    """ஏப்ரல்-மார்ச் அரசு நிதியாண்டு அடிப்படையில் 'நடப்பு ஆண்டு' label
    (எ.கா. இன்று ஜூலை 2026 எனில் -> '2026-2027')."""
    now = datetime.now()
    start_year = now.year if now.month >= 4 else now.year - 1
    return f"{start_year}-{start_year + 1}"


def _num(row, idx):
    try:
        v = row[idx] if len(row) > idx else 0
        return float(v) if v not in ("", None) else 0.0
    except (ValueError, TypeError):
        return 0.0


def _drop_empty_amount_columns(header, out_rows, keep_last_n=1):
    """header/out_rows-ல் இருக்கும் amount columns-ல் (S.No, Month தவிர்த்து)
    எல்லா rows-லும் value இல்லாத (0/''/None) columns-ஐ முழுசா நீக்கிவிடும்.
    நூலகத்திற்கு நூலகம் active categories வேறு வேறா இருப்பதால் (சிலவற்றுக்கு
    4 categories, சிலவற்றுக்கு 8), இப்படி dynamic-ஆ column-ஐ நீக்கினால்
    table இன்னும் தெளிவா, பரந்த columns-ஆக வரும்.
    keep_last_n: கடைசியில் இருக்கும் இத்தனை columns (மொத்தம்/grand-total
    வகை columns) எப்போதும் வைக்கப்படும், அவை எல்லா rows-லும் 0 ஆக
    இருந்தாலும் சரி."""
    n_amount_cols = len(header) - 2
    if n_amount_cols <= 0:
        return header, out_rows

    def _is_empty(v):
        return v in (0, "", None) or v == 0.0

    keep = []
    for i in range(n_amount_cols):
        if keep_last_n and i >= n_amount_cols - keep_last_n:
            keep.append(True)
            continue
        has_value = any(
            (len(r) > 2 + i and not _is_empty(r[2 + i]))
            for r in out_rows
        )
        keep.append(has_value)

    new_header = header[:2] + [header[2 + i] for i in range(n_amount_cols) if keep[i]]
    new_out_rows = [
        r[:2] + [r[2 + i] for i in range(n_amount_cols) if keep[i]]
        for r in out_rows
    ]
    return new_header, new_out_rows


def _yearly_abstract_html(library_name, subtitle, header, out_rows, landscape=True):
    """out_rows-ன் ஒவ்வொரு row-ம்: [S.No, Month, amount1, amount2, ...] —
    முதல் 2 columns தவிர மீதி எல்லாம் தொகைகள் (மொத்தம் row-க்கு sum ஆகும்)."""
    size_css = "size: A4 landscape;" if landscape else "size: A4;"

    n_amount_cols = len(header) - 2

    # --- column widths: S.No குறுகலாக, Month சற்று அகலமாக, மீதி
    # amount columns-ஆக equal-ஆக பிரிக்கப்படும் ---
    sno_w = 3.5
    month_w = 9.0 if n_amount_cols <= 12 else 6.0
    amount_w = (100 - sno_w - month_w) / n_amount_cols if n_amount_cols else 0

    # முக்கியமான fix: xhtml2pdf, <colgroup><col width> -ஐ நம்பமுடியாத
    # அளவுக்கு handle பண்ணுது — ஒரு column-ல் இருக்கும் எல்லா cell-களும்
    # காலியா (empty string) இருந்தால், table-layout:fixed இருந்தும் அந்த
    # column-ஐ width இல்லாமல் சுருக்கிவிடுது (இதனால் தான் columns ஒன்றன்
    # மேல் ஒன்று மேலெழுதி வந்தது). இதை தவிர்க்க:
    #   1. width-ஐ <colgroup> வழியாக மட்டும் இல்லாமல் ஒவ்வொரு <th>/<td>-லும்
    #      நேரடியா style="width:...%" ஆக போடுகிறோம்.
    #   2. வெறும் காலியாக (0/''/None) இருக்கும் cell-ல் "" போடாமல்
    #      "&nbsp;"-ஐ போடுகிறோம், அதனால் cell content ஒரு போதும்
    #      முழுக்க காலியாக இராது, column collapse ஆகாது.
    def _w(i):
        if i == 0:
            return sno_w
        if i == 1:
            return month_w
        return amount_w

    thead = "".join(f'<th style="width:{_w(i):.3f}%">{h}</th>' for i, h in enumerate(header))

    totals = [0.0] * n_amount_cols
    body_rows = ""
    for r in out_rows:
        cells = "".join(
            f'<td style="width:{_w(i):.3f}%">{("&nbsp;" if v in (0, "", None) else v)}</td>'
            for i, v in enumerate(r)
        )
        body_rows += f"<tr>{cells}</tr>"
        for i in range(n_amount_cols):
            val = r[2 + i] if len(r) > 2 + i else 0
            try:
                totals[i] += float(val) if val not in ("", None) else 0
            except (ValueError, TypeError):
                pass

    total_cells = "".join(
        f'<td style="width:{amount_w:.3f}%">{"₹" + format(t, ",.0f") if t else "&nbsp;"}</td>'
        for t in totals
    )

    # amount column எண்ணிக்கை அதிகமா இருந்தால் (செலவு அறிக்கை — 23 columns)
    # header/body font-size சிறிதாக்கவும், அதிக columns-க்கும் table சரியாக பொருந்தும்
    th_font = "6.5px" if n_amount_cols > 12 else "8.5px"
    td_font = "7px" if n_amount_cols > 12 else "9px"

    return f"""<!DOCTYPE html>
<html lang="ta"><head><meta charset="UTF-8"><style>
{TAMIL_FONT_FACE_CSS}
  @page {{ {size_css} margin: 8mm; }}
  body {{ font-family: 'NotoTamil', 'Arial Unicode MS', sans-serif; font-size: {td_font}; color:#000; }}
  h1 {{ text-align:center; font-size:15px; margin:2px 0; }}
  h2 {{ text-align:center; font-size:12px; margin:2px 0 10px; }}
  table {{ width:100%; table-layout:fixed; border-collapse:collapse; }}
  th, td {{ border:1px solid #000; padding:{"1px" if n_amount_cols > 12 else "3px"} 1px; text-align:center;
           word-wrap:break-word; overflow-wrap:break-word; line-height:1.15; }}
  th {{ background:#e0f2fe; font-weight:bold; font-size:{th_font}; }}
  tr.total td {{ font-weight:bold; background:#f3f4f6; }}
</style></head><body>
  <h1>{_esc_html(library_name).upper()}</h1>
  <h2>{_esc_html(subtitle)}</h2>
  <table>
    <thead><tr>{thead}</tr></thead>
    <tbody>
      {body_rows}
      <tr class="total"><td colspan="2">மொத்தம்</td>{total_cells}</tr>
    </tbody>
  </table>
</body></html>"""


def _esc_html(v):
    return "" if v is None else str(v)


def _save_yearly_abstract_pdf(file_name, pdf_bytes, folder_id, login_email):
    """குறிப்பிட்ட Drive folder-ல் இதே பெயரில் இருக்கும் பழைய PDF-ஐ நீக்கிவிட்டு,
    புதிய PDF-ஐ upload செய்து, anyone-with-link + login_email viewer ஆக share செய்யும்."""
    try:
        drive = get_drive()

        existing = drive.files().list(
            q=f"'{folder_id}' in parents and name='{file_name}' and trashed=false",
            fields="files(id)"
        ).execute()
        for f in existing.get("files", []):
            try:
                drive.files().delete(fileId=f["id"]).execute()
            except Exception:
                pass

        media = MediaIoBaseUpload(BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False)
        file = drive.files().create(
            body={"name": file_name, "parents": [folder_id]},
            media_body=media, fields="id, webViewLink"
        ).execute()
        file_id = file["id"]

        drive.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
        if login_email and "@" in login_email:
            try:
                drive.permissions().create(
                    fileId=file_id,
                    body={"role": "reader", "type": "user", "emailAddress": login_email},
                    sendNotificationEmail=False,
                ).execute()
            except Exception:
                pass  # safeAddViewer_ மாதிரியே — தோல்வியானாலும் தொடரும்

        meta = drive.files().get(fileId=file_id, fields="webViewLink").execute()
        return {
            "success": True,
            "message": "லிங்க் தயார் — கீழே கிளிக் செய்து PDF-ஐ பார்க்கலாம்",
            "fileId": file_id,
            "url": meta.get("webViewLink"),
            "originalUrl": meta.get("webViewLink"),
        }
    except Exception as e:
        return {"success": False, "message": f"Server பிழை: {e}"}


# ------------------------------------------------------------
# sendYearlyReceiptAbstract — "receipt abstract" tab column layout:
# col1(B)=library, col0(A)=month label, col4..13(E..N)=10 income categories
#
# குறிப்பு: Service Account-க்கு Drive storage quota இல்லாததால்
# (storageQuotaExceeded), இனி Drive-ல் PDF-ஐ upload செய்யாமல்,
# app.py-ல் இருக்கும் /pettycash/yearly_receipt_pdf GET route
# மூலம் நேரடியாக PDF-ஐ browser-க்கு stream செய்கிறோம்.
# ------------------------------------------------------------
def build_yearly_receipt_abstract_pdf(library_name):
    """(pdf_bytes, None) வெற்றியானால், (None, error_message) தோல்வியானால்."""
    try:
        if not library_name:
            return None, "நூலக பெயர் கிடைக்கவில்லை"
        if not ABSTRACT_SOURCE_SHEET_ID:
            return None, "ABSTRACT_SOURCE_SHEET_ID configured இல்லை"

        sh = get_client().open_by_key(ABSTRACT_SOURCE_SHEET_ID).worksheet(ABSTRACT_RECEIPT_SHEET_NAME)
        data = sh.get_all_values()
        rows = [r for r in data[1:] if len(r) > 1 and _s(r[1]) == _s(library_name)]
        if not rows:
            return None, "இந்த நூலகத்திற்கு தரவு இல்லை"

        header = ["S.No", "Month", "காப்புத் தொகை", "சந்தா", "காலக்கடப்பு",
                  "நூல் விலைப் பிடித்தம்", "பழைய இதழ் விற்பனை", "பழைய நூல் விற்பனை",
                  "புரவலர்", "பெரும்புரவலர்", "கொடையாளர்", "இதர வரவு", "மொத்தம்"]

        out_rows = []
        for i, r in enumerate(rows):
            nums = [_num(r, c) for c in range(4, 14)]
            total = sum(nums)
            out_rows.append(
                [i + 1, r[0] if r else ""] +
                [("" if n == 0 else n) for n in nums] +
                [("" if total == 0 else total)]
            )

        header, out_rows = _drop_empty_amount_columns(header, out_rows)

        html = _yearly_abstract_html(
            library_name, f"நூலக வரவு சுருக்கம் {_current_fiscal_year_label()}",
            header, out_rows, landscape=True,
        )
        return _html_to_pdf_bytes(html), None
    except Exception as e:
        return None, f"Server பிழை: {e}"


def send_yearly_receipt_abstract(login_email, library_name):
    """POST handler — இனி Drive-ல் எதுவும் create செய்யாது; வெறும்
    GET PDF route-ன் URL-ஐ திருப்பி அனுப்புகிறோம் (frontend அதே
    res.url / res.originalUrl-ஐ <a href> ஆக காட்டும்)."""
    if not library_name:
        return {"success": False, "message": "நூலக பெயர் கிடைக்கவில்லை"}
    url = f"/pettycash/yearly_receipt_pdf?library={quote(library_name)}"
    return {"success": True, "message": "PDF தயார்", "url": url, "originalUrl": url}


# ------------------------------------------------------------
# sendYearlyExpenseAbstract — "expense abstract" tab column layout:
# col2(C)=library, col0(A)=month (raw date/text), specific columns for
# each expense category (GAS Code.gs-ல் இருந்ததே அப்படியே — column
# index-கள் மாறாமல் வைக்கப்பட்டுள்ளது).
# ------------------------------------------------------------
def build_yearly_expense_abstract_pdf(library_name):
    """(pdf_bytes, None) வெற்றியானால், (None, error_message) தோல்வியானால்."""
    try:
        if not library_name:
            return None, "நூலக பெயர் கிடைக்கவில்லை"
        if not ABSTRACT_SOURCE_SHEET_ID:
            return None, "ABSTRACT_SOURCE_SHEET_ID configured இல்லை"

        sh = get_client().open_by_key(ABSTRACT_SOURCE_SHEET_ID).worksheet(ABSTRACT_EXPENSE_SHEET_NAME)
        data = sh.get_all_values()
        rows = [r for r in data[1:] if len(r) > 2 and _s(r[2]) == _s(library_name)]
        if not rows:
            return None, "இந்த நூலகத்திற்கு செலவு தரவு இல்லை"

        header = [
            "வரிசை எண்", "மாதம்", "நாளிதழ்கள்", "வாடகை", "மின் கட்டணம்",
            "தினக்கூலி பகுதிநேரத் துப்புரவாளர்", "தினக்கூலி நூலகர்",
            "தினக்கூலிக் காவலர்", "தினக்கூலி ஒட்டுநர்",
            "தினக்கூலி கணினி தட்டச்சர்", "தினக்கூலி பகுதிநேர நூலகர்",
            "பேருந்து கட்டணம்", "எழுது பொருட்கள் வாங்குதல்",
            "நுகர்பொருள் வாங்குதல்", "மின்சாதனங்கள் வாங்குதல்",
            "அஞ்சல் செலவினம்", "நகலெடுக்கும் கட்டணம்",
            "பிற செலவினங்கள் 1", "பிற செலவினங்கள் 2",
            "போக்குவரத்து கட்டணம்", "குடிநீர் கட்டணம்",
            "தொலைபேசி கட்டணம்", "கழிவறை சுத்தம் செய்தல்",
            "மொத்த செலவினம் (நாளிதழ்/வாடகை தவிர்த்து)",
            "மொத்த செலவினம்",
        ]
        AMOUNT_COLS = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
                       15, 16, 17, 18, 19, 21, 23, 25,
                       26, 27, 29, 30, 31]

        out_rows = []
        for i, r in enumerate(rows):
            nums = [_num(r, c) for c in AMOUNT_COLS]
            out_rows.append([i + 1, r[0] if r else ""] + nums)

        header, out_rows = _drop_empty_amount_columns(header, out_rows, keep_last_n=2)

        html = _yearly_abstract_html(
            library_name, f"நூலக ஆண்டு செலவின சுருக்கம் {_current_fiscal_year_label()}",
            header, out_rows, landscape=True,
        )
        return _html_to_pdf_bytes(html), None
    except Exception as e:
        return None, f"Server பிழை: {e}"


def send_yearly_expense_abstract(login_email, library_name):
    """POST handler — இனி Drive-ல் எதுவும் create செய்யாது; வெறும்
    GET PDF route-ன் URL-ஐ திருப்பி அனுப்புகிறோம்."""
    if not library_name:
        return {"success": False, "message": "நூலக பெயர் கிடைக்கவில்லை"}
    url = f"/pettycash/yearly_expense_pdf?library={quote(library_name)}"
    return {"success": True, "message": "PDF தயார்", "url": url, "originalUrl": url}
