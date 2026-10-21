let running = false;
let esSource = null;
let durduruldu = false;
let analizToplam = 0;

function setStep(num, state, desc) {
    const el = document.getElementById('step' + num);
    el.className = 'step ' + state;
    document.getElementById('step' + num + '-desc').textContent = desc;
}

function resetAll() {
    for (let i = 1; i <= 4; i++) setStep(i, '', 'Bekleniyor...');
    document.getElementById('resultCard').className = 'result-card';
    document.getElementById('waitingText').textContent = '';
    document.getElementById('duzeltBtn').style.display = 'none';
    document.getElementById('progressWrap').style.display = 'none';
    document.getElementById('progressBar').style.width = '0%';
    analizToplam = 0;
}

function gecmisYukle() {
    fetch('/gecmis')
        .then(r => r.json())
        .then(data => {
            const renderTablo = (rows, bodyId, bosMsg) => {
                const tbody = document.getElementById(bodyId);
                if (!rows || rows.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="3" class="bos">${bosMsg}</td></tr>`;
                    return;
                }
                tbody.innerHTML = rows.map(r => `<tr>
                    <td>${r.tarih}</td>
                    <td title="${r.gonderen}">${r.gonderen}</td>
                    <td title="${r.konu}">${r.konu}</td>
                </tr>`).join('');
            };
            renderTablo(data.onemli, 'onemliBody', 'Henüz önemli mail yok.');
            renderTablo(data.onemsiz, 'onemsizBody', 'Henüz önemsiz mail yok.');
        });
}

function istatistikYukle() {
    fetch('/api/istatistik')
        .then(r => r.json())
        .then(data => {
            document.getElementById('istatOnemli').textContent = data.onemli ?? '-';
            document.getElementById('istatOnemsiz').textContent = data.onemsiz ?? '-';
            document.getElementById('istatSonMail').textContent = data.son_tarih ?? '-';
            const logEl = document.getElementById('taramaLogListesi');
            const logCard = document.getElementById('taramaLogCard');
            if (data.tarama_gecmisi && data.tarama_gecmisi.length > 0) {
                logCard.style.display = 'block';
                logEl.innerHTML = [...data.tarama_gecmisi].reverse().map(g =>
                    `<div class="tarama-log-item">
                        <span>${g.tarih}</span>
                        <span class="log-sayi">${g.yeni} yeni mail</span>
                        <span class="${g.durum === 'tamamlandi' ? 'log-tamamlandi' : 'log-durduruldu'}">${g.durum === 'tamamlandi' ? '✓ Tamamlandı' : '⏸ Durduruldu'}</span>
                    </div>`
                ).join('');
            } else {
                logCard.style.display = 'none';
            }
        });
}

function analizBaslat() {
    if (running) return;
    running = true;
    durduruldu = false;
    resetAll();
    document.getElementById('startBtn').disabled = true;
    document.getElementById('continueBtn').style.display = 'none';
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'inline-block';
    document.getElementById('waitingText').textContent = 'Analiz çalışıyor...';

    esSource = new EventSource('/analiz');

    esSource.onmessage = function(e) {
        const data = JSON.parse(e.data);

        if (data.step === 2 && data.state === 'done' && data.toplam_taranacak != null) {
            analizToplam = data.toplam_taranacak;
            if (analizToplam > 0) {
                document.getElementById('progressWrap').style.display = 'block';
                document.getElementById('progressText').textContent = `0 / ${analizToplam} mail`;
                document.getElementById('progressPct').textContent = '0%';
            }
        }

        if (data.step) {
            setStep(data.step, data.state, data.desc);
        }

        if (data.step === 3 && data.current != null && analizToplam > 0) {
            const pct = Math.round((data.current / analizToplam) * 100);
            document.getElementById('progressBar').style.width = pct + '%';
            document.getElementById('progressText').textContent = `${data.current} / ${analizToplam} mail`;
            document.getElementById('progressPct').textContent = pct + '%';
        }

        if (data.type === 'result') {
            const card = document.getElementById('resultCard');
            const karar = data.karar.toUpperCase();
            const isOnemli = karar.includes('ONEMLI') || karar.includes('ÖNEMLİ');
            card.className = 'result-card show ' + (isOnemli ? 'onemli' : 'onemsiz');
            document.getElementById('resultLabel').textContent = isOnemli ? 'ÖNEMLİ' : 'ÖNEMSİZ';
            document.getElementById('mailGonderen').textContent = data.gonderen;
            document.getElementById('mailKonu').textContent = data.konu;
            document.getElementById('mailTarih').textContent = data.tarih || 'Tarih bilgisi yok';
            card.dataset.messageId = data.message_id || '';
            card.dataset.karar = isOnemli ? 'ONEMLI' : 'ONEMSIZ';
            document.getElementById('duzeltBtn').style.display = data.message_id ? 'inline-block' : 'none';
            // Her mail sonucunda tabloyu guncelle
            gecmisYukle();
        }

        if (data.type === 'done' || data.type === 'error') {
            esSource.close();
            esSource = null;
            running = false;
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            if (durduruldu) {
                document.getElementById('continueBtn').style.display = 'inline-block';
                document.getElementById('waitingText').textContent = 'Analiz durduruldu. Kaldığı yerden devam edebilirsin.';
            } else {
                document.getElementById('continueBtn').style.display = 'none';
                if (data.type === 'done') {
                    gecmisYukle();
                    istatistikYukle();
                    bildirimGonder('Analiz Tamamlandı', 'Tüm mailler analiz edildi.');
                }
            }
        }
    };

    esSource.onerror = function() {
        esSource.close();
        esSource = null;
        running = false;
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').style.display = 'none';
        document.getElementById('waitingText').textContent = 'Bağlantı hatası.';
    };
}

function baslat() {
    // Baştan başlat: pozisyonu sıfırla
    fetch('/analiz/sifirla', { method: 'POST' }).then(() => analizBaslat());
}

function devamEt() {
    // Kaldığı yerden devam et: pozisyonu sıfırlama
    analizBaslat();
}

function durdur() {
    if (!running) return;
    durduruldu = true;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('waitingText').textContent = 'Durduruluyor, mevcut mail bitince duracak...';
    fetch('/analiz/durdur', { method: 'POST' });
}

function kararDuzelt() {
    const card = document.getElementById('resultCard');
    const messageId = card.dataset.messageId;
    const mevcutKarar = card.dataset.karar;
    if (!messageId) return;
    const yeniKarar = mevcutKarar === 'ONEMLI' ? 'ONEMSIZ' : 'ONEMLI';
    const btn = document.getElementById('duzeltBtn');
    btn.disabled = true;
    fetch('/api/karar-duzelt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, karar: yeniKarar })
    }).then(r => r.json()).then(res => {
        if (res.hata) { btn.disabled = false; return; }
        card.classList.remove('onemli', 'onemsiz');
        card.classList.add(yeniKarar === 'ONEMLI' ? 'onemli' : 'onemsiz');
        document.getElementById('resultLabel').textContent = (yeniKarar === 'ONEMLI' ? 'ÖNEMLİ' : 'ÖNEMSİZ') + ' ✓';
        card.dataset.karar = yeniKarar;
        btn.textContent = 'Tekrar Değiştir';
        btn.disabled = false;
        // Duzeltmeyi kaydet (AI bir sonraki analizde ogrenecek)
        const bilgi = document.createElement('p');
        bilgi.textContent = '✓ Duzeltme kaydedildi. AI bir dahaki analizde ogrenecek.';
        bilgi.style.cssText = 'color:#4caf88;font-size:0.8rem;text-align:center;margin-top:8px;';
        card.appendChild(bilgi);
        setTimeout(() => bilgi.remove(), 3000);
    });
}

function bildirimIzniAl() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function bildirimGonder(baslik, mesaj) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(baslik, { body: mesaj });
    }
}

// Sayfa açılınca geçmişi ve istatistikleri yükle, bildirim izni iste
gecmisYukle();
istatistikYukle();
bildirimIzniAl();
