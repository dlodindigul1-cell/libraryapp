"""
app.py
------------------------------------------------------------
நூலகர் விடுப்பு மேலாண்மை — Flask backend.

GAS-ன் doGet()/doPost()-க்கு பதிலாக:
  GET  /leave              -> index HTML page (Index.html-க்கு பதில்)
  POST /leave/api/<fn>     -> google.script.run.fn(args) -க்கு பதில்
                               (gas-shim.js இதை call செய்யும்)

இது library portal-ல் ("விடுப்பு பதிவு" card) இதே Render
project-ல் இணைக்கப்படும் ஒரு blueprint-ஆக design செய்யப்பட்டது —
தனியாகவும் இயங்கும் (python app.py).
------------------------------------------------------------
"""

from flask import Flask, render_template, request, jsonify, redirect

import sheets_service as svc
import pdf_service as pdf
import pettycash_service as pc

app = Flask(__name__)


@app.route("/")
def home():
    return redirect("/leave")


# ------------------------------------------------------------
# function name (frontend அழைக்கும் பெயர்) -> Python callable
# ------------------------------------------------------------
DISPATCH = {
    "getAllEmployees":          lambda args: svc.get_all_employees(),
    "lookupEmployeeByQuery":    lambda args: svc.lookup_employee_by_query(*args),
    "getUsedLeave":             lambda args: svc.get_used_leave(*args),
    "checkPermissionLimit":     lambda args: svc.check_permission_limit(*args),
    "addLeaveRows":             lambda args: svc.add_leave_rows(*args),
    "getTodayLeaveStaff":       lambda args: svc.get_today_leave_staff(),
    "getEmployeeLeaveHistory":  lambda args: svc.get_employee_leave_history(*args),
    "checkDuplicateLeave":      lambda args: svc.check_duplicate_leave(*args),
    "getRHDates":                lambda args: svc.get_rh_dates(),
    "checkRHDate":               lambda args: svc.check_rh_date(*args),
    "sendLeaveApplicationEmail": lambda args: pdf.send_leave_application_email(*args),
    "sendELMLApplicationEmail":  lambda args: pdf.send_elml_application_email(*args),
}

# ------------------------------------------------------------
# சில்லறை செலவினம் (Petty Cash) — Phase 1
# ------------------------------------------------------------
PETTYCASH_DISPATCH = {
    "getLibraryTypes":              lambda args: pc.get_library_types(),
    "getLibrariesByType":           lambda args: pc.get_libraries_by_type(*args),
    "getEmailsForLibrary":          lambda args: pc.get_emails_for_library(*args),
    "getExistingContingentData":    lambda args: pc.get_existing_contingent_data(*args),
    "submitOrUpdateContingent":     lambda args: pc.submit_or_update_contingent(*args),
    "getAvailableMonthsForLibrary": lambda args: pc.get_available_months_for_library(*args),
    "shareApprovedExpenseMailByFileId":  lambda args: pc.share_approved_expense_mail_by_file_id(*args),
    # --- நூலக வரவினங்கள் (Receipts) ---
    "validatePaymentWithBank":                    lambda args: pc.validate_payment_with_bank(*args),
    "saveOrUpdateReceipt":                        lambda args: pc.save_or_update_receipt(*args),
    "getAvailableMonthsForLibraryAcknowledgement": lambda args: pc.get_available_months_for_library_acknowledgement(*args),
    "shareReceiptAcknowledgementByFileId":         lambda args: pc.share_receipt_acknowledgement_by_file_id(*args),
}


@app.route("/leave")
@app.route("/leave/")
def leave_index():
    return render_template("leave_index.html")


@app.route("/leave/api/<fn_name>", methods=["POST"])
def leave_api(fn_name):
    handler = DISPATCH.get(fn_name)
    if handler is None:
        return jsonify({"__gasError__": f"Unknown function: {fn_name}"}), 200

    body = request.get_json(silent=True) or {}
    args = body.get("args", [])

    try:
        result = handler(args)
        return jsonify(result)
    except Exception as e:
        return jsonify({"__gasError__": str(e)}), 200


# ------------------------------------------------------------
# சில்லறை செலவினம் routes
# ------------------------------------------------------------
@app.route("/pettycash")
@app.route("/pettycash/")
def pettycash_index():
    is_admin = "admin" in request.args
    return render_template("pettycash_index.html", is_admin=is_admin)


@app.route("/pettycash/api/<fn_name>", methods=["POST"])
def pettycash_api(fn_name):
    handler = PETTYCASH_DISPATCH.get(fn_name)
    if handler is None:
        return jsonify({"__gasError__": f"Unknown function: {fn_name} (Phase 1-ல் இன்னும் சேர்க்கப்படவில்லை)"}), 200

    body = request.get_json(silent=True) or {}
    args = body.get("args", [])

    try:
        result = handler(args)
        return jsonify(result)
    except Exception as e:
        return jsonify({"__gasError__": str(e)}), 200


# ------------------------------------------------------------
# Health check (Render-க்கு உபயோகம்)
# ------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=True)
