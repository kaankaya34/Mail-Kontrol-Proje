# Mail Kontrol - Çalıştırma Rehberi

## Gereksinim

- **Python** (venv klasörü proje içinde hazır)
- **MySQL** kurulu ve `mail_kontrol` veritabanı oluşturulmuş olmalı (bkz. [Veritabani-Kurulum/sqlKurulum.md](Veritabani-Kurulum/sqlKurulum.md))
- **Ollama** kurulu ve `qwen2.5:3b` modeli indirilmiş olmalı

---

## Çalıştırma

1. Ollama'nın çalıştığından ve modelin hazır olduğundan emin ol:

```bash
ollama run mail-asistani:v6 ""
```

2. Proje klasöründe terminal aç ve venv'i aktive et:

```bash
cd /home/kaan/Mail-Kontrol-Proje
source venv/bin/activate
```

3. Gerekli paketleri kur (ilk seferde):

```bash
pip install -r requirements.txt
```

4. Uygulamayı başlat:

```bash
python app.py
```

5. Tarayıcıda şu adresi aç:

```
http://localhost:5000
```

---

## Durdurma

Terminalde `Ctrl+C` yeterli.

## Notlar

- Ollama sistemde servis olarak (systemd) sürekli çalışıyorsa ayrıca başlatmana gerek yok, sadece `systemctl status ollama` ile kontrol et
- `app.py` içindeki `DB_KONFIG` alanında MySQL kullanıcı adı/şifresini kendi ortamına göre ayarla
