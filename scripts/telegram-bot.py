import os
import requests
import json
import time

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

offset = None

print("Listening for updates...\n")

while True:
    params = {
        "timeout": 30,
    }

    if offset:
        params["offset"] = offset

    try:
        r = requests.get(URL, params=params, timeout=35)
        data = r.json()

        for update in data["result"]:
            offset = update["update_id"] + 1

            print("=" * 80)
            print(json.dumps(update, indent=4))
            print("=" * 80)

    except Exception as e:
        print(e)

    time.sleep(1)
