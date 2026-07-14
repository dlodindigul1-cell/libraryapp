"""
pdf_service.py
------------------------------------------------------------
GAS-ன் buildApplicationHTML() / buildELMLApplicationHTML() /
sendLeaveApplicationEmail() / sendELMLApplicationEmail()
functions-ஐ port செய்யப்பட்ட பதிப்பு.

வித்தியாசம்: Gmail-க்கு அனுப்பாமல், PDF-ஐ Google Drive-ல்
சேமித்து, share-link-ஐ response-ல் திருப்பி அனுப்புகிறோம்
(frontend-ல் "PDF திறக்கவும்" button ஏற்கனவே இதை காட்டும்).
------------------------------------------------------------
"""

from io import BytesIO
from xhtml2pdf import pisa

from drive_service import upload_pdf


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
  @page {{ size: A4; margin: 20mm 18mm; }}
  body {{ font-family: 'Noto Sans Tamil', 'Arial Unicode MS', sans-serif;
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
  @page {{ size: A4 portrait; margin: 18mm 16mm; }}
  body {{ font-family: "Noto Sans Tamil","Arial Unicode MS",sans-serif;
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
    out = BytesIO()
    result = pisa.CreatePDF(src=html_content, dest=out, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF உருவாக்கத்தில் பிழை")
    return out.getvalue()


def send_leave_application_email(params):
    """பெயர் பழையபடி வைத்திருக்கிறோம் (frontend அதே பெயரை அழைக்கிறது) —
    ஆனால் இப்போது மெயில் அனுப்பாது, PDF-ஐ Drive-ல் சேமித்து link திருப்பும்."""
    try:
        leave_type_label = "தற்செயல் விடுப்பு விண்ணப்பம்" if params.get("leaveType") == "CL" \
            else "மத/வரையறுக்கப்பட்ட விடுப்பு விண்ணப்பம்"
        html_content = build_application_html(params, leave_type_label)
        pdf_bytes = _html_to_pdf_bytes(html_content)

        apply_date = str(params.get("applyDate", "")).replace("/", "-")
        file_name = f"{params.get('empId')}_{params.get('leaveType')}_{apply_date}.pdf"

        share_url = upload_pdf(file_name, pdf_bytes)
        return {"success": True, "shareUrl": share_url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_elml_application_email(params):
    try:
        html_content = build_elml_application_html(params)
        pdf_bytes = _html_to_pdf_bytes(html_content)

        apply_date = str(params.get("applyDate", "")).replace("/", "-")
        file_name = f"{params.get('empId')}_{params.get('leaveType')}_{apply_date}.pdf"

        share_url = upload_pdf(file_name, pdf_bytes)
        return {"success": True, "shareUrl": share_url}
    except Exception as e:
        return {"success": False, "error": str(e)}
