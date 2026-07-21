from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'test'
CSRFProtect(app)

class DummyRow:
    def __init__(self, d): self.d = d
    def __getitem__(self, k): return self.d[k]
    def get(self, k, default=None): return self.d.get(k, default)
    def keys(self): return self.d.keys()

d1 = DummyRow({'id':1, 'status':'pending', 'log_type':'notes', 'raw_transcript':'test', 'created_at':None, 'parsed_data':'{}'})

with app.app_context():
    with app.test_request_context('/dashboard'):
        try:
            res = render_template('dashboard.html', pending_reports=[d1], reports_by_type={}, total_reports=1, stats={})
            print("SUCCESS")
        except Exception as e:
            import traceback
            traceback.print_exc()
