"""
drive_service.py
------------------------------------------------------------
Service Account மூலம் Google Drive-ல் PDF file-ஐ upload செய்து,
"anyone with the link can view" ஆக share செய்யும்.
------------------------------------------------------------
"""

import os
from io import BytesIO

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from sheets_service import _get_credentials

DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

_drive = None


def get_drive_service():
    global _drive
    if _drive is None:
        _drive = build("drive", "v3", credentials=_get_credentials())
    return _drive


def upload_pdf(file_name, pdf_bytes):
    drive = get_drive_service()

    file_metadata = {"name": file_name, "parents": [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False)

    file = drive.files().create(
        body=file_metadata, media_body=media, fields="id, webViewLink"
    ).execute()

    file_id = file["id"]
    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()

    result = drive.files().get(fileId=file_id, fields="webViewLink").execute()
    return result["webViewLink"]
