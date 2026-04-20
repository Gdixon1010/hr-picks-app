import os
from pathlib import Path
import json
from datetime import datetime

# =========================
# ✅ USE PERSISTENT DISK
# =========================
BASE_DIR = Path(os.getenv("HR_APP_DATA_DIR", "output"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# FIND LATEST V40 FILE
# =========================
def get_latest_v40_file():
    files = list(BASE_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"))
    if not files:
        raise FileNotFoundError("No v40 appdata JSON was created.")
    return max(files, key=lambda x: x.stat().st_mtime)

# =========================
# LOAD V40 DATA
# =========================
def load_v40_data():
    latest_file = get_latest_v40_file()
    with open(latest_file, "r") as f:
        return json.load(f)

# =========================
# SAVE V41 OUTPUT
# =========================
def save_v41_data(data):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = BASE_DIR / f"HR_Hit_Drought_v41_appdata-{timestamp}.json"

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

    return file_path

# =========================
# MAIN PROCESS
# =========================
def build_v41():
    v40_data = load_v40_data()

    # 🔥 You can enhance this later — for now we pass through
    v41_data = v40_data

    output_file = save_v41_data(v41_data)

    return {
        "status": "success",
        "message": "v41 built successfully",
        "output_file": str(output_file)
    }

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    result = build_v41()
    print(result)
