import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

# Pre-load modules to prevent forks from importing everything
from core.database import Database
from core.whatsapp_handler import handle_message_async

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('BackgroundWorker')

def run_worker():
    """Start the RQ worker to process background jobs from Redis."""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    try:
        from redis import Redis
        from rq import Worker, Connection
        
        redis_conn = Redis.from_url(redis_url)
        # Test connection
        redis_conn.ping()
        
        logger.info(f"👷 RQ Worker started. Connected to Redis at {redis_url}")
        
        with Connection(redis_conn):
            worker = Worker(['rapidsite-tasks'])
            worker.work()
            
    except Exception as e:
        logger.error(f"❌ Could not connect to Redis: {e}")
        logger.error("Please ensure Redis is running or use threading fallback in development.")
        # If this is local dev without redis, just exit cleanly and let the fallback handle it
        if os.getenv("FLASK_ENV") != "production":
            logger.info("Local environment detected. Fallback threads will handle jobs.")
            sys.exit(0)
        sys.exit(1)

if __name__ == "__main__":
    # Ensure Sentry is initialized if DSN is present
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    if SENTRY_DSN and SENTRY_DSN != "your_sentry_dsn_here":
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
    
    run_worker()
