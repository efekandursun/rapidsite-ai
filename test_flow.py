import json
from core.brain import ConstructionBrain
brain = ConstructionBrain()

print("--- Initial Message ---")
msg1 = "Hi boss, I'm at building A right now and we got 250 pieces of bricks right now. What should we do?"
parsed1 = [
  {
    "status": "incomplete",
    "follow_up_question": "Could you please provide the vendor name and the time of delivery for the bricks?",
    "project_id": None,
    "project_name": None,
    "translated_transcript": None,
    "log_type": "delivery",
    "description": "Received 250 pieces of bricks at Building A.",
    "item": "Bricks",
    "quantity": 250,
    "unit": "EA",
    "location": {
      "name": "Building A",
      "building": "Building A",
      "level": None,
      "area": None
    },
    "cost_code": None,
    "delivery_details": {
      "delivery_from": None,
      "tracking_number": None,
      "time": None,
      "contents": "250 pieces of bricks"
    },
    "urgency": "normal",
    "procore_ready": False
  }
]
print(json.dumps(parsed1, indent=2))

print("\n--- Follow up Message (Misunderstood) ---")
msg2 = "Vietnam'da Apex yapmadılar"
if isinstance(parsed1, list):
    parsed1 = parsed1[0]
resolution = brain.resolve_incomplete(parsed1, msg2)
print(json.dumps(resolution, indent=2))
