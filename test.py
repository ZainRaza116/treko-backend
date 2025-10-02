import os

def list_applications(paths=["/Applications", os.path.expanduser("~/Applications")]):
    apps = []
    for path in paths:
        if os.path.exists(path):
            for item in os.listdir(path):
                if item.endswith(".app"):
                    apps.append(item.replace(".app", ""))
    return sorted(set(apps))

apps = list_applications()
print(apps[:20])  # show first 20 apps
print(f"Total apps found: {len(apps)}")

import os
import json

# Step 1: Get installed apps
def list_applications(paths=["/Applications", os.path.expanduser("~/Applications")]):
    apps = []
    for path in paths:
        if os.path.exists(path):
            for item in os.listdir(path):
                if item.endswith(".app"):
                    apps.append(item.replace(".app", ""))
    return sorted(set(apps))

apps = list_applications()

# Step 2: Define category mapping
category_map = {
    "Battery": "Utilities",
    "Battery Health 2": "Utilities",
    "Better Battery 2": "Utilities",
    "Bruno": "Development",
    "Cursor": "Development",
    "DB Browser for SQLite": "Development",
    "DBeaver": "Development",
    "Docker": "Development",
    "Google Chrome": "Browser",
    "Hubstaff": "Productivity",
    "PyCharm": "Development",
    "Safari": "Browser",
    "Slack": "Communication",
    "iTerm": "Development",
    "zoom.us": "Communication"
}

# Step 3: Assign categories (fallback to Uncategorized)
final_map = {app: category_map.get(app, "Uncategorized") for app in apps}

# Step 4: Save result
with open("app_category_map.json", "w") as f:
    json.dump(final_map, f, indent=4)

print(json.dumps(final_map, indent=4))
