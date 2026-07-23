import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.whatsapp_handler import process_text_message

def run_chaos_test():
    phone = "+905464055467"
    
    msg = """Abi bugün şantiyede tam bir karmaşa vardı. Sabah hava felaketti, resmen fırtına koptu o yüzden işe başlayamadık. 
    Apex ekibinden 5 usta geldi ama yağmur yüzünden 2 saat çadırda yattılar, sonra 6 saat çalışabildiler. 
    Öğlene doğru CemCorp'tan 10 ton çimento bekliyorduk, adamlar yanlışlıkla 5 ton getirmiş, bir de irsaliyeyi kaybetmişler. 
    Bu yetmezmiş gibi kiraladığımız CAT ekskavatör öğleden sonra arıza yaptı, 4 saat boşta bekledi sadece 2 saat çalışabildi. 
    Bir de ufak bir kaza atlattık, işçilerden biri baret takmadığı için kafasını iskeleye çarptı, Allahtan ciddi bir şey yok ama revire gönderdik. 
    Son olarak not düşeyim, ana kapının kilidi tamamen bozulmuş, yarın acil tamir edilmesi lazım yoksa güvenlik zafiyeti olacak."""

    print("📤 Mesaj işleniyor...")
    print(f"Mesaj: {msg}\n")
    
    result = process_text_message(msg, None, phone, [])
    
    print("\n✅ İşlem tamamlandı!")
    if result and 'parsed_data_list' in result:
        print(f"Toplam {len(result['parsed_data_list'])} farklı veri çıkarıldı ve veritabanına kaydedildi.")
        for item in result['parsed_data_list']:
            print(f"- [{(item.get('log_type') or 'bilinmiyor').upper()}] {item.get('description', '')[:60]}...")
    else:
        print("Sonuç:", result)

if __name__ == "__main__":
    run_chaos_test()
