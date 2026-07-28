# 📰 brief-pagi

**Satu pesan tiap pagi** ke **WhatsApp dan/atau Telegram**: harga TBS & ringkasan
Palm Pulse, cuaca kebun, status banjir/karhutla/udara, kutipan pasar, lalu berita
sawit — diringkas AI (opsional).

> Judul pesan: **📰 BRIEF PAGI — <tanggal>**

## Tiga sumber data

| Bagian pesan | Sumber | Cara ambil |
|---|---|---|
| Harga TBS, ringkasan, **berita sawit** | repo **palm-pulse** | 1 GET ke GitHub Pages (hanya baca) |
| Cuaca, banjir, karhutla, udara | repo **kebun-sawit-cuaca** | 2 GET ke GitHub Pages (hanya baca) |
| Saham/ETF & kurs | internet | Yahoo Finance (+ fallback exchangerate.host) |

Berita **tidak lagi** diambil dari RSS atau Google News. Semua berita sawit
datang dari `stories[]` milik Palm Pulse, jadi tidak ada lagi judul dobel dan
tidak ada lagi feed pihak ketiga yang bisa mati diam-diam.

## Isi pesan

```
📰 BRIEF PAGI — 28 Jul 2026

🧠 Ringkasan:            <- kalau GEMINI_API_KEY diisi

🌴 Harga TBS Riau (2026-07-22 s/d 2026-07-28)
  Plasma: Rp3.640/kg (naik Rp40)
  Swadaya: Rp3.564/kg (turun Rp13)

🧭 Ringkasan Palm Pulse:
• <sampai 4 poin dari master_summary>

🌦️ Cuaca kebun (Rawang Air Putih):
  Gerimis ringan, hujan 0.4 mm (peluang 24%), 24.4–30.8°C
  Angin Tenggara 13.6 km/jam (hembusan 28.4)
  Prakiraan:
    2026-07-29: 5.1 mm, 62%

🌊 Banjir, karhutla & udara:
  Banjir: Normal · debit 272.5 m3/s (turun)
  Karhutla: waspada · titik terdekat 42.1 km selatan
  Udara: AQI 63, Sedang, berkabut tipis

📈 Pasar:
  ▼ VOO (S&P 500): 679.31 (-0.43%)
  💱 USD/IDR: 17.990

📰 Berita sawit (Palm Pulse):
• <judul> — <sumber>

Palm Pulse: https://zurplox.github.io/palm-pulse/
Cuaca kebun: https://zurplox.github.io/kebun-sawit-cuaca/
```

Urutannya sengaja: **angka keputusan dulu** (harga TBS → cuaca → risiko kebun),
baru pasar, baru bacaan.

## Hubungan dengan repo lain

```
palm-pulse (TIDAK DISENTUH)
  -> Pages: data/latest.json --------GET-----\
                                              \
kebun-sawit-cuaca (TIDAK DISENTUH)             >  brief-pagi (repo ini)
  -> Pages: data/cuaca.json      ----GET-----/     fetch_palm.py
            data/lingkungan.json ----GET----/      fetch_cuaca.py
                                                   fetch_markets.py  <- internet
                                                   -> build_brief.py -> notify.py
                                                        -> WhatsApp + Telegram
```

- **Kedua repo sumber tidak pernah diubah.** Repo ini cuma melakukan HTTP GET ke
  halaman yang sudah publik. Tidak ada token tulis, tidak ada langkah yang
  menyentuhnya.
- Bentuk JSON `palm-pulse` juga tidak boleh berubah: aplikasi Android memakai
  adapter Moshi yang ketat, field non-null yang hilang bikin crash.
- **`palm-pulse-telegram` tidak lagi diperlukan.** Repo itu belum pernah
  di-push, dan fungsinya sekarang ada di sini. Kalau kamu tetap memasangnya,
  kamu akan menerima **dua pesan** tiap pagi ke chat yang sama.

## Alur (GitHub Actions)

| Waktu | Workflow | Isi |
|---|---|---|
| 06:52 SGT | **Fetch** | tes offline → `fetch_palm.py` → `fetch_cuaca.py` → `fetch_markets.py` → `build_brief.py` → commit `data/` |
| 08:07 SGT | **Notify** | tes offline → `notify.py` kirim ke WhatsApp + Telegram |

Palm Pulse terbit ~06:51 SGT, jadi fetch 06:52 SGT bisa kepagian; pesan tetap
aman karena feed lama masih dipakai dengan catatan umur. Kalau mau lebih rapat,
geser cron fetch ke `10 23 * * *` UTC (07:10 SGT). Repo cuaca sendiri jalan 3x
sehari, jadi datanya hampir selalu lebih baru dari brief.

Hanya **pustaka standar Python** (tanpa `pip install`).

## Secrets (Settings → Secrets and variables → Actions)

| Secret | Wajib? | Untuk |
|---|---|---|
| `WA_PHONE` | notif WA | nomor WhatsApp tujuan (mis. `628xxxxxxxxxx`) |
| `WA_APIKEY` | notif WA | apikey CallMeBot |
| `TG_TOKEN` | notif TG | token bot dari @BotFather |
| `TG_CHAT_ID` | notif TG | chat id tujuan (@userinfobot; grup = angka **negatif**) |
| `GEMINI_API_KEY` | opsional | ringkasan AI (Google AI Studio, ada **free tier**) |

Alias didukung: `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (nama ala
`palm-pulse-telegram`) dipakai otomatis kalau `TG_TOKEN` / `TG_CHAT_ID` kosong.

**Token bot hanya boleh hidup di GitHub Secret.** Jangan pernah ditulis ke file,
commit, README, log, atau jendela chat. Kalau bocor, langsung `/revoke` di
@BotFather dan tempel penggantinya ke secret.

**CallMeBot:** kirim `I allow callmebot to send me messages` ke **+34 644 51 95 23**, simpan apikey balasannya.
**Gemini gratis:** aistudio.google.com → *Get API key*.

## Setup Telegram (3 menit)

1. Pakai bot yang sudah ada atau buat baru di **@BotFather** → `/newbot`.
2. **Kirim satu pesan apa pun ke bot itu.** Bot tidak boleh memulai percakapan;
   melewati langkah ini menghasilkan `HTTP 400 chat not found`.
3. Ambil chat id dari **@userinfobot**. Untuk grup: masukkan bot ke grup, kirim
   satu pesan, buka `https://api.telegram.org/bot<TOKEN>/getUpdates`, baca
   `chat.id` (**negatif**, jangan buang tanda minus). Untuk channel, bot harus
   jadi admin.
4. Simpan `TG_TOKEN` + `TG_CHAT_ID` sebagai repository secret (tanpa kutip,
   tanpa spasi di ujung).
5. Actions → **Brief Pagi - Fetch** → Run workflow (isi `data/`).
6. Actions → **Brief Pagi - Notify** → Run workflow → `force_send = 1`.
   Sukses terlihat dari baris log `Telegram terkirim (1 bagian, N karakter).`

## Perilaku pengiriman (yang dijamin)

| Situasi | Perilaku |
|---|---|
| Kredensial tidak diisi | dilewati, tidak ada panggilan jaringan, exit 0 |
| Variabel kosong (`""` dari GitHub) | dianggap tidak diisi, bukan nilai valid |
| Pesan > 4096 karakter | dipecah di batas baris, diberi penanda `(1/2)`, URL tidak terpotong |
| Telegram 429 / 5xx / koneksi putus | diulang **satu kali** setelah 5 detik |
| Telegram 4xx (token/chat salah) | **tidak** diulang, dicatat di log |
| WA sukses tapi TG gagal | state per kanal → TG tetap dicoba lagi, WA tidak dobel |
| Feed Palm Pulse mati | pakai `data/palm.json` terakhir; brief tetap terbit |
| Feed cuaca mati | pakai `data/cuaca.json` + `data/lingkungan.json` terakhir |
| Data rusak di `data/*.json` | baris rusak dilewati; seksi hilang kalau tak ada yang layak |
| Feed Palm Pulse > 36 jam / cuaca > 24 jam | tetap dikirim + catatan umur |
| Kegagalan apa pun | log jelas, exit 0, workflow tidak merah |

Catatan teknis:
- Telegram dikirim **tanpa `parse_mode`** (teks polos). Judul berita sering
  memuat `*`, `_`, `[`, `(` yang membuat Markdown/HTML ditolak Telegram.
  Penekanan `*tebal*` gaya WhatsApp otomatis dibersihkan untuk Telegram.
- Respons Telegram tidak pernah dicetak, dan pesan error disaring (`scrub`)
  supaya token tidak muncul di log Actions.
- Harga TBS memakai urutan umur tanaman **5, 6, 4, 9** lalu fallback ke
  `price_rp_per_kg` — sama persis dengan widget Android Palm Pulse.
- Prakiraan cuaca hanya menampilkan hari **ke depan**: entri `kind: "actual"`
  dan tanggal hari ini dibuang.
- Kata `None` tidak pernah dicetak; separator ribuan Indonesia (`Rp3.640`).
- Karena script selalu exit 0, **centang hijau saja tidak membuktikan terkirim** —
  selalu baca baris lognya.
- `data/last_sent.json` **di-commit** (tidak lagi masuk `.gitignore`). Tanpa itu
  runner selalu mulai dari nol dan guard "maks 1x/hari" tidak pernah benar-benar
  berlaku antar-run.
- Semua teks dari feed dirender sebagai **teks**, bukan HTML, di `index.html`,
  dan hanya tautan `http(s)` yang dijadikan link.

## Tes

```
python -m unittest discover -s scripts/tests
```

**112 tes, tanpa jaringan.** Kedua workflow menjalankannya sebelum bekerja.

| Berkas | Cakupan |
|---|---|
| `test_palm.py` (58) | format harga TBS, urutan umur, batas WIB, poin ringkasan, berita `stories[]` + dedupe, data rusak, pasar rusak, pesan gabungan |
| `test_cuaca.py` (23) | baris cuaca hari ini, angin, filter prakiraan (`actual` dibuang), banjir/karhutla/udara, feed rusak & sebagian |
| `test_notify.py` (31) | pemecahan pesan, retry, penyaringan token, guard duplikat per kanal, alias secret, exit 0 |

Beberapa tes mengunci **format lama** (`-2.0%` tetap `-2.0%`, `10.00`,
`16.290`) supaya pengerasan anti-crash tidak diam-diam mengubah tampilan
pesan yang sudah kamu baca tiap pagi.

Setiap tes yang menambal `nt.tg_post`, `nt.time.sleep`, `nt.LAST` atau variabel
lingkungan menyimpan & memulihkannya di `setUp`/`tearDown`. Sudah diverifikasi
jalan **bersama, per kelas, dan terbalik** tanpa kebocoran state.

## Atur di `config.json`
- `palm.feed_url`, `palm.site_url` — sumber Palm Pulse (`palm.enabled: false` untuk mematikan)
- `palm.stale_hours` (36), `palm.max_bullets` (4), `palm.max_stories` (8)
- `cuaca.base_url`, `cuaca.site_url` — sumber kebun-sawit-cuaca (`cuaca.enabled: false` untuk mematikan)
- `cuaca.stale_hours` (24), `cuaca.forecast_days` (3)
- `markets.tickers` — symbol **Yahoo Finance** (default VOO / QQQ / VEU)
- `markets.fx` — pasangan kurs (default USD/SGD, USD/IDR, SGD/IDR)
- `brief_title`, `emoji` — judul & ikon pesan

Env opsional untuk uji lokal: `PALM_FEED_URL`, `CUACA_BASE_URL`.

## Catatan
- **Kurs pakai Yahoo Finance.** Kalau Yahoo error untuk FX, fallback ke exchangerate.host.
- **CPO futures (Bursa Malaysia FCPO) tidak punya API gratis/resmi.** CPO dibahas lewat berita + harga MPOB, bukan feed futures live.
- Jalankan lokal: `python scripts/fetch_palm.py && python scripts/fetch_cuaca.py && python scripts/fetch_markets.py && python scripts/build_brief.py` (butuh internet).
- Cron GitHub Actions bersifat *best-effort*: sering telat 5–20 menit, kadang dilewati. Bukan bug, dan run yang terlewat tidak merusak apa pun.
