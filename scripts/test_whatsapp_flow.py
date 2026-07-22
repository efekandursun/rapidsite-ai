import sys
import json
import asyncio
import re
from unittest.mock import patch
sys.path.append('.')
from core.whatsapp_handler import process_text_message, format_confirmation
from core.database import Database

def main():
    print("🚀 WHATSAPP SİMÜLATÖRÜ BAŞLADI\n(Çıkmak için 'exit' yazın)\n")
    
    number = "+905464055467"
    
    while True:
        try:
            mesaj = input("📝 [SEN]: ")
            if mesaj.lower() in ['exit', 'quit', 'çıkış']:
                break
                
            if not mesaj.strip():
                continue
                
            print("\n⏳ Yapay Zeka Düşünüyor...")
            
            # process_text_message işlemleri yapar ve bir sözlük döner
            result = process_text_message(mesaj, None, number, [])
            
            if result:
                # Dönen sözlüğü WhatsApp formatına çevir
                bot_message = format_confirmation(result)
                
                print("\n" + "="*50)
                print(f"🟢 [BOT]:\n{bot_message}")
                print("="*50 + "\n")
                
                # Bot her mesajın sonuna butonları ekler
                print("What would you like to do?\n[👍 Send]\n[✏️ Edit]\n")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Hata: {e}")

if __name__ == "__main__":
    main()
