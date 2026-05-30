import os
import urllib.request
import json

api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    exit(1)

req = urllib.request.Request(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}',
    data=b'{"contents":[{"parts":[{"text":"hi"}]}]}',
    headers={'Content-Type':'application/json'}
)
try:
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    body = getattr(e, 'read', lambda: lambda: b'')()().decode()
    print("API Error:", body if body else str(e))
