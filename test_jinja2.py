from app import app
from flask import session

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['company_id'] = 1
    
    res = client.get('/dashboard')
    print("STATUS:", res.status_code)
    if res.status_code == 500:
        print("ERROR:", res.data)
