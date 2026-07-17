import json
from dotenv import load_dotenv
from core.brain import ConstructionBrain

load_dotenv()

brain = ConstructionBrain()
text = "Bugün A Blok 3. katta taşeron firmadan 5 demirci çalıştı, toplam 10 ton demir bağladılar. Ayrıca kule vinç sabahtan beri 6 saat aktif kullanıldı, 2 saat de rölantide boşta bekledi."
print("Parsing text...")
result = brain.parse_text(text)

print(f"Type: {type(result)}")
print(json.dumps(result, indent=2, ensure_ascii=False))
