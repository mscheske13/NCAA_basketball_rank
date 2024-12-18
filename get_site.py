from io import StringIO
import io
import requests
import time
import sys

SLEEP_DELAY : int = 3

def get_site(url : str) -> io.StringIO:
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.100 Safari/537.36",
            "Referer": "https://example.com",
            "Accept-Language": "en-US,en;q=0.9"
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.5672.63 Safari/537.36",
            "Referer": "https://example.com",
            "Accept-Language": "en-US,en;q=0.8,en;q=0.7"
        },
        {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.5563.64 Safari/537.36",
            "Referer": "https://example.com",
            "Accept-Language": "en-US,en;q=0.9"
        }
    ]

    max_retries = 5
    for attempt in range(max_retries):
        # Use a different header for each attempt
        headers = headers_list[attempt % len(headers_list)]
        response = requests.get(url, headers=headers)

            # Check if the response is successful (status code 200)
        if response.status_code == 200:
            return StringIO(response.text)
        else:
            time.sleep(SLEEP_DELAY)
    else:
        print("Failed after maximum retries.")
        sys.exit(1)


