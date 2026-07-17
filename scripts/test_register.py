import requests
from bs4 import BeautifulSoup

session = requests.Session()
url = "http://127.0.0.1:5000/register"

# Get CSRF token
response = session.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
csrf_token = soup.find('input', {'name': 'csrf_token'})['value']

# Post data
data = {
    "csrf_token": csrf_token,
    "company_name": "Test Company Crash",
    "name": "Test User",
    "email": "testcrash@rapidsite.app",
    "password": "password123",
    "confirm_password": "password123"
}

print("Submitting registration...")
post_response = session.post(url, data=data)
print(f"Status Code: {post_response.status_code}")
if post_response.status_code == 502:
    print("GOT 502 BAD GATEWAY!")
elif post_response.status_code == 500:
    print("GOT 500 INTERNAL SERVER ERROR!")
else:
    print("SUCCESS or Redirection")
