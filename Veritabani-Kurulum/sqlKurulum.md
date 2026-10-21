# SQL Veritabanı Kurulum Rehberi

## 
    xamp i kurulumunu tamamladıktan sonra, projenin çalışması için gerekli olan MySQL veritabanını kurmak gerekiyor. Aşağıda adım adım nasıl yapacağınızı anlatacağım.py 
## Kurulum Adımları

### 1. setup_db.sql Dosyasını Aç

**MySQL Workbench ile:**
1. MySQL Workbench'i aç
2. Bağlantı seç (localhost)
3. Sol üstte: `File` → `Open SQL Script`
4. `setup_db.sql` dosyasını seç
5. `Execute` (Petekli ikon) tuşuna bas veya `Ctrl+Shift+Enter`

**phpMyAdmin ile:**
1. tarayıcıda: `http://localhost/phpmyadmin`
2. Giriş yap
3. Üst menüde `Import` tıkla
4. `setup_db.sql` dosyasını seç
5. `Import` tuşuna bas

**Command Line ile:**
1. PowerShell/CMD aç
2. Proje klasörüne git:
```bash
cd C:\Users\abdur\Desktop\Mail-Kontrol-Proje
```
3. Komutu çalıştır:
```bash
mysql -u root -p < setup_db.sql
```
   - Şifre sor ↓ (eğer varsa gir, yoksa Enter bas)

---

## Hata Çözümleri

### Hata 1: "ERROR 1045 - Access Denied"
**Sebep:** Yanlış kullanıcı adı veya şifre

**Çözüm:**
- Eğer MySQL şifresi varsa, `setup_db.sql`'i aç
- Yada doğru kullanıcı ile giriş yap

**Command Line'da:**
```bash
mysql -u root -pSİFRENİZ < setup_db.sql
```
(Şifrenin hemen sonra boşluksuz yazılması gerekir)

---

### Hata 2: "ERROR 1007 - Database Already Exists"
**Sebep:** mail_kontrol veritabanı zaten var

**Çözüm:** 
Bu normal, script `IF NOT EXISTS` komutu kullanıyor, devam et.

**Tamamen yeniden kurmak istersen:**
1. MySQL Workbench'te:
```sql
DROP DATABASE mail_kontrol;
```
2. Sonra `setup_db.sql`'yi tekrar çalıştır

---

### Hata 3: "ERROR 1064 - Syntax Error"
**Sebep:** SQL kodunda hata var

**Çözüm:**
- `setup_db.sql` dosyasını kopyala-yapıştır ederken yanlış yapılmış olabilir
- Dosyayı GitHub'dan yeniden indir ya da böyle bir mesaj al ise bana haber ver

---

### Hata 4: "ERROR 2002 - Can't Connect to MySQL"
**Sebep:** MySQL servisi çalışmıyor

**Çözüm:**

**Windows'ta:**
1. `services.msc` aç (Windows + R → services.msc)
2. `MySQL80` bulup çift tıkla (veya MySQL sürümün adı)
3. `Startup type` → "Automatic" seç
4. `Start` tuşuna bas
5. OK

**Komut satırında:**
```bash
net start MySQL80
```

---

### Hata 5: "ERROR 1231 - Incorrect Value"
**Sebep:** MySQL sürümü çok eski

**Çözüm:**
- MySQL 8.0+ kullanıyor musun kontrol et:
```sql
SELECT VERSION();
```
- Eski sürümde ise upgradeyle

---

### Hata 6: "Tablo Oluşturulmadı, Hiçbir Hata Yok"
**Sebep:** Betik çalıştı ama tabloları görmüyorsun

**Çözüm:**
```sql
USE mail_kontrol;
SHOW TABLES;
```

Eğer tabloları görmüyorsan:
1. `setup_db.sql` tamamını kopyala-yapıştır yap
2. `USE mail_kontrol;` satırından sonra başla

---

## Doğru Kuruldu Mu Kontrol Et?

Kurulum sonra bunu çalıştır:

```sql
USE mail_kontrol;
SHOW TABLES;
```

**Şu tabloları görmelisin:**
- duzeltmeler
- kurallar
- mails_onemli
- mails_onemsiz
- mails_spam
- users

Tüm 6 tablo görünüyorsa ✓ **Kurulum başarılı!**

---

## İçerik Kontrol

Tabloların doğru sütunları var mı diye kontrol:

```sql
DESCRIBE users;
DESCRIBE mails_onemli;
DESCRIBE kurallar;
```

---

## Şifre/Kullanıcı Değiştirmek

**MySQL'de root şifresi varsa:**

setup_db.sql dosyasının başına ekle:
```sql
-- Kullanıcı ve Şifre Değiştir
CREATE USER 'admin'@'localhost' IDENTIFIED BY 'sifre123';
GRANT ALL PRIVILEGES ON mail_kontrol.* TO 'admin'@'localhost';
```

Sonra uygulamada `app.py` dosyasında:
```python
db_connection = pymysql.connect(
    host="localhost",
    user="admin",           # ← Bunu değiştir
    password="sifre123",    # ← Bunu değiştir
    database="mail_kontrol"
)
```

---

## Başka Bilgisayara Taşıyorum

1. `setup_db.sql` dosyasını kopyala
2. Diğer bilgisayarda MySQL yükle
3. Aynı adımları takip et

**Tamamen aynı veritabanını taşıyacaksan:**
```sql
mysqldump -u root -p mail_kontrol > backup.sql
```

Sonra diğer bilgisayarda:
```sql
mysql -u root -p < backup.sql
```

---

## Daha Fazla Yardım Gerekiyorsa

- MySQL uyarı mesajını kopyala-yapıştır et
- Hangi yöntemi kullandığını söyle (Workbench/phpMyAdmin/CMD)
- Hangi adımda takıldığını anlat
