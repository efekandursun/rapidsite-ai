import re
texts = [
    "edit 9: change to 5",
    "9 numarayı düzenle, çimento 60 olacak",
    "edit rapor 103 çimento 60",
    "103 düzenle 50 olsun",
    "  103'ü düzenle 50 olsun"
]

for text in texts:
    cleaned_text = text.strip().lower()
    edit_match = re.match(r'^(?:edit|düzenle|duzenle|değiştir|degistir)\s*(?:rapor|report|numara|#)?\s*(\d+)[:\s,\-]+(.*)', cleaned_text)
    if not edit_match:
        edit_match = re.match(r'^(\d+)\s*(?:numarayı|numarali|numaralı|raporu|report|\'ü|\'u|i|ı)?\s*(?:edit|düzenle|duzenle|değiştir|degistir)[:\s,\-]+(.*)', cleaned_text)
    
    if edit_match:
        print(f"MATCH: {text} -> ID: {edit_match.group(1)}, Text: {edit_match.group(2)}")
    else:
        print(f"NO MATCH: {text}")
