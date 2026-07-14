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

from flask import Flask, render_template, request, jsonify

import sheets_service as svc
import pdf_service as pdf

app = Flask(__name__)

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
# Health check (Render-க்கு உபயோகம்)
# ------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=True)
