import httpx
import sys

def check():
    url = "http://localhost:8000/api/openapi.json"
    print(f"Checking {url}...")
    try:
        response = httpx.get(url, timeout=5.0)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("Response is 200 OK. Content starts with:")
            print(response.text[:100])
        else:
            print(f"Unexpected status code: {response.status_code}")
            sys.exit(1)
    except httpx.ConnectError:
        print("Error: Could not connect to localhost:8000. Is the server running?")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check()
