function kurallarYukle() {
    fetch('/api/kurallar')
        .then(r => r.json())
        .then(data => {
            const gruplar = { ONEMLI: [], ONEMSIZ: [] };
            data.forEach(k => {
                const g = gruplar[k.karar] || gruplar.ONEMSIZ;
                g.push(k);
            });
            renderGrup(gruplar.ONEMLI, 'onemliKuralListesi', 'Önemli kural yok.');
            renderGrup(gruplar.ONEMSIZ, 'onemsizKuralListesi', 'Önemsiz kural yok.');
        });
}

function renderGrup(kurallar, containerId, bosMsg) {
    const el = document.getElementById(containerId);
    if (kurallar.length === 0) {
        el.innerHTML = `<p class="bos">${bosMsg}</p>`;
        return;
    }
    el.innerHTML = kurallar.map(k => {
        const turLabel = k.tur === 'gonderen' ? 'Gönderen içeriyorsa' : 'Konu içeriyorsa';
        const kararClass = k.karar === 'ONEMLI' ? 'onemli' : 'onemsiz';
        const kararLabel = k.karar === 'ONEMLI' ? '→ ÖNEMLİ' : '→ ÖNEMSİZ';
        return `<div class="kural-item">
            <span class="kural-tur">${turLabel}</span>
            <span class="kural-deger">${k.deger}</span>
            <span class="kural-karar ${kararClass}">${kararLabel}</span>
            <span class="kural-tarih">${k.tarih || ''}</span>
            <button class="sil-btn" onclick="kuralSil(${k.id})">Sil</button>
        </div>`;
    }).join('');
}

function kuralEkle() {
    const tur = document.getElementById('turSelect').value;
    const deger = document.getElementById('degerInput').value.trim();
    const karar = document.getElementById('kararSelect').value;
    const hata = document.getElementById('hataMesaj');

    if (!deger) {
        hata.textContent = 'Lütfen bir değer girin.';
        return;
    }
    hata.textContent = '';

    fetch('/api/kurallar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tur, deger, karar })
    })
    .then(r => r.json())
    .then(res => {
        if (res.hata) { hata.textContent = res.hata; return; }
        document.getElementById('degerInput').value = '';
        kurallarYukle();
    });
}

function kuralSil(id) {
    fetch(`/api/kurallar/${id}`, { method: 'DELETE' })
        .then(() => kurallarYukle());
}

// Enter ile ekle
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('degerInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') kuralEkle();
    });
    kurallarYukle();
});
