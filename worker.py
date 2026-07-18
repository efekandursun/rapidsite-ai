import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

from core.database import Database
from core.whatsapp_handler import handle_message_async

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('BackgroundWorker')

def run_worker():
    """Continuously poll and process webhook jobs sequentially to avoid memory spikes."""
    db = Database()
    logger.info("👷 Worker started. Listening for WhatsApp webhook jobs...")
    
    while True:
        try:
            job = db.get_next_webhook_job()
            if job:
                job_id = job['id']
                payload = job['payload']
                message_sid = job['message_sid']
                
                logger.info(f"⚙️ Processing job {job_id} for MessageSid: {message_sid}")
                
                num_media = int(payload.get('NumMedia', 0))
                from_number = payload.get('From', '')
                message_body = payload.get('Body', '')
                
                try:
                    # Execute heavy lifting synchronously in this worker process
                    handle_message_async(message_sid, from_number, message_body, num_media, payload)
                    
                    # Mark as complete
                    db.complete_webhook_job(job_id)
                    logger.info(f"✅ Job {job_id} completed successfully.")
                except Exception as inner_e:
                    logger.error(f"❌ Job {job_id} failed: {inner_e}")
                    db.fail_webhook_job(job_id, str(inner_e))
            else:
                # No pending jobs, sleep to avoid hammering the DB
                time.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Error in main worker loop: {e}")
            time.sleep(5)  # Backoff on error

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
