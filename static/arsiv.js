let tumVeri = { onemli: [], onemsiz: [] };
let aktifSekme = 'onemli';

function sekmeGoster(sekme, btn) {
    aktifSekme = sekme;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-onemli').classList.toggle('gizli', sekme !== 'onemli');
    document.getElementById('panel-onemsiz').classList.toggle('gizli', sekme !== 'onemsiz');
    ara();
}

function renderTablo(rows, bodyId, yeniKarara) {
    const tbody = document.getElementById(bodyId);
    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="bos">Kayıt bulunamadı.</td></tr>';
        return;
    }
    const etiket = yeniKarara === 'ONEMLI' ? 'Önemli Yap' : 'Önemsiz Yap';
    tbody.innerHTML = rows.map(r => `
        <tr>
            <td>${r.tarih}</td>
            <td title="${r.gonderen}">${r.gonderen}</td>
            <td title="${r.konu}">${r.konu}</td>
            <td><button class="aksiyon-btn" onclick="kararDegistir('${(r.message_id || '').replace(/'/g, '\\&#39;')}','${yeniKarara}',this)">${etiket}</button></td>
        </tr>
    `).join('');
}

function kararDegistir(messageId, yeniKarar, btn) {
    if (!messageId) return;
    btn.disabled = true;
    btn.textContent = '...';
    fetch('/api/karar-duzelt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, karar: yeniKarar })
    }).then(r => r.json()).then(res => {
        if (res.hata) { btn.textContent = 'Hata!'; return; }
        const row = btn.closest('tr');
        row.style.opacity = '0.3';
        setTimeout(() => { row.remove(); }, 400);
        // Sayaci guncelle
        const sayacId = yeniKarar === 'ONEMLI' ? 'onemsizSayac' : 'onemliSayac';
        const el = document.getElementById(sayacId);
        if (el) el.textContent = Math.max(0, parseInt(el.textContent) - 1);
        const karsiSayacId = yeniKarar === 'ONEMLI' ? 'onemliSayac' : 'onemsizSayac';
        const el2 = document.getElementById(karsiSayacId);
        if (el2) el2.textContent = parseInt(el2.textContent) + 1;
    });
}

function csvExport() {
    const rows = aktifSekme === 'onemli' ? tumVeri.onemli : tumVeri.onemsiz;
    if (!rows || rows.length === 0) { alert('Dışa aktarılacak veri yok.'); return; }
    const baslik = ['Tarih', 'Kimden', 'Konu'];
    const satirlar = rows.map(r => [
        '"' + (r.tarih || '').replace(/"/g, '""') + '"',
        '"' + (r.gonderen || '').replace(/"/g, '""') + '"',
        '"' + (r.konu || '').replace(/"/g, '""') + '"'
    ].join(','));
    const csvIcerik = [baslik.join(','), ...satirlar].join('\n');
    const blob = new Blob(['\uFEFF' + csvIcerik], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = aktifSekme + '_mailler.csv';
    link.click();
}

function ara() {
    const q = document.getElementById('aramaInput').value.toLowerCase();
    const filtrele = (rows) => rows.filter(r =>
        (r.konu || '').toLowerCase().includes(q) ||
        (r.gonderen || '').toLowerCase().includes(q)
    );
    renderTablo(filtrele(tumVeri.onemli), 'onemliBody', 'ONEMSIZ');
    renderTablo(filtrele(tumVeri.onemsiz), 'onemsizBody', 'ONEMLI');
}

fetch('/gecmis')
    .then(r => r.json())
    .then(data => {
        tumVeri = data;
        document.getElementById('onemliSayac').textContent = data.onemli.length;
        document.getElementById('onemsizSayac').textContent = data.onemsiz.length;
        renderTablo(data.onemli, 'onemliBody', 'ONEMSIZ');
        renderTablo(data.onemsiz, 'onemsizBody', 'ONEMLI');
    });
