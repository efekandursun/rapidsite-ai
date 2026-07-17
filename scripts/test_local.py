import requests
import time
from bs4 import BeautifulSoup

url = "http://127.0.0.1:5006/register"
session = requests.Session()

# Get the page and cookies
response = session.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
csrf_input = soup.find('input', {'name': 'csrf_token'})
csrf_token = csrf_input['value'] if csrf_input else ''

data = {
    "csrf_token": csrf_token,
    "company_name": "Test Local",
    "name": "Test User",
    "email": "testlocal@rapidsite.app",
    "password": "password123",
    "confirm_password": "password123"
}

headers = {
    "Referer": "http://127.0.0.1:5006/register"
}

print("Submitting to local...")
start = time.time()
try:
    post_response = session.post(url, data=data, headers=headers)
    print(f"Status Code: {post_response.status_code}")
    if post_response.status_code == 400:
        print(post_response.text)
    elif post_response.status_code == 502:
        print("502 BAD GATEWAY")
except Exception as e:
    print(f"Error: {e}")
end = time.time()
print(f"Took: {end - start:.2f} seconds")
