from core.brain import ConstructionBrain
import json
brain = ConstructionBrain()
print(json.dumps(brain.parse_text("Vietnam'da Apex yapmadılar"), indent=2))
