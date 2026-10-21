"""Kural tabanlı ön filtre (v6): model çalışmadan ÖNCE kesin olan durumları karara bağlar.

Mantık (yanlış negatif en pahalı hata olduğu için asimetrik):
- Güvenlik/OTP kalıpları (tek kullanımlık kod, şifre sıfırlama, yeni cihazdan giriş, hesap kurtarma...) ve
  güvenlik gönderenleri (accountprotection.microsoft.com, security-noreply@...) her zaman "Önemli".
- Resmi/e-Devlet gönderenleri, öğrenci belgesi, randevu talebi, servis kaydı ve Cyberforce destek/akademi
  gönderenleri reklam ipucu YOKSA "Önemli".
- Para/hesap kalıpları (makbuz, iade, ekstre, abonelik iptali...) ve mülakat/burs, mailde indirim/kupon
  gibi reklam ipuçları YOKSA "Önemli".
- "şifre / password / parola / doğrulama" kelimesi başlıkta geçiyorsa (reklam, bülten, rehber ipucu yoksa) "Önemli".
- "Önemsiz" kararı yalnızca hem reklam gönderen/başlık ipucu birlikte varsa verilir (tek ipucu yetmez).
- Emin değilse None döner -> mail modele sorulur.

Kullanım (uygulamada):
    import kural_filtresi
    sonuc = kural_filtresi.karar(gonderen, konu, icerik, list_unsubscribe=False)
    if sonuc is None:
        sonuc = model_sor(...)

Aynı mailin hem önemli hem önemsiz CSV'sine yazılmaması için (v5'te 16 çakışma görüldü):
    tekil = kural_filtresi.Tekillestirici()
    if tekil.yeni_mi(message_id, tarih, gonderen, konu):   # False ise mail zaten işlendi, atla
        ...  # sınıflandır ve TEK bir CSV'ye yaz

Kuralların test setindeki isabetini görmek için:
    python kural_filtresi.py data_v6/test.jsonl
"""
import re
import sys

_TR = str.maketrans("şçğöüâîû", "scgouaiu")


def _fold(text):
    # Türkçe/İngilizce büyük-küçük ve aksan farklarını yok say (ASCII'ye indirge)
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
    return text.lower().translate(_TR)


ONEMLI_KESIN = re.compile("|".join([
    r"tek kullanimlik|tek seferlik|single[- ]use|dogrulama kodu|guvenlik kodu|giris kodu|one[- ]time|verification code",
    r"security code|sign[- ]?in code|passcode|\bpin(iniz)?\b\D{0,12}\d{4,8}|is your .{0,20}code",
    r"kodu(nu)? kimseyle paylasma",
    r"sifre(niz)? (sifirla|degistir)|sifreniz (degisti|sifirlandi)|parola\w* (sifirla|degisti)|sifre\w* sifirlama",
    r"reset (your )?\w*\s?password|password (was |has been )?(reset|changed|updated)|password reset|forgot.{0,10}password",
    r"yeni (bir )?cihaz(da|dan) (oturum|giris)|new sign-?in|sign-?in (alert|attempt)|oturum acma uyari",
    r"suspicious (activity|sign)|olagandisi etkinlik|two-factor|iki adimli dogrulama",
    r"kurtarildi|hesabiniz kilitlendi|\[action (required|advised)\]|hesab\w* guvenligini|recovery (email|phone|info)",
]))

ONEMLI_ORTA = re.compile("|".join([
    r"para iadesi|refund|makbuz|receipt|dekont|ekstre|e-?(arsiv )?fatura|faturaniz|fatura bilgilendirme",
    r"payment (failed|declined)|odemeniz (basarisiz|alindi)|kartiniz reddedildi|kartiniz teslim",
    r"aboneli\w+ (iptal|sona|yenilen)|subscription (will be |has been )?(cancel|expire|renew)|fiyat\w* (artacak|degisiyor)",
    r"mulakat|\bburs\b|interview",
    r"ogrenci belgesi|barkodlu belge|belgeniz hazir|randevu (talebi|onay|bilgi)|randevunuz|servis (kayd|talebi)|onarim",
]))

# Başlıkta geçmesi yeterli olan geniş anahtar kelimeler (reklam/bülten/rehber ipucu yoksa)
ONEMLI_GENIS = re.compile(r"\bsifre\w*|\bpassword\w*|\bparola(niz\w*)?\b|dogrulama")
GENIS_ENGEL = re.compile(r"rehber|ipucu|nedir|guide|tips|checker|strong|how to|roundup|\bweekly\b|\bvpn\b|antivir|yoneticisi")

# Gönderen adresine göre "Önemli" (reklam ipucu yoksa)
ONEMLI_GONDEREN_KESIN = re.compile(r"accountprotection\.microsoft\.com|security-noreply@|@accounts\.google\.com")
ONEMLI_GONDEREN_ORTA = re.compile(
    r"@(?:[\w-]+\.)*(?:turkiye|sgk|osym|gib|mhrs)\.gov\.tr|^(?:destek|akademi|egitim|staj)@(?:[\w-]+\.)*cyberforce\.com\.tr"
)

REKLAM_IPUCU = re.compile(
    r"indirim|kupon|firsat|kampanya|%\s?\d{1,3}|\d{1,3}\s?%|\bsale\b|discount|\boff\b|aldin aldin|haftanin yildizlari|"
    r"bulten|newsletter|weekly digest|webinar"
)
REKLAM_GONDEREN = re.compile(
    r"^(bulten|newsletter|kampanya|marketing|promo|promotions?|campaigns?|deals|offers|digest|mailer|news)\b"
)


def _adres(gonderen):
    adres = re.search(r"<([^>]+)>", gonderen) or re.search(r"(\S+@\S+)", gonderen)
    return _fold(adres.group(1)) if adres else ""


def _yerel_kisim(gonderen):
    return _adres(gonderen).split("@")[0]


def karar(gonderen="", konu="", icerik="", list_unsubscribe=False):
    """'Önemli', 'Önemsiz' veya emin değilse None döner."""
    baslik = _fold(f"{konu}")
    metin = _fold(f"{konu} {icerik[:400]}")
    adres = _adres(gonderen)
    reklam_basligi = bool(REKLAM_IPUCU.search(baslik))
    reklam_metni = bool(REKLAM_IPUCU.search(metin))

    if ONEMLI_KESIN.search(metin):
        return "Önemli"
    if ONEMLI_GONDEREN_KESIN.search(adres) and not reklam_metni:
        return "Önemli"
    if not reklam_metni and (ONEMLI_ORTA.search(baslik) or ONEMLI_GONDEREN_ORTA.search(adres)):
        return "Önemli"
    if not reklam_metni and ONEMLI_GENIS.search(baslik) and not GENIS_ENGEL.search(baslik) and "?" not in baslik:
        return "Önemli"

    reklam_gonderen = bool(REKLAM_GONDEREN.match(_yerel_kisim(gonderen)))
    if (reklam_gonderen and reklam_basligi) or (list_unsubscribe and reklam_basligi):
        return "Önemsiz"
    return None


class Tekillestirici:
    """Aynı mailin iki kez işlenip hem önemli hem önemsiz CSV'sine yazılmasını engeller.

    Anahtar: Message-ID varsa o, yoksa (tarih, gönderen, konu). Büyük/küçük harf ve boşluk farkı yok sayılır.
    """

    def __init__(self):
        self._gorulen = set()

    @staticmethod
    def anahtar(message_id="", tarih="", gonderen="", konu=""):
        mid = (message_id or "").strip().strip("<>").lower()
        if mid:
            return ("id", mid)
        return ("alan", *(" ".join(str(x).split()).lower() for x in (tarih, gonderen, konu)))

    def yeni_mi(self, message_id="", tarih="", gonderen="", konu=""):
        anahtar = self.anahtar(message_id, tarih, gonderen, konu)
        if anahtar in self._gorulen:
            return False
        self._gorulen.add(anahtar)
        return True


def _ayir(mail):
    g = re.search(r"^Gönderen: (.*)$", mail, re.M)
    k = re.search(r"^Konu: (.*)$", mail, re.M)
    i = re.search(r"^İçerik:\n(.*)", mail, re.M | re.S)
    return (g.group(1) if g else ""), (k.group(1) if k else ""), (i.group(1) if i else "")


def _kendi_testi(path):
    import json
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    karar_sayisi = dogru = 0
    hatalar = []
    for r in rows:
        sonuc = karar(*_ayir(r["mail"]))
        if sonuc:
            karar_sayisi += 1
            if sonuc == r["etiket"]:
                dogru += 1
            else:
                hatalar.append((r["etiket"], sonuc, r["mail"].replace("\n", " | ")[:160]))
    print(f"{path}: {len(rows)} mailin {karar_sayisi} tanesine kural karar verdi "
          f"(%{100 * karar_sayisi / len(rows):.0f}), isabet {dogru}/{karar_sayisi}")
    for gercek, verilen, mail in hatalar[:15]:
        print(f"  HATA gerçek={gercek} kural={verilen}: {mail}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for yol in sys.argv[1:] or ["data_v6/test.jsonl", "data_v6/test_eski.jsonl", "data_v6/test_gercek.jsonl"]:
        _kendi_testi(yol)
