import requests
import time
from bs4 import BeautifulSoup

url = "https://rapidsite.app/register"
session = requests.Session()

# Get the page and cookies
response = session.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
csrf_input = soup.find('input', {'name': 'csrf_token'})
csrf_token = csrf_input['value'] if csrf_input else ''

data = {
    "csrf_token": csrf_token,
    "company_name": "Test Prod Three",
    "name": "Test User",
    "email": "testprod3@rapidsite.app",
    "password": "password123",
    "confirm_password": "password123"
}

headers = {
    "Referer": "https://rapidsite.app/register"
}

print("Submitting to prod...")
start = time.time()
post_response = session.post(url, data=data, headers=headers)
print(f"Status Code: {post_response.status_code}")
if post_response.status_code == 400:
    print(post_response.text)
elif post_response.status_code == 502:
    print("502 BAD GATEWAY")
end = time.time()
print(f"Took: {end - start:.2f} seconds")
