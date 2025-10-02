#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone

# Sample payload based on the new structure
payload = {
  "app_version": "treko-desktop-iced/0.1",
  "apps": {
    "active_by_app_sec": {
      "Chrome": 3,
      "Visual Studio Code": 1
    },
    "session_count": 1,
    "session_duration_sec": 4
  },
  "by_task": [
    {
      "effective_sec": 4,
      "overtime_sec": 0,
      "recorded_sec": 4,
      "remaining_task_time_sec": 43192,
      "task_id": "4dde3ad9-d876-4569-8d4c-4ad82b30cd53",
      "total_task_time_sec": 43200,
      "total_worked_time_sec": 8
    }
  ],
  "chunk_count": 1,
  "chunk_id": "f45e4df7-8995-4fda-b5ea-30d2edf5865e",
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "is_partial": True,
  "media": {
    "headshots": [],
    "screenshots": []
  },
  "project_id": "9a92974f-8821-4592-ac0d-c536bdc33b17",
  "stats": {
    "active_sec": 4,
    "effective_sec": 4,
    "idle_sec": 0,
    "overtime_sec": 0,
    "recorded_sec": 4
  },
  "user_id": "53805750-5cb4-46b0-81c7-67d30ed97458",  # Valid employee ID from the database
  "window": {
    "end": datetime.now(timezone.utc).isoformat(),
    "start": datetime.now(timezone.utc).isoformat()
  }
}

# URL of your API endpoint
url = "http://localhost:8000/api/payload/"

# Send the request
headers = {'Content-Type': 'application/json'}
response = requests.post(url, json=payload, headers=headers)

# Print the response
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
