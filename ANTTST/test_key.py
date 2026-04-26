import httpx
import json

MODEL    = "gpt-4o-mini"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
MESSAGE  = "Reply with exactly: HELLO"
MAX_TOKENS = 20

print("OpenAI API Key Tester")
print("-" * 40)

api_key = input("Enter your OpenAI API key: ").strip()

print("-" * 40)

prefix = api_key[:10] if len(api_key) >= 10 else api_key
suffix = api_key[-6:]  if len(api_key) >=  6 else api_key
print(f"Key entered : {prefix}...{suffix}")
print()

payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": MESSAGE}],
    "max_tokens": MAX_TOKENS,
}

print("Request details:")
print(f"  model      : {MODEL}")
print(f"  message    : {MESSAGE}")
print(f"  max_tokens : {MAX_TOKENS}")
print(f"  key        : {prefix}...{suffix}")
print(f"  endpoint   : {ENDPOINT}")
print()

try:
    response = httpx.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    print("Raw response:")
    print(f"  status : {response.status_code}")
    print(f"  body   : {response.text}")
    print()

    if response.status_code == 200:
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        print(f"✓ SUCCESS — key works. Response: {text}")
    else:
        data = response.json()
        err  = data.get("error", {})
        code = err.get("code", response.status_code)
        msg  = err.get("message", response.text)
        print(f"✗ FAILED — HTTP {response.status_code} | {code}: {msg}")

except httpx.ConnectError as e:
    print(f"✗ FAILED — connection error: {e}")
except Exception as e:
    print(f"✗ FAILED — {type(e).__name__}: {e}")
