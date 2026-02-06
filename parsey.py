import openai
import json

def parse_santiye_data(raw_text):
    # Bu prompt, AI'nın bir inşaat mühendisi gibi düşünmesini sağlar
    system_instruction = """
    Sen bir inşaat veri analiz uzmanısın. Kullanıcıdan gelen düz metni oku ve aşağıdaki JSON şemasına uygun şekilde parçala.
    
    ŞEMA:
    {
      "kategori": "Uretim / Stok / Personel / Ariza",
      "islem_detayi": "Yapılan işin kısa adı",
      "miktar": sayisal deger veya null,
      "birim": "m3, ton, adet, m2 vb.",
      "lokasyon": "Blok, kat veya mahâl bilgisi",
      "notlar": "Ekstra bilgiler veya acil durumlar"
    }
    
    KURALLAR:
    1. Sadece saf JSON döndür.
    2. Eğer miktar belirtilmemişse null bırak.
    3. Teknik terimleri (donatı, kalıp, aplikasyon) doğru sınıflandır.
    """

    client = openai.OpenAI(api_key="SENIN_API_KEYIN")

    response = client.chat.completions.create(
        model="gpt-4o-mini", # Hem ucuz hem çok hızlı
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": raw_text}
        ],
        response_format={ "type": "json_object" } # JSON garantisi
    )

    return json.loads(response.choices[0].message.content)

# TEST EDELİM:
test_cumlesi = "Selam şefim, bugün A blok 2. katta 150 metreküp beton döktük, ama pompa arıza yaptı yarım kaldı."
print(parse_santiye_data(test_cumlesi))