import os
from dotenv import load_dotenv
from redis import Redis
from rq import Queue
load_dotenv()
redis_url = os.getenv('REDIS_URL')
if not redis_url:
    print("No REDIS_URL found in .env")
    exit(1)
print(f"Connecting to {redis_url.split('@')[-1]}...")
r = Redis.from_url(redis_url)
q = Queue('rapidsite-tasks', connection=r)
print(f"Jobs in queue: {len(q)}")
failed_q = Queue('failed', connection=r)
print(f"Failed jobs in queue: {len(failed_q)}")
