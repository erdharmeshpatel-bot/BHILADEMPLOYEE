import os
from datetime import date, datetime, timedelta
from collections import Counter, defaultdict

from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables are required.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLES = {
    "employees": "employees",
    "departments": "departments",
    "positions": "positions",
    "attendance": "attendance",
    "leaves": "leaves",
    "payroll": "payroll",
}

ALLOWED_FIELDS = {
    "departments": {"name", "description"},
    "positions": {"title", "department_id", "description"},
    "employees": {
        "name",
        "email",
        "phone",
        "profile_pic",
        "salary",
        "status",
        "hire_date",
        "department_id",
        "position_id",
    },
    "attendance": {"employee_id", "date", "check_in", "check_out", "status"},
    "leaves": {"employee_id", "type", "start_date", "end_date", "status", "reason"},
    "payroll": {
        "employee_id",
        "month",
        "basic_salary",
        "allowances",
        "deductions",
        "net_salary",
        "status",
    },
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "ITIBhilad HR"}), 200


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    password = payload.get("password")

    if email == "admin@ITIBhilad.hr" and password == "password123":
        return jsonify(
            {
                "token": "mock-itibhilad-hr-token",
                "user": {"email": email, "name": "ITIBhilad Admin"},
            }
        )

    return jsonify({"error": "Invalid email or password"}), 401


def clean_payload(resource: str, payload: dict) -> dict:
    allowed = ALLOWED_FIELDS[resource]
    return {k: v for k, v in payload.items() if k in allowed}


def table_response(result):
    return jsonify(result.data if result.data is not None else [])


@app.route("/api/<resource>", methods=["GET"])
def list_records(resource):
    if resource not in TABLES:
        return jsonify({"error": "Unknown resource"}), 404

    try:
        result = (
            supabase.table(TABLES[resource])
            .select("*")
            .order("id", desc=False)
            .execute()
        )
        return table_response(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/<resource>/<int:record_id>", methods=["GET"])
def get_record(resource, record_id):
    if resource not in TABLES:
        return jsonify({"error": "Unknown resource"}), 404

    try:
        result = (
            supabase.table(TABLES[resource])
            .select("*")
            .eq("id", record_id)
            .single()
            .execute()
        )
        return jsonify(result.data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/<resource>", methods=["POST"])
def create_record(resource):
    if resource not in TABLES:
        return jsonify({"error": "Unknown resource"}), 404

    payload = request.get_json(silent=True) or {}
    data = clean_payload(resource, payload)

    if not data:
        return jsonify({"error": "No valid fields supplied"}), 400

    try:
        result = supabase.table(TABLES[resource]).insert(data).execute()
        return jsonify(result.data[0] if result.data else data), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/<resource>/<int:record_id>", methods=["PUT"])
def update_record(resource, record_id):
    if resource not in TABLES:
        return jsonify({"error": "Unknown resource"}), 404

    payload = request.get_json(silent=True) or {}
    data = clean_payload(resource, payload)

    if not data:
        return jsonify({"error": "No valid fields supplied"}), 400

    try:
        result = (
            supabase.table(TABLES[resource])
            .update(data)
            .eq("id", record_id)
            .execute()
        )
        return jsonify(result.data[0] if result.data else {"id": record_id, **data})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/<resource>/<int:record_id>", methods=["DELETE"])
def delete_record(resource, record_id):
    if resource not in TABLES:
        return jsonify({"error": "Unknown resource"}), 404

    try:
        result = supabase.table(TABLES[resource]).delete().eq("id", record_id).execute()
        return jsonify({"deleted": True, "id": record_id, "data": result.data})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def fetch_all(table_name: str):
    return supabase.table(table_name).select("*").execute().data or []


@app.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    try:
        employees = fetch_all("employees")
        departments = fetch_all("departments")
        positions = fetch_all("positions")
        attendance = fetch_all("attendance")
        leaves = fetch_all("leaves")

        today_iso = date.today().isoformat()

        dept_by_id = {d["id"]: d for d in departments}
        pos_by_id = {p["id"]: p for p in positions}

        present_today = sum(
            1
            for row in attendance
            if row.get("date") == today_iso and row.get("status") == "Present"
        )

        pending_leaves = sum(1 for row in leaves if row.get("status") == "Pending")

        hiring_counter = defaultdict(int)
        for emp in employees:
            hire_date = emp.get("hire_date")
            if hire_date:
                try:
                    dt = datetime.fromisoformat(hire_date[:10])
                    key = dt.strftime("%b %Y")
                    hiring_counter[key] += 1
                except ValueError:
                    continue

        hiring_items = sorted(
            hiring_counter.items(),
            key=lambda item: datetime.strptime(item[0], "%b %Y"),
        )[-8:]

        dept_counter = Counter()
        for emp in employees:
            dept_name = dept_by_id.get(emp.get("department_id"), {}).get(
                "name", "Unassigned"
            )
            dept_counter[dept_name] += 1

        last_10_days = [date.today() - timedelta(days=i) for i in range(9, -1, -1)]
        attendance_labels = [d.strftime("%d %b") for d in last_10_days]
        attendance_values = []
        for d in last_10_days:
            attendance_values.append(
                sum(
                    1
                    for row in attendance
                    if row.get("date") == d.isoformat()
                    and row.get("status") in {"Present", "Late", "Half Day"}
                )
            )

        status_counter = Counter(emp.get("status") or "Active" for emp in employees)

        employees_by_position = []
        for emp in employees:
            employees_by_position.append(
                {
                    "id": emp.get("id"),
                    "name": emp.get("name"),
                    "profile_pic": emp.get("profile_pic"),
                    "department": dept_by_id.get(emp.get("department_id"), {}).get(
                        "name", "No department"
                    ),
                    "position": pos_by_id.get(emp.get("position_id"), {}).get(
                        "title", "Unassigned"
                    ),
                }
            )

        return jsonify(
            {
                "cards": {
                    "employees": len(employees),
                    "departments": len(departments),
                    "positions": len(positions),
                    "present_today": present_today,
                    "pending_leaves": pending_leaves,
                },
                "hiring_trend": {
                    "labels": [item[0] for item in hiring_items],
                    "data": [item[1] for item in hiring_items],
                },
                "department_mix": {
                    "labels": list(dept_counter.keys()),
                    "data": list(dept_counter.values()),
                },
                "attendance_trend": {
                    "labels": attendance_labels,
                    "data": attendance_values,
                },
                "status_breakdown": {
                    "labels": list(status_counter.keys()),
                    "data": list(status_counter.values()),
                },
                "employees_by_position": employees_by_position,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
