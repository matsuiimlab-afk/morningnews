import os
import requests

TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
USER_ID = os.environ["LINE_USER_ID"]

url = "https://api.line.me/v2/bot/message/push"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "to": USER_ID,
    "messages": [
        {
            "type": "text",
            "text": "朝刊システム テスト成功 🚀"
        }
    ]
}

r = requests.post(url, headers=headers, json=payload)

print(r.status_code)
print(r.text)