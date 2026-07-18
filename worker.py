"""
RapidSite AI - Background Worker
Processes WhatsApp webhook jobs from the database queue safely and asynchronously.
Designed to run as a separate process in production.
"""

import time
import logging
from core.database import Database
from core.whatsapp_handler import handle_message_async

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_jobs():
    db = Database()
    logging.info("🚀 Background worker started. Polling for jobs...")

    while True:
        try:
            job = db.get_next_webhook_job()
            
            if job:
                job_id = job['id']
                message_sid = job['message_sid']
                payload = job['payload']
                
                logging.info(f"⏳ Processing job #{job_id} for MessageSid: {message_sid}")
                
                # Extract fields expected by handle_message_async
                from_number = payload.get('From', '')
                message_body = payload.get('Body', '')
                num_media = int(payload.get('NumMedia', 0))
                
                try:
                    # Execute the heavy lifting AI logic
                    handle_message_async(message_sid, from_number, message_body, num_media, payload)
                    
                    # Mark as completed
                    db.complete_webhook_job(job_id)
                    logging.info(f"✅ Job #{job_id} completed successfully.")
                    
                except Exception as e:
                    logging.exception(f"❌ Error processing job #{job_id}")
                    db.fail_webhook_job(job_id, str(e))
            else:
                # No jobs found, sleep before polling again
                time.sleep(2)
                
        except Exception as e:
            logging.error(f"❌ Worker loop error: {e}")
            time.sleep(5) # Prevent tight loop on DB failure

if __name__ == "__main__":
    process_jobs()
