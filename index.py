import imaplib
import email
from email.header import decode_header
import ollama

# Buraya kendi bilgilerini gir
EMAIL_HESABI = "abdurahmankaankaya34@gmail.com"
UYGULAMA_SIFRESI = "fhkd lvko rbyz qdac"

print("1. Mail sunucusuna bağlanılıyor...")
mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
mail.login(EMAIL_HESABI, UYGULAMA_SIFRESI)
mail.select("inbox")

print("2. Son mail çekiliyor...")
_, messages = mail.search(None, "ALL")
son_mail_id = messages[0].split()[-1]
_, msg_data = mail.fetch(son_mail_id, "(RFC822)")

# Sadece konuyu (Subject) ve Göndereni alıyoruz
konu = ""
gonderen = ""
for response_part in msg_data:
    if isinstance(response_part, tuple):
        msg = email.message_from_bytes(response_part[1])
        
        # Gönderen bilgisini al
        gonderen = msg.get("From")
        
        # Konuyu utf-8 formatına çevir
        konu_ham, encoding = decode_header(msg["Subject"])[0]
        if isinstance(konu_ham, bytes):
            konu = konu_ham.decode(encoding if encoding else "utf-8")
        else:
            konu = konu_ham

print("-" * 30)
print(f"Kimden: {gonderen}")
print(f"Konu: {konu}")
print(f"Tarih: {msg.get('Date')}")
print("-" * 30)

print("3. Yapay zeka maili inceliyor (Llama3)...")
# Modele vereceğimiz kesin talimat (Prompt Engineering)
prompt = f"Şu mail konusunu oku ve sadece 'ÖNEMLİ' veya 'ÖNEMSİZ' olarak yanıtla. Başka hiçbir kelime kullanma. Açıklama yapma. Mail konusu: {konu}"

response = ollama.chat(model='llama3', messages=[
  {'role': 'user', 'content': prompt}
])

karar = response['message']['content'].strip()

print(f">>> YAPAY ZEKA KARARI: {karar}")

mail.logout()