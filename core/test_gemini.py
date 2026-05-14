import requests

key = "AIzaSyBioWlRi2fZbAzEYi1py5_TC5XCO0QifRI"
url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
payload = {"model": "gemini-2.0-flash", "max_tokens": 50, "messages": [{"role": "user", "content": "Say hello."}]}

resp = requests.post(url, headers=headers, json=payload, timeout=30)
print("STATUS:", resp.status_code)
print("BODY:", resp.text[:2000])
