import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 1. .env dosyasındaki değişkenleri yüklüyoruz
load_dotenv()

class SantiyeParser:
    def __init__(self):
        # OpenRouter ayarları ve API Key bağlantısı
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        # Ücretsiz ve zeki modelimiz: Llama 3.1 8B
        self.model = "meta-llama/llama-3.1-8b-instruct:free"

    def get_system_prompt(self):
        """AI'ya inşaat mühendisi kimliği ve veri formatı talimatı verir."""
        return """
        Sen uzman bir inşaat saha mühendisi ve veri analistisin. 
        Görevin, sahadan gelen ses dökümlerini analiz edip SADECE JSON formatında döndürmektir.
        
        KATEGORİLER: 
        - Uretim: Beton dökümü, kalıp çakımı, duvar örümü gibi imalatlar.
        - Stok: Sahaya gelen veya sahadan çıkan malzemeler (çimento, demir vb.).
        - Personel: Çalışan sayısı, usta-işçi bilgisi.
        - Ariza: Makine bozulmaları, duruşlar.

        JSON ŞEMASI:
        {
            "kategori": "Uretim/Stok/Personel/Ariza",
            "islem": "Yapılan işin kısa adı",
            "miktar": sayısal değer veya null,
            "birim": "m3, ton, adet, m2 vb.",
            "lokasyon": "Blok/Kat bilgisi",
            "ozet": "Profesyonel kısa özet"
        }
        
        KURALLAR:
        1. Asla JSON dışında bir metin (Açıklama, 'İşte cevabın' vb.) yazma.
        2. Teknik terimleri (donatı, pabuç, aks) anla ve doğru işle.
        """

    def parse_text(self, raw_text):
        """Düz metni AI'ya gönderir ve JSON objesi olarak geri alır."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": raw_text}
                ],
                # Bazı modellerde JSON mode zorunludur, free modellerde de hata payını azaltır
                response_format={ "type": "json_object" }
            )
            
            # AI'dan gelen string'i Python sözlüğüne (dict) çeviriyoruz
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            return {"error": f"AI Analiz Hatası: {str(e)}"}

# --- MANUEL TEST ---
if __name__ == "__main__":
    parser = SantiyeParser()
    
    # Test için örnek bir şantiye cümlesi
    test_metni = "Selam, bugün C blok 4. kata 85 metreküp hazır beton döküldü, ekipte 4 usta vardı."
    
    print("--- Analiz Başlatılıyor ---")
    analiz_sonucu = parser.parse_text(test_metni)
    
    # Sonucu ekrana güzelce basalım
    print(json.dumps(analiz_sonucu, indent=4, ensure_ascii=False))