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
from datetime import datetime

import gspread
from googleapiclient.discovery import build

from sheets_service import _get_credentials  # ஒரே Service Account, எல்லா sheets/drive-க்கும்

# ------------------------------------------------------------
# Config (env vars)
# ------------------------------------------------------------
LIBRARY_DATA_SPREAD_ID   = os.environ["LIBRARY_DATA_SPREAD_ID"]
LIBRARY_DATA_SHEET_NAME  = os.environ.get("LIBRARY_DATA_SHEET_NAME", "Sheet1")

CONTINGENT_SHEET_ID      = os.environ["CONTINGENT_SHEET_ID"]
CONTINGENT_SHEET_NAME    = os.environ.get("CONTINGENT_SHEET_NAME", "contingent")

APPROVAL_PDF_FOLDER_ID   = os.environ.get("APPROVAL_PDF_FOLDER_ID", "")

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
