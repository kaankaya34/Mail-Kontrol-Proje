import imaplib
import email
import re as _re
import os
from email.header import decode_header
from email.utils import parseaddr
import ollama
import json
import queue
import threading
import time
import hashlib
import logging
import pymysql
import kural_filtresi
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, Response, render_template, jsonify, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "mailkontrol-gizli-anahtar-2024"

_ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_ollama_client = ollama.Client(host=_ollama_host, timeout=120)

log = logging.getLogger("mail_kontrol")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL_ADI = "mail-asistani:v6"
MODEL_DENEME = 3

durdur_flaglari = {}   # { user_id: True/False }
analiz_pozisyon = {}   # { user_id: int } - sonraki taranacak mail indeksi (0 = bastan)
tarama_gecmisi = {}    # { user_id: [ {tarih, yeni, durum}, ... ] }

DB_KONFIG = {
    "host": "localhost",
    "user": "kaan",
    "password": "123456",
    "database": "mail_kontrol",
    "charset": "utf8mb4"
}


def db_baglanti():
    return pymysql.connect(**DB_KONFIG)


def db_tablolari_olustur():
    """Eksik tablolari otomatik olusturur."""
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS duzeltmeler (
                id INT AUTO_INCREMENT PRIMARY KEY,
                gonderen VARCHAR(255),
                konu TEXT,
                eski_karar VARCHAR(20),
                yeni_karar VARCHAR(20),
                tarih VARCHAR(20),
                user_id INT NOT NULL
            ) CHARACTER SET utf8mb4
        """)
    con.commit()
    con.close()


db_tablolari_olustur()


def giris_gerekli(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def aktif_kullanici():
    if "user_id" not in session:
        return None
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("SELECT id, ad, email, gmail_hesabi, gmail_sifre FROM users WHERE id = %s", (session["user_id"],))
        row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "ad": row[1], "email": row[2], "gmail_hesabi": row[3], "gmail_sifre": row[4]}


def turkce_normalize(metin):
    """Türkçe karakterleri ASCII'ye çevirir, büyük harf yapar."""
    return (
        metin.upper()
        .replace("Ö", "O").replace("ö", "O")
        .replace("İ", "I").replace("ı", "I")
        .replace("Ş", "S").replace("ş", "S")
        .replace("Ç", "C").replace("ç", "C")
        .replace("Ğ", "G").replace("ğ", "G")
        .replace("Ü", "U").replace("ü", "U")
    )


def mime_baslik_decode(deger):
    """=?UTF-8?...?= gibi MIME basliklarini okunur metne cevirir."""
    if not deger:
        return ""
    parcalar = decode_header(deger)
    cozulmus = []
    for yazi, enc in parcalar:
        if isinstance(yazi, bytes):
            try:
                cozulmus.append(yazi.decode(enc if enc and enc.lower() not in ("unknown-8bit",) else "utf-8"))
            except (UnicodeDecodeError, LookupError):
                cozulmus.append(yazi.decode("latin-1", errors="replace"))
        else:
            cozulmus.append(yazi or "")
    return "".join(cozulmus).strip()


def kaydet(message_id, gonderen, konu, karar, user_id, mail_tarihi=None, con=None):
    tarih = mail_tarihi or datetime.now().strftime("%Y-%m-%d %H:%M")
    # Belirsiz/bilinmeyen karar Onemsiz'e degil Onemli'ye gider
    if "ONEMSIZ" in turkce_normalize(karar):
        tablo = "mails_onemsiz"
    else:
        tablo = "mails_onemli"
    _kapat = con is None
    if _kapat:
        con = db_baglanti()
    with con.cursor() as cur:
        # Ayni mail iki tabloda birden bulunmasin
        cur.execute(
            "SELECT 1 FROM mails_onemli WHERE message_id=%s AND user_id=%s "
            "UNION SELECT 1 FROM mails_onemsiz WHERE message_id=%s AND user_id=%s LIMIT 1",
            (message_id, user_id, message_id, user_id)
        )
        if cur.fetchone():
            log.info("Mukerrer mail atlandi: %s", message_id)
            if _kapat:
                con.close()
            return False
        cur.execute(
            f"INSERT IGNORE INTO {tablo} (message_id, gonderen, konu, tarih, user_id) VALUES (%s, %s, %s, %s, %s)",
            (message_id, gonderen, konu, tarih, user_id)
        )
    con.commit()
    if _kapat:
        con.close()
    return True


def gecmis_getir(user_id):
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("SELECT message_id, gonderen, konu, tarih FROM mails_onemli WHERE user_id=%s ORDER BY tarih DESC", (user_id,))
        onemli = cur.fetchall()
        cur.execute("SELECT message_id, gonderen, konu, tarih FROM mails_onemsiz WHERE user_id=%s ORDER BY tarih DESC", (user_id,))
        onemsiz = cur.fetchall()
    con.close()
    return {
        "onemli": [{"message_id": r[0], "gonderen": r[1], "konu": r[2], "tarih": r[3]} for r in onemli],
        "onemsiz": [{"message_id": r[0], "gonderen": r[1], "konu": r[2], "tarih": r[3]} for r in onemsiz]
    }


def db_tum_message_idler(user_id):
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute(
            "SELECT message_id FROM mails_onemli WHERE user_id = %s "
            "UNION "
            "SELECT message_id FROM mails_onemsiz WHERE user_id = %s",
            (user_id, user_id)
        )
        rows = cur.fetchall()
    con.close()
    return {r[0] for r in rows}


def hizli_filtre(gonderen, konu):
    """
    Kesin ONEMLI oldugu belli mailleri AI'a gonderme.
    None donerse karar belirsiz, AI'a gonder.
    """
    k = turkce_normalize(konu)

    # ── Kesinlikle ONEMLI — direkt karar ver ──────────────────────────
    kesin_onemli_konu = [
        # Guvenlik / hesap
        "PAROLA SIFIRLA", "SIFRENIZI SIFIRLAYIN", "SIFRE SIFIRLAMA",
        "HESABINIZ KILITLENDI", "HESABINIZ ASKIYA ALINDI",
        "GUVENLIK UYARISI", "GUVENLIK BILDIRIMI", "GUVENLIK KODU",
        "SECURITY ALERT", "SECURITY NOTIFICATION", "SECURITY CODE",
        "SUSPICIOUS ACTIVITY", "UNUSUAL ACTIVITY", "UNUSUAL SIGN",
        "SIGN-IN ATTEMPT", "LOGIN ATTEMPT", "NEW SIGN-IN",
        "VERIFY YOUR", "VERIFICATION CODE", "DOGRULAMA KODU",
        "HESAP DOGRULAMA", "EMAIL DOGRULAMA", "TWO-FACTOR",
        "2FA", "OTP",
        # Is / kariyer
        "MULAKAT", "IS TEKLIFI", "BASVURUNUZ", "BASVURU SONUCU",
        "ISSIZLIK", "CALISMA IZNI",
        # Finans / resmi
        "FATURA", "ODEME BILDIRIMI", "BORCUNUZ", "KREDI KARTI",
        "BANKA HESABINIZ", "PARA TRANSFERI", "IBAN",
        "SGK", "MAHKEME", "NOTER", "VERGI DAIRESI",
        # Kargo / teslimat
        "KARGONUZ", "TESLIMAT BILDIRIMI", "SIPARISINIZ TESLIM",
        # Egitim
        "SINAV SONUCU", "HARF NOTUNUZ", "TRANSKRIPT",
        "UNIVERSITE KABUL", "DIPLOMA",
        # Sozlesme
        "SOZLESME", "KIRA SOZLESMESI", "SIGORTA POLIÇESI",
    ]
    for ipucu in kesin_onemli_konu:
        if ipucu in k:
            return "ONEMLI"

    # Onemsiz kararini (no-reply gonderen, kampanya/indirim kelimeleri vb.) artik
    # bu filtre vermez: OTP/sifre mailleri de no-reply adreslerinden gelir.
    return None  # Belirsiz, AI'a gonder


def model_sor(gonderen, konu, govde):
    """Modele Modelfile'daki sablonla uyumlu duz metin gonderir (system prompt ezilmez).
    Basarisiz/belirsiz durumda 'ONEMLI' dondurur ve loglar."""
    metin = f"Gönderen: {gonderen}\nKonu: {konu}"
    govde = (govde or "").strip()[:300]
    if govde:
        metin += f"\nİçerik:\n{govde}"
    son_hata = None
    for deneme in range(1, MODEL_DENEME + 1):
        try:
            response = _ollama_client.chat(
                model=MODEL_ADI,
                options={"temperature": 0, "num_predict": 32},
                keep_alive="30m",
                messages=[{"role": "user", "content": metin}]
            )
            cevap = turkce_normalize((response["message"]["content"] or "").strip())
            if "ONEMSIZ" in cevap:
                return "ONEMSIZ"
            if "ONEMLI" in cevap:
                return "ONEMLI"
            log.warning("Beklenmeyen model cevabi %r -> ONEMLI (%s | %s)", cevap, gonderen, konu)
            return "ONEMLI"
        except Exception as ex:
            son_hata = ex
            log.warning("Model hatasi (deneme %d/%d): %s", deneme, MODEL_DENEME, ex)
            time.sleep(deneme)
    log.error("Model cevap vermedi, mail ONEMLI sayildi: %s | %s (%s)", gonderen, konu, son_hata)
    return "ONEMLI"


def siniflandir(gonderen, konu, govde, kurallar=None):
    """(karar, kaynak) dondurur. Sira: kullanici kurali -> kural_filtresi -> hizli_filtre -> model."""
    kural_karar = kural_kontrol(gonderen, konu, kurallar)
    if kural_karar is not None:
        return kural_karar, "kural"
    sonuc = kural_filtresi.karar(gonderen, konu, (govde or "")[:400])
    if sonuc is not None:
        return ("ONEMSIZ" if "ONEMSIZ" in turkce_normalize(sonuc) else "ONEMLI"), "kural_filtresi"
    sonuc = hizli_filtre(gonderen, konu)
    if sonuc is not None:
        return sonuc, "filtre"
    return model_sor(gonderen, konu, govde), "model"


def kurallar_getir(user_id):
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute(
            "SELECT id, tur, deger, karar, tarih FROM kurallar WHERE user_id = %s ORDER BY id ASC",
            (user_id,)
        )
        rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "tur": r[1], "deger": r[2], "karar": r[3], "tarih": r[4]} for r in rows]


def kural_kontrol(gonderen, konu, kurallar):
    """Kullanici kurallarini uygula. Eslesen kural varsa kararini dondur, yoksa None."""
    if not kurallar:
        return None
    g = turkce_normalize(gonderen)
    k = turkce_normalize(konu)
    for kural in kurallar:
        deger = turkce_normalize(kural["deger"])
        if kural["tur"] == "gonderen" and deger in g:
            return kural["karar"]
        elif kural["tur"] == "konu" and deger in k:
            return kural["karar"]
    return None


def duzeltmeler_getir(user_id, limit=8):
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute(
            "SELECT gonderen, konu, yeni_karar FROM duzeltmeler WHERE user_id = %s ORDER BY id DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cur.fetchall()
    con.close()
    return [{"gonderen": r[0], "konu": r[1], "karar": r[2]} for r in rows]


def mail_analiz_generator(q, kullanici):
    EMAIL_HESABI = kullanici["gmail_hesabi"]
    UYGULAMA_SIFRESI = kullanici["gmail_sifre"]
    user_id = kullanici["id"]

    def run():
        durdur_flaglari[user_id] = False
        analiz_con = None
        try:
            q.put({"step": 1, "state": "active", "desc": "Gmail'e baglaniliyor..."})
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
            mail.login(EMAIL_HESABI, UYGULAMA_SIFRESI)
            mail.select("inbox")
            q.put({"step": 1, "state": "done", "desc": "Baglanti basarili"})

            q.put({"step": 2, "state": "active", "desc": "Mailler aliniyor..."})
            _, messages = mail.search(None, "ALL")
            # En yeniden eskiye
            mail_idleri = list(reversed(messages[0].split()))
            toplam = len(mail_idleri)
            taranan_idler = db_tum_message_idler(user_id)
            tekil = kural_filtresi.Tekillestirici()
            for _mid in taranan_idler:
                tekil.yeni_mi(_mid)

            # DB'den kayitli pozisyonu yukle
            _con_p = db_baglanti()
            with _con_p.cursor() as _cur:
                _cur.execute(
                    "SELECT COALESCE(analiz_idx,0), COALESCE(son_imap_toplam,0) FROM users WHERE id=%s",
                    (user_id,)
                )
                _satir = _cur.fetchone()
            _con_p.close()
            saved_idx = int(_satir[0]) if _satir else 0
            son_imap_toplam_db = int(_satir[1]) if _satir else 0

            # Son taramadan beri kac yeni mail geldi?
            yeni_sayisi = max(0, toplam - son_imap_toplam_db) if son_imap_toplam_db > 0 else 0

            if saved_idx >= toplam:
                saved_idx = 0

            # ── Taranacak liste olustur ──────────────────────────────────────
            _tarama_hazir = False

            # Gecis durumu: DB'de pozisyon bilgisi yok ama onceki taramadan veri var
            # Tum mailleri tara — taranan_idler check ile skip edilir,
            # kac tane yeni mail olursa olsun hepsi yakalanir (tek seferlik maliyet)
            if son_imap_toplam_db == 0 and saved_idx == 0 and len(taranan_idler) > 0:
                taranacak_idler = mail_idleri
                global_idx_listesi = list(range(toplam))
                _tarama_hazir = True
                # son_imap_toplam'i DB'ye kaydet ki bir sonraki calistirmada duzgun calisssin
                _con_s = db_baglanti()
                with _con_s.cursor() as _cur:
                    _cur.execute(
                        "UPDATE users SET son_imap_toplam=%s WHERE id=%s",
                        (toplam, user_id)
                    )
                _con_s.commit()
                _con_s.close()

            if not _tarama_hazir:
                # Durum 1: Hic tarama yapilmamis (ilk calistirma veya tam sifirla)
                if son_imap_toplam_db == 0 and saved_idx == 0:
                    taranacak_idler = mail_idleri
                    global_idx_listesi = list(range(toplam))

                # Durum 2: Onceki tarama tamamlandi — sadece yeni gelen mailleri tara
                elif saved_idx == 0:
                    if yeni_sayisi > 0:
                        taranacak_idler = mail_idleri[:yeni_sayisi]
                        global_idx_listesi = list(range(yeni_sayisi))
                    else:
                        taranacak_idler = []
                        global_idx_listesi = []

                # Durum 3: Devam taramasi + yeni mailler var
                elif yeni_sayisi > 0:
                    adjusted = min(saved_idx + yeni_sayisi, toplam)
                    tum_range = list(range(0, yeni_sayisi)) + list(range(adjusted, toplam))
                    taranacak_idler = [mail_idleri[i] for i in tum_range]
                    global_idx_listesi = tum_range

                # Durum 4: Devam taramasi, yeni mail yok
                else:
                    taranacak_idler = mail_idleri[saved_idx:]
                    global_idx_listesi = list(range(saved_idx, toplam))

            taranacak_sayisi = len(taranacak_idler)
            zaten_taranmis = len(taranan_idler)

            devam_notu = ""
            if saved_idx > 0:
                devam_notu += f" | {saved_idx}. pozisyondan devam"
            if yeni_sayisi > 0:
                devam_notu += f" | {yeni_sayisi} yeni mail once taranacak"
            if taranacak_sayisi == 0:
                devam_notu = " | tum mailler taranmis, yeni mail yok"
            q.put({
                "step": 2, "state": "done",
                "desc": f"{toplam} mail | {zaten_taranmis} taranmis | {taranacak_sayisi} taranacak{devam_notu}",
                "toplam_taranacak": taranacak_sayisi
            })

            if taranacak_sayisi == 0:
                q.put({"step": 3, "state": "done", "desc": "Taranacak yeni mail bulunamadi"})
                q.put({"step": 4, "state": "done", "desc": "Islem tamamlandi"})
                q.put({"type": "done"})
                return

            q.put({"step": 3, "state": "active", "desc": "Yeni mailler analiz ediliyor..."})
            yeni = 0

            kurallar_cache = kurallar_getir(user_id)
            analiz_con = db_baglanti()

            # ── Batch MESSAGE-ID pre-scan ────────────────────────────────────
            # Tum taranacak maillerin MESSAGE-ID'sini toplu cek (150'lik gruplar)
            # Boylece her mail icin ayri IMAP istegi gitmez
            hdr_map = {}  # {mid_bytes: message_id_str}
            _BATCH = 150
            q.put({"step": 3, "state": "active", "desc": f"Mail ID'leri toplu yukleniyor ({taranacak_sayisi} mail, {max(1, (taranacak_sayisi+_BATCH-1)//_BATCH)} istek)..."})
            for _b in range(0, taranacak_sayisi, _BATCH):
                _batch = taranacak_idler[_b:_b + _BATCH]
                _ids = b','.join(_batch)
                try:
                    _, _data = mail.fetch(_ids, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                    for _part in _data:
                        if isinstance(_part, tuple):
                            _hdr = email.message_from_bytes(_part[1])
                            _mid_str = _hdr.get("Message-ID", "").strip()
                            _m = _re.match(rb'(\d+)', _part[0])
                            if _m and _mid_str:
                                hdr_map[_m.group(1)] = _mid_str
                except Exception:
                    pass  # Hata durumunda loop'ta fallback kullanilir

            for offset, mid in enumerate(taranacak_idler):
                global_idx = global_idx_listesi[offset]
                i = global_idx + 1  # gosterim indeksi
                if durdur_flaglari.get(user_id, False):
                    analiz_pozisyon[user_id] = global_idx
                    with analiz_con.cursor() as _cur:
                        _cur.execute(
                            "UPDATE users SET analiz_idx=%s, son_imap_toplam=%s WHERE id=%s",
                            (global_idx, toplam, user_id)
                        )
                    analiz_con.commit()
                    tarama_gecmisi.setdefault(user_id, []).append({"tarih": datetime.now().strftime("%Y-%m-%d %H:%M"), "yeni": yeni, "durum": "durduruldu"})
                    if len(tarama_gecmisi[user_id]) > 20:
                        tarama_gecmisi[user_id] = tarama_gecmisi[user_id][-20:]
                    q.put({"step": 3, "state": "done", "desc": f"{yeni} mail analiz edildi | pozisyon kaydedildi ({global_idx}/{toplam})"})
                    q.put({"step": 4, "state": "done", "desc": f"{yeni} mail veritabanina kaydedildi"})
                    q.put({"type": "done"})
                    analiz_con.close()
                    mail.logout()
                    return
                # hdr_map'ten message_id al (batch pre-scan); yoksa mail cekildikten sonra belirlenir
                message_id = hdr_map.get(mid, "").strip()

                def _atla():
                    analiz_pozisyon[user_id] = global_idx + 1
                    q.put({"step": 3, "state": "active", "desc": f"[{i}] Zaten taranmis, atlaniyor"})

                id_onceden = bool(message_id)
                if id_onceden and not tekil.yeni_mi(message_id):
                    _atla()
                    continue

                # Mail icerigini tek tek al; tum mailleri bellekte toplama.
                _, msg_data = mail.fetch(mid, "(RFC822)")
                msg = None
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        break
                if msg is None:
                    continue

                ham_gonderen = msg.get("From", "Bilinmiyor")
                ad, adres = parseaddr(ham_gonderen)
                ad_cozulmus = mime_baslik_decode(ad)
                gonderen = f"{ad_cozulmus} <{adres}>" if ad_cozulmus and adres else (ad_cozulmus or adres or "Bilinmiyor")
                mail_tarihi = None
                try:
                    from email.utils import parsedate_to_datetime
                    tarih_str = msg.get("Date", "")
                    if tarih_str:
                        mail_tarihi = parsedate_to_datetime(tarih_str).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    mail_tarihi = None
                konu = mime_baslik_decode(msg.get("Subject", ""))

                govde = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        cd = str(part.get("Content-Disposition", ""))
                        if ct == "text/plain" and "attachment" not in cd:
                            try:
                                charset = part.get_content_charset() or "utf-8"
                                govde = part.get_payload(decode=True).decode(charset, errors="replace")
                            except Exception:
                                govde = ""
                            break
                else:
                    try:
                        charset = msg.get_content_charset() or "utf-8"
                        govde = msg.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        govde = ""
                govde = govde.strip()[:800]

                if not id_onceden:
                    message_id = (msg.get("Message-ID") or "").strip()
                    if not message_id:
                        # Message-ID yoksa kararli sentetik anahtar
                        message_id = "noid-" + hashlib.sha1(
                            f"{mail_tarihi}|{gonderen}|{konu}".encode("utf-8")
                        ).hexdigest()
                    if not tekil.yeni_mi(message_id, mail_tarihi, gonderen, konu):
                        _atla()
                        continue

                karar, kaynak = siniflandir(gonderen, konu, govde, kurallar_cache)
                etiket = {"kural": "Kural eslesti", "kural_filtresi": "Kural filtresi", "filtre": "Filtre karar verdi", "model": "AI karar verdi"}[kaynak]
                q.put({"step": 3, "state": "active", "desc": f"[{i}] {etiket} ({karar}): {konu[:45]}", "current": offset + 1, "total": taranacak_sayisi})
                kaydet(message_id, gonderen, konu, karar, user_id, mail_tarihi, con=analiz_con)
                yeni += 1
                analiz_pozisyon[user_id] = global_idx + 1
                # Her 50 mailden bir pozisyonu DB'ye kaydet
                if yeni % 50 == 0:
                    with analiz_con.cursor() as _cur:
                        _cur.execute(
                            "UPDATE users SET analiz_idx=%s, son_imap_toplam=%s WHERE id=%s",
                            (global_idx + 1, toplam, user_id)
                        )
                    analiz_con.commit()
                q.put({
                    "type": "result",
                    "karar": karar,
                    "gonderen": gonderen,
                    "konu": konu,
                    "tarih": mail_tarihi,
                    "message_id": message_id,
                    "cached": False,
                })
                time.sleep(1)

            with analiz_con.cursor() as _cur:
                _cur.execute(
                    "UPDATE users SET analiz_idx=0, son_imap_toplam=%s WHERE id=%s",
                    (toplam, user_id)
                )
            analiz_con.commit()
            analiz_con.close()
            mail.logout()
            analiz_pozisyon[user_id] = 0  # tum mailler taranmis, sifirla
            tarama_gecmisi.setdefault(user_id, []).append({"tarih": datetime.now().strftime("%Y-%m-%d %H:%M"), "yeni": yeni, "durum": "tamamlandi"})
            if len(tarama_gecmisi[user_id]) > 20:
                tarama_gecmisi[user_id] = tarama_gecmisi[user_id][-20:]
            q.put({"step": 3, "state": "done", "desc": f"{yeni} yeni mail analiz edildi"})
            q.put({"step": 4, "state": "done", "desc": f"{yeni} mail veritabanina kaydedildi"})
            q.put({"type": "done"})

        except Exception as ex:
            if analiz_con:
                analiz_con.close()
            q.put({"step": 1, "state": "error", "desc": f"Hata: {str(ex)}"})
            q.put({"type": "error"})

    threading.Thread(target=run, daemon=True).start()


@app.route("/analiz/durdur", methods=["POST"])
@giris_gerekli
def analiz_durdur():
    durdur_flaglari[session["user_id"]] = True
    return jsonify({"durum": "durduruldu"})


@app.route("/analiz/sifirla", methods=["POST"])
@giris_gerekli
def analiz_sifirla():
    uid = session["user_id"]
    analiz_pozisyon[uid] = 0
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("UPDATE users SET analiz_idx=0, son_imap_toplam=0 WHERE id=%s", (uid,))
    con.commit()
    con.close()
    return jsonify({"durum": "sifirlandi"})


@app.route("/api/karar-duzelt", methods=["POST"])
@giris_gerekli
def karar_duzelt():
    data = request.get_json()
    message_id = data.get("message_id", "").strip()
    yeni_karar = data.get("karar", "").strip().upper()
    if not message_id or yeni_karar not in ("ONEMLI", "ONEMSIZ"):
        return jsonify({"hata": "Gecersiz"}), 400
    user_id = session["user_id"]
    con = db_baglanti()
    with con.cursor() as cur:
        # Oncce onemli tablosunda ara
        cur.execute("SELECT gonderen, konu FROM mails_onemli WHERE message_id = %s AND user_id = %s", (message_id, user_id))
        row = cur.fetchone()
        if row:
            eski_karar_upper = "ONEMLI"
            gonderen, konu = row[0], row[1]
        else:
            cur.execute("SELECT gonderen, konu FROM mails_onemsiz WHERE message_id = %s AND user_id = %s", (message_id, user_id))
            row = cur.fetchone()
            if not row:
                con.close()
                return jsonify({"hata": "Mail bulunamadi"}), 404
            eski_karar_upper = "ONEMSIZ"
            gonderen, konu = row[0], row[1]
        if "ONEMLI" in eski_karar_upper:
            cur.execute("DELETE FROM mails_onemli WHERE message_id = %s AND user_id = %s", (message_id, user_id))
        else:
            cur.execute("DELETE FROM mails_onemsiz WHERE message_id = %s AND user_id = %s", (message_id, user_id))
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M")
        if yeni_karar == "ONEMLI":
            cur.execute("INSERT IGNORE INTO mails_onemli (message_id, gonderen, konu, tarih, user_id) VALUES (%s,%s,%s,%s,%s)",
                        (message_id, gonderen, konu, tarih, user_id))
        else:
            cur.execute("INSERT IGNORE INTO mails_onemsiz (message_id, gonderen, konu, tarih, user_id) VALUES (%s,%s,%s,%s,%s)",
                        (message_id, gonderen, konu, tarih, user_id))
        # Duzeltmeyi few-shot ornegi olarak kaydet
        cur.execute(
            "INSERT INTO duzeltmeler (gonderen, konu, eski_karar, yeni_karar, tarih, user_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (gonderen, konu, eski_karar_upper, yeni_karar, tarih, user_id)
        )
    con.commit()
    con.close()
    return jsonify({"durum": "ok", "gonderen": gonderen, "konu": konu, "yeni_karar": yeni_karar})

@app.route("/api/istatistik")
@giris_gerekli
def istatistik():
    user_id = session["user_id"]
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mails_onemli WHERE user_id=%s", (user_id,))
        onemli_sayisi = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mails_onemsiz WHERE user_id=%s", (user_id,))
        onemsiz_sayisi = cur.fetchone()[0]
        cur.execute(
            "SELECT tarih FROM ("
            "  SELECT tarih FROM mails_onemli WHERE user_id=%s "
            "  UNION ALL "
            "  SELECT tarih FROM mails_onemsiz WHERE user_id=%s"
            ") t ORDER BY tarih DESC LIMIT 1",
            (user_id, user_id)
        )
        son_row = cur.fetchone()
    con.close()
    return jsonify({
        "onemli": onemli_sayisi,
        "onemsiz": onemsiz_sayisi,
        "son_tarih": son_row[0] if son_row else None,
        "tarama_gecmisi": tarama_gecmisi.get(user_id, [])[-10:]
    })


@app.route("/")
@giris_gerekli
def index():
    return render_template("index.html")


@app.route("/arsiv")
@giris_gerekli
def arsiv():
    return render_template("arsiv.html")


@app.route("/kurallar")
@giris_gerekli
def kurallar():
    return render_template("kurallar.html")


@app.route("/api/kurallar", methods=["GET"])
@giris_gerekli
def api_kurallar_listele():
    return jsonify(kurallar_getir(session["user_id"]))


@app.route("/api/kurallar", methods=["POST"])
@giris_gerekli
def api_kural_ekle():
    data = request.get_json()
    tur = data.get("tur", "").strip()
    deger = data.get("deger", "").strip()
    karar = data.get("karar", "").strip().upper()
    if tur not in ("gonderen", "konu") or not deger or karar not in ("ONEMLI", "ONEMSIZ"):
        return jsonify({"hata": "Gecersiz veri"}), 400
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO kurallar (tur, deger, karar, tarih, user_id) VALUES (%s, %s, %s, %s, %s)",
            (tur, deger, karar, datetime.now().strftime("%Y-%m-%d %H:%M"), session["user_id"])
        )
    con.commit()
    con.close()
    return jsonify({"durum": "ok"})


@app.route("/api/kurallar/<int:kural_id>", methods=["DELETE"])
@giris_gerekli
def api_kural_sil(kural_id):
    con = db_baglanti()
    with con.cursor() as cur:
        cur.execute("DELETE FROM kurallar WHERE id = %s AND user_id = %s", (kural_id, session["user_id"]))
    con.commit()
    con.close()
    return jsonify({"durum": "ok"})

@app.route("/analiz")
@giris_gerekli
def analiz():
    kullanici = aktif_kullanici()
    if not kullanici or not kullanici["gmail_hesabi"]:
        return jsonify({"hata": "Gmail bilgileri eksik. Ayarlar sayfasindan ekleyin."}), 400
    q = queue.Queue()
    mail_analiz_generator(q, kullanici)

    def stream():
        while True:
            item = q.get()
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            if item.get("type") in ("done", "error"):
                break

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/gecmis")
@giris_gerekli
def gecmis():
    return jsonify(gecmis_getir(session["user_id"]))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    hata = None
    if request.method == "POST":
        email_giris = request.form.get("email", "").strip()
        sifre_giris = request.form.get("sifre", "").strip()
        con = db_baglanti()
        with con.cursor() as cur:
            cur.execute("SELECT id, ad, sifre FROM users WHERE email = %s", (email_giris,))
            row = cur.fetchone()
        con.close()
        if row and check_password_hash(row[2], sifre_giris):
            session["user_id"] = row[0]
            session["user_ad"] = row[1]
            return redirect(url_for("index"))
        hata = "Email veya sifre yanlis."
    return render_template("login.html", hata=hata)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))
    hata = None
    if request.method == "POST":
        ad = request.form.get("ad", "").strip()
        email_yeni = request.form.get("email", "").strip()
        sifre_yeni = request.form.get("sifre", "").strip()
        if not ad or not email_yeni or not sifre_yeni:
            hata = "Tum alanlari doldurun."
        else:
            try:
                con = db_baglanti()
                with con.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (ad, email, sifre, tarih) VALUES (%s, %s, %s, %s)",
                        (ad, email_yeni, generate_password_hash(sifre_yeni), datetime.now().strftime("%Y-%m-%d %H:%M"))
                    )
                con.commit()
                con.close()
                return redirect(url_for("login"))
            except pymysql.err.IntegrityError:
                hata = "Bu email zaten kayitli."
    return render_template("register.html", hata=hata)


@app.route("/ayarlar", methods=["GET", "POST"])
@giris_gerekli
def ayarlar():
    mesaj = None
    kullanici = aktif_kullanici()
    if request.method == "POST":
        gmail_hesabi = request.form.get("gmail_hesabi", "").strip()
        gmail_sifre = request.form.get("gmail_sifre", "").strip()
        con = db_baglanti()
        with con.cursor() as cur:
            cur.execute(
                "UPDATE users SET gmail_hesabi=%s, gmail_sifre=%s WHERE id=%s",
                (gmail_hesabi, gmail_sifre, session["user_id"])
            )
        con.commit()
        con.close()
        mesaj = "Kaydedildi."
        kullanici = aktif_kullanici()
    return render_template("ayarlar.html", kullanici=kullanici, mesaj=mesaj)


@app.route("/cikis")
def cikis():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
