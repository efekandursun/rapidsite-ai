from core.whatsapp_handler import handle_message_async

try:
    handle_message_async("test_sid", "whatsapp:+905464055467", "Today at Building B, 10 workers from Acme worked for 8 hours each on Electrical installations. Also, our main excavator was active for 8 hours doing foundation excavation at Building B. However, around 11 AM a severe rainstorm started and we had to halt work for 3 hours due to the weather. Meanwhile, a safety violation was issued to a worker named John Doe because he was not wearing his hard hat.", 0, {})
except Exception as e:
    import traceback
    traceback.print_exc()
