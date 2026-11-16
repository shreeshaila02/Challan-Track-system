"""
ChallanTrack – Vehicle Challan Management System
Main Entry Point – Direct Web Application Launcher

When executed directly (`python challan_track.py` or clicking RUN in VS Code):
- Starts the Flask backend server automatically on http://127.0.0.1:5000
- Opens Google Chrome automatically to load the ChallanTrack web portal
- Operates strictly on actual registered data in challans.json
- Preserves all registered records and fine calculation logic
"""

import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# Base directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
FILE_NAME = os.path.join(BASE_DIR, "challans.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)

# Standard Traffic Violation Catalog & Fines
VIOLATIONS = {
    "1": ("No Helmet", 500),
    "2": ("No Seat Belt", 500),
    "3": ("Using Mobile While Driving", 1000),
    "4": ("Over Speeding", 1000),
    "5": ("Signal Violation", 500),
    "6": ("No Parking", 300),
    "7": ("Other Violation", 0)
}


# ============================================================================
# DATA STORAGE HELPERS (Strictly reads/writes actual registered records)
# ============================================================================

def load_challans():
    """Loads actual registered records from challans.json. Returns [] if empty."""
    if os.path.exists(FILE_NAME):
        try:
            if os.path.getsize(FILE_NAME) == 0:
                return []
            with open(FILE_NAME, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {FILE_NAME}: {e}")
            return []
    return []


def save_challans(challans):
    """Saves actual registered records to challans.json file."""
    try:
        with open(FILE_NAME, "w", encoding="utf-8") as f:
            json.dump(challans, f, indent=4)
        return True
    except OSError as e:
        print(f"Error saving {FILE_NAME}: {e}")
        return False


# ============================================================================
# FLASK WEB ROUTES & APIS
# ============================================================================

@app.route("/")
def index():
    """Renders the main ChallanTrack single-page web portal."""
    return render_template("index.html")


@app.route("/api/violations", methods=["GET"])
def get_violations():
    """Returns the violation catalog with standard fines."""
    items = []
    for key, (name, fine) in VIOLATIONS.items():
        items.append({
            "key": key,
            "name": name,
            "fine": fine
        })
    return jsonify(items)


@app.route("/api/challans", methods=["GET"])
def get_all_challans():
    """Returns all actual registered challan records."""
    challans = load_challans()
    # Return reversed so newest registered are at the top
    return jsonify(list(reversed(challans)))


@app.route("/api/challans/search", methods=["GET"])
def search_challans():
    """
    Searches for challans associated with a vehicle registration number.
    Returns calculated summary metrics and full history for actual registered records.
    If no records exist, returns found: False with 'No Challan Records Found'.
    """
    vehicle_query = request.args.get("vehicle", "").strip().upper()
    if not vehicle_query:
        return jsonify({"found": False, "error": "Vehicle number required"}), 400

    challans = load_challans()
    normalized_query = vehicle_query.replace(" ", "")

    # Match exact or spaces-stripped registration against actual stored records
    matching = [
        c for c in challans
        if c.get("vehicle", "").strip().upper() == vehicle_query
        or c.get("vehicle", "").replace(" ", "").upper() == normalized_query
    ]

    if not matching:
        return jsonify({
            "found": False,
            "vehicle": vehicle_query,
            "message": "No Challan Records Found"
        })

    # Calculate summary values strictly from actual matching records
    total_count = len(matching)
    paid_count = sum(1 for c in matching if c.get("status") == "Paid")
    pending_count = sum(1 for c in matching if c.get("status") == "Pending")

    total_fine = sum(float(c.get("fine", 0)) for c in matching)
    total_paid = sum(float(c.get("fine", 0)) for c in matching if c.get("status") == "Paid")
    total_pending = sum(float(c.get("fine", 0)) for c in matching if c.get("status") == "Pending")

    owner_name = matching[-1].get("owner", "N/A")
    canonical_vehicle = matching[-1].get("vehicle", vehicle_query)

    return jsonify({
        "found": True,
        "summary": {
            "vehicle": canonical_vehicle,
            "owner": owner_name,
            "total_challans": total_count,
            "paid_challans": paid_count,
            "pending_challans": pending_count,
            "total_fine": total_fine,
            "total_paid": total_paid,
            "total_pending": total_pending
        },
        "records": list(reversed(matching))
    })


@app.route("/api/challans", methods=["POST"])
def register_challan():
    """
    Registers a new challan from actual user input:
    - Saves entered vehicle number
    - Saves entered owner name
    - Saves selected violation and calculated fine
    - Generates unique Challan ID
    - Generates current date and time
    - Sets initial status 'Pending'
    - Saves record in challans.json
    """
    data = request.get_json() or {}
    vehicle = data.get("vehicle", "").strip().upper()
    owner = data.get("owner", "").strip()
    violation = data.get("violation", "").strip()
    fine = data.get("fine")

    if not vehicle or not owner or not violation or fine is None:
        return jsonify({"success": False, "error": "All fields are required"}), 400

    try:
        fine = float(fine)
        if fine <= 0:
            return jsonify({"success": False, "error": "Fine must be greater than zero"}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid fine amount"}), 400

    challans = load_challans()

    # Generate next unique Challan ID based on actual registered records
    challan_id = max((int(c.get("id", 1000)) for c in challans), default=1000) + 1

    new_challan = {
        "id": challan_id,
        "vehicle": vehicle,
        "owner": owner,
        "violation": violation,
        "fine": fine,
        "date": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "status": "Pending"
    }

    challans.append(new_challan)

    if save_challans(challans):
        return jsonify({"success": True, "challan": new_challan}), 201
    else:
        return jsonify({"success": False, "error": "Failed to save record to storage"}), 500


@app.route("/api/challans/<int:challan_id>/pay", methods=["POST"])
def pay_challan(challan_id):
    """Marks an actual pending challan as Paid and persists changes to challans.json."""
    challans = load_challans()
    for c in challans:
        if int(c.get("id")) == challan_id:
            if c.get("status") == "Paid":
                return jsonify({"success": False, "error": f"Challan #{challan_id} is already paid"}), 400

            c["status"] = "Paid"
            if save_challans(challans):
                return jsonify({"success": True, "challan": c})
            else:
                c["status"] = "Pending"
                return jsonify({"success": False, "error": "Failed to update record in storage"}), 500

    return jsonify({"success": False, "error": f"Challan #{challan_id} not found"}), 404


@app.route("/api/report", methods=["GET"])
def get_fine_report():
    """
    Calculates live fine collection statistics EXCLUSIVELY from actual registered records.
    If no records exist, returns 0 for all counts and amounts.
    """
    challans = load_challans()

    total_challans = len(challans)
    total_fine = sum(float(c.get("fine", 0)) for c in challans)

    collected_fine = sum(
        float(c.get("fine", 0)) for c in challans
        if c.get("status") == "Paid"
    )

    outstanding_fine = sum(
        float(c.get("fine", 0)) for c in challans
        if c.get("status") == "Pending"
    )

    paid_count = sum(1 for c in challans if c.get("status") == "Paid")
    pending_count = total_challans - paid_count

    collection_rate = (collected_fine / total_fine * 100) if total_fine > 0 else 0.0

    return jsonify({
        "total_challans": total_challans,
        "total_fine": total_fine,
        "collected_fine": collected_fine,
        "outstanding_fine": outstanding_fine,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "collection_rate": round(collection_rate, 1)
    })


# ============================================================================
# AUTOMATIC GOOGLE CHROME LAUNCHER
# ============================================================================

def auto_launch_chrome(url="http://127.0.0.1:5000"):
    """
    Waits briefly for Flask to bind, then automatically opens Google Chrome
    directly to the ChallanTrack portal.
    """
    time.sleep(1.2)  # Wait for Flask web server to be ready
    
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    ]

    for path in chrome_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path, url])
                return
            except Exception:
                pass

    # Fallback to default browser if chrome.exe direct path fails
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not open browser automatically: {e}")


# ============================================================================
# MAIN ENTRY POINT (Direct Launch)
# ============================================================================

def main():
    """Starts the Flask backend server and automatically opens Google Chrome."""
    url = "http://127.0.0.1:5000"

    print("\n" + "=" * 68)
    print("         CHALLAN TRACK – VEHICLE CHALLAN MANAGEMENT SYSTEM")
    print("=" * 68)
    print(f"  [✓] Flask backend server starting on {url}")
    print("  [✓] Opening Google Chrome automatically...")
    print("  [✓] Application running. Press Ctrl+C in this terminal to exit.")
    print("=" * 68 + "\n")

    # Launch Chrome in a separate background daemon thread
    launcher_thread = threading.Thread(target=auto_launch_chrome, args=(url,), daemon=True)
    launcher_thread.start()

    # Start Flask Web Server directly (no terminal menus)
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
