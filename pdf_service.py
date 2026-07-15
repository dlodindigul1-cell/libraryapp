"""
pdf_service.py
------------------------------------------------------------
GAS-ன் buildApplicationHTML() / buildELMLApplicationHTML() /
sendLeaveApplicationEmail() / sendELMLApplicationEmail()
functions-ஐ port செய்யப்பட்ட பதிப்பு.

வித்தியாசம் (v2): Service Account-க்கு Drive storage quota
இல்லாததால் (storageQuotaExceeded), இனி Drive-ல் PDF-ஐ upload
செய்யாமல் — உருவாக்கிய PDF-ஐ சிறிது நேரம் memory-ல் வைத்து,
app.py-ல் இருக்கும் /leave/pdf/<token> GET route மூலம்
நேரடியாக browser-க்கு stream செய்கிறோம் (Gmail-க்கும் அனுப்பாது,
frontend-ல் "PDF திறக்கவும்" link ஏற்கனவே இதை காட்டும்).
------------------------------------------------------------
"""

import os
import time
import uuid
import pathlib
import smtplib
from email.message import EmailMessage
from io import BytesIO
from flask import request
from weasyprint import HTML as _WeasyHTML
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from sheets_service import _get_credentials

# ------------------------------------------------------------
# Email அனுப்புதல் (Gmail SMTP + App Password)
# ------------------------------------------------------------
# Service Account-க்கு GmailApp.sendEmail() போன்ற ஒன்று கிடையாது
# (domain-wide delegation இல்லாத personal Gmail-க்கு). அதனால் ஒரு
# சாதாரண Gmail account-ன் "App Password" மூலம் SMTP-ஆக அனுப்புகிறோம்.
# GMAIL_ADDRESS / GMAIL_APP_PASSWORD env vars set ஆகி இல்லைன்னா,
# silent-ஆ skip பண்ணி (PDF link மட்டும்) பழையபடி வேலை செய்யும்.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# ------------------------------------------------------------
# Render, raw SMTP (port 465/587) outbound connection-ஐ block
# செய்வதால் ([Errno 101] Network is unreachable), Gmail SMTP
# வேலை செய்யாது. அதனால் Drive API (HTTPS-ல் ஓடுவதால் block
# ஆகாது) மூலம் PDF-ஐ upload செய்து, sendNotificationEmail=True
# கொடுத்து Google-ஐயே notification அனுப்ப வைக்கிறோம் — இதுவே
# இப்போதைய முதன்மை வழி (SMTP இன்னும் இருக்கிறது, ஆனால் Render-ல்
# எப்போதும் தோல்வியடையும்).
# ------------------------------------------------------------
LEAVE_PDF_FOLDER_ID = os.environ.get("LEAVE_PDF_FOLDER_ID", "")

_leave_drive = None


def _get_leave_drive():
    global _leave_drive
    if _leave_drive is None:
        _leave_drive = build("drive", "v3", credentials=_get_credentials())
    return _leave_drive


def _upload_and_share_pdf(pdf_bytes, file_name, to_email):
    """PDF-ஐ LEAVE_PDF_FOLDER_ID-ல் upload செய்து, to_email-க்கு
    Viewer access + Google-ன் தானியங்கி notification email-ஐ
    கொடுக்கும். (drive_url, shared: bool, error: str|None) திருப்பும்."""
    if not LEAVE_PDF_FOLDER_ID:
        return None, False, "LEAVE_PDF_FOLDER_ID configured இல்லை"
    try:
        drive = _get_leave_drive()
        media = MediaIoBaseUpload(BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False)
        file = drive.files().create(
            body={"name": file_name, "parents": [LEAVE_PDF_FOLDER_ID]},
            media_body=media,
            fields="id, webViewLink",
        ).execute()
        file_id = file["id"]

        shared, share_error = False, None
        if to_email and "@" in to_email:
            try:
                drive.permissions().create(
                    fileId=file_id,
                    body={"role": "reader", "type": "user", "emailAddress": to_email},
                    sendNotificationEmail=True,
                    emailMessage="உங்கள் விடுப்பு விண்ணப்பம் (PDF) இணைக்கப்பட்டுள்ளது. கீழே உள்ள கோப்பை கிளிக் செய்து பார்க்கலாம்.",
                ).execute()
                shared = True
            except Exception as e:
                share_error = str(e)
        else:
            share_error = "பணியாளர் மின்னஞ்சல் கிடைக்கவில்லை"

        meta = drive.files().get(fileId=file_id, fields="webViewLink").execute()
        return meta.get("webViewLink"), shared, share_error
    except Exception as e:
        return None, False, str(e)


def _absolute_url(path):
    """Email body-க்குள் இருக்கும் link வேலை செய்ய, absolute URL தேவை
    (relative path email client-ல் broken-ஆ இருக்கும்). Flask request
    context கிடைக்காத நேரங்களில் (எ.கா local testing) path-ஐயே திருப்பும்."""
    try:
        return request.url_root.rstrip("/") + path
    except RuntimeError:
        return path


def _send_email_with_pdf(to_email, subject, html_body, pdf_bytes, pdf_filename):
    """Gmail SMTP மூலம் PDF-ஐ attachment-ஆ சேர்த்து மெயில் அனுப்பும்.
    (sent: bool, error: str|None) திருப்பும்."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return False, "GMAIL_ADDRESS/GMAIL_APP_PASSWORD configured இல்லை"
    if not to_email or "@" not in to_email:
        return False, "பணியாளர் மின்னஞ்சல் கிடைக்கவில்லை"

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"நூலகர் விடுப்பு மேலாண்மை <{GMAIL_ADDRESS}>"
        msg["To"] = to_email
        msg.set_content("உங்கள் விடுப்பு விண்ணப்பம் PDF இணைக்கப்பட்டுள்ளது. இந்த மெயிலை HTML-ஆக பார்க்க முடியாத மெயில் app-ல் இந்த வரி தெரியும்.")
        msg.add_alternative(html_body, subtype="html")
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def _leave_mail_html(emp_name, pdf_url):
    return f"""<div style='font-family:Arial,sans-serif;font-size:14px;color:#1e293b;'>
<p>வணக்கம் <strong>{emp_name}</strong>,</p>
<p>உங்கள் விடுப்பு விண்ணப்பம் (PDF) இந்த மெயிலுடன் இணைக்கப்பட்டுள்ளது.<br>
கீழே உள்ள பட்டனை அழுத்தியும் PDF-ஐ திறக்கலாம் / பதிவிறக்கலாம்:</p>
<p style='margin:20px 0;'>
<a href='{pdf_url}' target='_blank'
style='background:#1a4f7a;color:#fff;padding:10px 22px;border-radius:8px;
text-decoration:none;font-weight:bold;font-size:14px;'>📄 PDF திறக்கவும்</a></p>
<p style='font-size:12px;color:#64748b;'>தேவைப்பட்டால் Print செய்து அலுவலகத்தில் சமர்ப்பிக்கவும்.</p>
<hr style='border:none;border-top:1px solid #e2e8f0;margin:16px 0;'>
<p style='font-size:11px;color:#94a3b8;'>தமிழ்நாடு அரசு பொது நூலகத்துறை — திண்டுக்கல் மாவட்ட நூலக ஆணைக்குழு</p>
</div>"""

# ------------------------------------------------------------
# Tamil font embedding
# ------------------------------------------------------------
# முன்பு xhtml2pdf/reportlab பயன்படுத்தினோம் — அதன் text-rendering
# engine-க்கு Indic complex-script shaping (தமிழ் உயிர்மெய் குறியீடுகள்
# எழுத்துடன் சரியாக இணைவது, எழுத்துக்கள் சரியான வரிசையில் இருப்பது
# போன்றவை) தெரியாது. இதனால் NotoSansTamil font embed ஆகியிருந்தும்,
# எழுத்துருக்கள் தவறான வரிசையில்/பிரிந்த நிலையில் "கேவலமாக" (garbled)
# வந்தது.
#
# WeasyPrint, Pango/HarfBuzz shaping pipeline-ஐ பயன்படுத்துவதால்
# தமிழ் உயிர்மெய் எழுத்துக்கள் சரியாக shape ஆகி வருகிறது. எனவே PDF
# உருவாக்கம் முழுவதும் (விடுப்பு விண்ணப்பங்கள் + ஆண்டு வரவு/செலவு
# சுருக்கங்கள்) WeasyPrint-க்கு மாற்றப்பட்டுள்ளது.
#
# @font-face src-க்கு WeasyPrint-க்கு file:// URI தேவை (வெறும்
# filesystem path கொடுத்தால் சில சூழல்களில் resolve ஆகாது) —
# gunicorn எந்த working directory-ல் இருந்தாலும் சரியாக வேலை செய்ய
# absolute path-ஐ pathlib.Path.as_uri()-ஆல் file:// URI ஆக மாற்றுகிறோம்.
# ------------------------------------------------------------
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts")
_FONT_REGULAR = os.path.join(_FONTS_DIR, "NotoSansTamil-Regular.ttf")
_FONT_BOLD = os.path.join(_FONTS_DIR, "NotoSansTamil-Bold.ttf")

_FONT_REGULAR_URI = pathlib.Path(_FONT_REGULAR).as_uri()
_FONT_BOLD_URI = pathlib.Path(_FONT_BOLD).as_uri()

TAMIL_FONT_FACE_CSS = f"""
  @font-face {{ font-family: 'NotoTamil'; src: url('{_FONT_REGULAR_URI}'); }}
  @font-face {{ font-family: 'NotoTamil'; font-weight: bold; src: url('{_FONT_BOLD_URI}'); }}
"""

# ------------------------------------------------------------
# In-memory PDF cache (Drive-க்கு பதிலாக) — token -> (pdf_bytes, created_at)
# ஒரே gunicorn worker (Procfile: "web: gunicorn app:app", -w flag இல்லை)
# process-ல் இயங்குவதால் இது போதுமானது. TTL_SECONDS கழித்து பழையவை நீக்கப்படும்.
# ------------------------------------------------------------
_PDF_CACHE = {}
_PDF_TTL_SECONDS = 30 * 60  # 30 நிமிடம்


def _store_pdf(pdf_bytes):
    now = time.time()
    # பழைய entries-ஐ சுத்தம் செய்யவும் (memory தேங்காமல் இருக்க)
    for k in [k for k, (_, ts) in _PDF_CACHE.items() if now - ts > _PDF_TTL_SECONDS]:
        _PDF_CACHE.pop(k, None)

    token = uuid.uuid4().hex
    _PDF_CACHE[token] = (pdf_bytes, now)
    return token


def get_cached_pdf(token):
    """app.py-ல் இருக்கும் /leave/pdf/<token> route இதை கூப்பிடும்.
    (pdf_bytes, None) கிடைத்தால் வெற்றி, இல்லையெனில் (None, error_message)."""
    entry = _PDF_CACHE.get(token)
    if entry is None:
        return None, "இந்த PDF link காலாவதியாகிவிட்டது — மீண்டும் PDF-ஐ உருவாக்கவும்"
    pdf_bytes, ts = entry
    if time.time() - ts > _PDF_TTL_SECONDS:
        _PDF_CACHE.pop(token, None)
        return None, "இந்த PDF link காலாவதியாகிவிட்டது — மீண்டும் PDF-ஐ உருவாக்கவும்"
    return pdf_bytes, None


def _esc(v):
    return "" if v is None else str(v)


def build_application_html(p, title):
    dates = p.get("currentDates")
    if isinstance(dates, list):
        dates_formatted = "<br>".join(dates)
    else:
        dates_formatted = _esc(dates)

    reason = _esc(p.get("reason", "")).replace("\n", "<br>")
    address = _esc(p.get("address", "")).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<style>
{TAMIL_FONT_FACE_CSS}
  @page {{ size: A4; margin: 20mm 18mm; }}
  body {{ font-family: 'NotoTamil', 'Arial Unicode MS', sans-serif;
         margin: 0; padding: 0; font-size: 13px; color: #000; }}
  .container {{ width: 100%; border: 1.5px solid #000; padding: 20px 24px; box-sizing: border-box; }}
  .title-block {{ text-align: center; margin-bottom: 18px; }}
  .title-block .dept  {{ font-size: 15px; font-weight: bold; margin-bottom: 4px; }}
  .title-block .dist  {{ font-size: 15px; font-weight: bold; margin-bottom: 4px; }}
  .title-block .leave-title {{ font-size: 14px; font-weight: bold;
    margin-top: 8px; text-decoration: underline; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  td {{ padding: 8px 6px; vertical-align: top; font-size: 13px; }}
  td:first-child {{ width: 48%; font-weight: 600; }}
  td:nth-child(2) {{ padding-left: 12px; }}
  .footer-row {{ width: 100%; margin-top: 50px; }}
  .footer-left, .footer-right {{ font-size: 13px; line-height: 2; }}
  .sign-box {{ margin-top: 30px; border-top: 1px solid #000;
              width: 160px; text-align: center; padding-top: 6px; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="title-block">
    <div class="dept">தமிழ்நாடு அரசு பொது நூலகத்துறை</div>
    <div class="dist">திண்டுக்கல் மாவட்ட நூலக ஆணைக்குழு</div>
    <div class="leave-title">{title}</div>
  </div>

  <table>
    <tr><td>1. பணியாளர் பெயர்</td><td>: {_esc(p.get('empName'))}</td></tr>
    <tr><td>2. பதவி</td><td>: {_esc(p.get('designation'))}</td></tr>
    <tr><td>3. பணியாற்றும் இடம்</td><td>: {_esc(p.get('workplace'))}</td></tr>
    <tr><td>4. மொத்த விடுப்பு நாட்கள்</td><td>: {_esc(p.get('totalLeave'))}</td></tr>
    <tr><td>5. இதுவரை எடுத்த விடுப்பு நாட்கள்</td><td>: {_esc(p.get('usedLeave'))}</td></tr>
    <tr><td>6. மீதமுள்ள விடுப்பு நாட்கள்</td><td>: {_esc(p.get('remainLeave'))}</td></tr>
    <tr><td>7. தற்போது தேவைப்படும் விடுப்பு நாட்கள்</td><td>: {dates_formatted}</td></tr>
    <tr><td>8. அனுமதி விடுப்பு நாட்கள்</td><td>: {_esc(p.get('permittedDays'))}</td></tr>
    <tr><td>9. விடுப்பிற்கான காரணம்</td><td>: {reason}</td></tr>
    <tr><td>10. விடுப்பின் போது முகவரி</td><td>: {address}</td></tr>
  </table>

  <table class="footer-row"><tr>
    <td style="text-align:left; width:50%;">
      <div>திண்டுக்கல்</div>
      <div>நாள்: {_esc(p.get('applyDate'))}</div>
    </td>
    <td style="text-align:right; width:50%;">
      <div>தங்கள் உண்மையுள்ள</div>
      <br/><br/>
      <div class="sign-box" style="margin-left:auto;">பணியாளர் கையொப்பம்</div>
    </td>
  </tr></table>
</div>
</body>
</html>"""


def build_elml_application_html(p):
    leave_title = "ஈட்டிய விடுப்பு விண்ணப்பம்" if p.get("leaveType") == "EL" else "மருத்துவ விடுப்பு விண்ணப்பம்"
    med_cert = "ஆம்" if p.get("medCert") == "ஆம்" else "இல்லை"
    gov_holiday = "ஆம்" + (f" ({p.get('govHolidayDate')})" if p.get("govHolidayDate") else "") \
        if p.get("govHoliday") == "ஆம்" else "இல்லை"
    tamil_rule = "ஆம்" if p.get("tamilRule") == "ஆம்" else "இல்லை"
    salary_str = f"ரூ. {p.get('salary')}" if p.get("salary") else ""
    address = _esc(p.get("address", "")).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="ta">
<head><meta charset="UTF-8">
<style>
{TAMIL_FONT_FACE_CSS}
  @page {{ size: A4 portrait; margin: 18mm 16mm; }}
  body {{ font-family: "NotoTamil","Arial Unicode MS",sans-serif;
         margin:0; padding:0; font-size:13px; color:#000; }}
  .wrap {{ width:100%; border:1.5px solid #000; padding:20px 24px; box-sizing:border-box; }}
  .ttl  {{ text-align:center; margin-bottom:16px; border-bottom:1px solid #000; padding-bottom:10px; }}
  .ttl .d1 {{ font-size:15px; font-weight:700; }}
  .ttl .d2 {{ font-size:14px; font-weight:700; margin-top:3px; }}
  .ttl .d3 {{ font-size:13px; font-weight:700; text-decoration:underline; margin-top:8px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
  td {{ padding:7px 6px; vertical-align:top; line-height:1.5; font-size:12px; }}
  td:first-child {{ width:50%; font-weight:600; }}
  .ft {{ width:100%; margin-top:40px; }}
  .ft td {{ padding:0; vertical-align:top; width:50%; }}
  .slr {{ border-top:1px solid #000; width:150px; text-align:center;
         padding-top:4px; font-size:11px; margin-top:30px; margin-left:auto; }}
</style></head>
<body><div class="wrap">
<div class="ttl">
  <div class="d1">தமிழ்நாடு அரசு பொது நூலகத்துறை</div>
  <div class="d2">திண்டுக்கல் மாவட்ட நூலக ஆணைக்குழு</div>
  <div class="d3">{leave_title}</div>
</div>
<table>
<tr><td>1. விண்ணப்பதார் பெயர்</td><td>: {_esc(p.get('empName'))}</td></tr>
<tr><td>2. பதவியின் பெயர்</td><td>: {_esc(p.get('designation'))}</td></tr>
<tr><td>3. பணிபுரியும் துறை/பிரிவு/அலுவலகம்</td><td>: {_esc(p.get('workplace'))}</td></tr>
<tr><td>4. ஊதியம்</td><td>: {salary_str}</td></tr>
<tr><td>5.(1) விண்ணப்பிக்கும் விடுப்பின் தன்மை</td><td>: {_esc(p.get('leaveNature'))}</td></tr>
<tr><td>&nbsp;&nbsp;&nbsp;(2) விடுப்பின் கால அளவு / விடுப்பில் செல்லும் நாள்</td><td>: {_esc(p.get('leaveDateRange'))}</td></tr>
<tr><td>6.(3) மருத்துவ சான்று இணைக்கப்பட்டுள்ளதா?</td><td>: {med_cert}</td></tr>
<tr><td>7. விடுப்பில் செல்லக் காரணம்</td><td>: {_esc(p.get('reason'))}</td></tr>
<tr><td>8. வார விடுமுறை/அரசு விடுமுறை இணைப்பு உத்தேசிக்கப்பட்டுள்ளதா?</td><td>: {gov_holiday}</td></tr>
<tr><td>9. இதற்கு முன் விடுப்பு விண்ணப்பித்திருந்தால் கால அளவு மற்றும் தன்மை</td><td>: {_esc(p.get('prevLeave')) or "—"}</td></tr>
<tr><td>10. விடுப்பின் போது முகவரி</td><td>: {address}</td></tr>
<tr><td>11. தமிழ்நாடு விடுப்பு விதிகளின் விதி 5 கீழ் விதிமுறை 4ன்படி உறுதி மொழி இணைக்கப்பட்டுள்ளதா?</td><td>: {tamil_rule}</td></tr>
</table>
<table class="ft"><tr>
  <td style="text-align:left;">
    <div>திண்டுக்கல்</div>
    <div>நாள்: {_esc(p.get('applyDate'))}</div>
  </td>
  <td style="text-align:right;">
    <div>தங்கள் உண்மையுள்ள</div>
    <br/><br/>
    <div class="slr">பணியாளர் கையொப்பம்</div>
  </td>
</tr></table>
</div></body></html>"""


def _html_to_pdf_bytes(html_content):
    """WeasyPrint மூலம் HTML-ஐ PDF bytes ஆக மாற்றுகிறது (தமிழ் Indic
    shaping சரியாக வருவதற்காக xhtml2pdf-க்கு பதிலாக இதை பயன்படுத்துகிறோம்)."""
    try:
        out = BytesIO()
        _WeasyHTML(string=html_content, base_url=_FONTS_DIR).write_pdf(out)
        return out.getvalue()
    except Exception as e:
        raise RuntimeError(f"PDF உருவாக்கத்தில் பிழை: {e}")


def send_leave_application_email(params):
    """PDF-ஐ generate பண்ணி, memory-ல் cache பண்ணி (fallback link-க்காக),
    மற்றும் பணியாளரின் email-க்கு (params['email']) Gmail SMTP மூலம்
    PDF attachment-ஆ அனுப்புகிறது."""
    try:
        leave_type_label = "தற்செயல் விடுப்பு விண்ணப்பம்" if params.get("leaveType") == "CL" \
            else "மத/வரையறுக்கப்பட்ட விடுப்பு விண்ணப்பம்"
        html_content = build_application_html(params, leave_type_label)
        pdf_bytes = _html_to_pdf_bytes(html_content)

        token = _store_pdf(pdf_bytes)
        share_url = f"/leave/pdf/{token}"

        emp_name = params.get("empName", "")
        emp_id = params.get("empId", "")
        leave_type = params.get("leaveType", "")
        apply_date = str(params.get("applyDate", "")).replace("/", "-")
        pdf_filename = f"{emp_id}_{leave_type}_{apply_date}.pdf"

        to_email = params.get("email", "")
        drive_url, mail_sent, mail_error = _upload_and_share_pdf(
            pdf_bytes, pdf_filename, to_email
        )

        return {
            "success": True,
            "shareUrl": share_url,
            "driveUrl": drive_url,
            "emailSent": mail_sent,
            "emailError": mail_error,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_elml_application_email(params):
    try:
        html_content = build_elml_application_html(params)
        pdf_bytes = _html_to_pdf_bytes(html_content)

        token = _store_pdf(pdf_bytes)
        share_url = f"/leave/pdf/{token}"

        emp_name = params.get("empName", "")
        emp_id = params.get("empId", "")
        leave_type = params.get("leaveType", "")
        apply_date = str(params.get("applyDate", "")).replace("/", "-")
        pdf_filename = f"{emp_id}_{leave_type}_{apply_date}.pdf"

        to_email = params.get("email", "")
        drive_url, mail_sent, mail_error = _upload_and_share_pdf(
            pdf_bytes, pdf_filename, to_email
        )

        return {
            "success": True,
            "shareUrl": share_url,
            "driveUrl": drive_url,
            "emailSent": mail_sent,
            "emailError": mail_error,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
