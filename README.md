<p align="center"><img src="depoloma/web/icon.png" width="96" alt="Depoloma"></p>

<h1 align="center">Depoloma</h1>

<p align="center"><b>Diskin nereye gitti?</b> · Where did my disk go?</p>

<p align="center"><a href="#türkçe">Türkçe</a> · <a href="#english">English</a></p>

---

## Türkçe

Depoloma bilgisayarını tarar, disk alanının **hangi klasörlere gittiğini** gösterir ve her birinin
**ne olduğunu, sana lazım olup olmadığını ve nasıl güvenle temizleneceğini** sade bir dille anlatır.

> **Depoloma sen onaylamadan hiçbir şeyi silmez.** Tarama yalnızca okur. Güvenli önbellekleri istersen
> işaretleyip onaylayarak toplu temizlersin; oyunlara, projelere, indirilenlere ve geri kalan her şeye yalnızca sen dokunursun.

### Neler gösterir?

- **Genel bakış** — ne kadar boş alan kaldı, alan hangi gruplara gidiyor (kişisel dosyalar, programlar ve
  oyunlar, geliştirici araçları, uygulama verileri, sanal diskler, sistem) ve en çok yer tutan noktalar.
- **Klasörler** — alan haritası (treemap) ve boyuta göre sıralı liste; tıklayarak içine girersin.
- **Öneriler** — bulgular dört sınıfa ayrılır:
  - **Güvenle temizlenebilir**: önbellekler, geçici dosyalar (npm / pip / Gradle önbelleği, tarayıcı önbellekleri…)
  - **Yeniden üretilebilir**: `node_modules`, Python sanal ortamları, derleme çıktıları
  - **Gözden geçir**: eski indirmeler, unutulmuş projeler, oyunlar, emülatörler, telefon yedekleri, yapay zekâ modelleri
  - **Dokunma**: Windows, sayfa dosyası, sürücü deposu gibi gerekli şeyler — neden büyük olduklarını açıklar
- **Toplu temizlik** — "güvenle temizlenebilir" önbellekleri (tarayıcı ve uygulama önbellekleri, npm / pip / uv /
  Gradle / NuGet / Cargo / Go önbellekleri, eski geçici dosyalar…) işaretler, listeyi görür, onaylarsın; Depoloma
  içlerini boşaltır ve ne kadar yer açıldığını raporlar.
- **Unutulmuş projeler** — aylardır dokunmadığın projeleri ve içlerinde kodu kaybetmeden silinebilecek kısmı bulur.
- **Büyük dosyalar**, **kurulu programlar** ve **WSL**: Linux dağıtımının sanal diskinin içine bakar, diskin
  boşa tuttuğu alanı ve nasıl sıkıştırılacağını gösterir.
- Her öğe için: *Nedir? · Sana lazım mı? · Yer açmanın doğru yolu.*
- Türkçe ve İngilizce arayüz, açık ve koyu tema.

### Kurulum

Gereken tek şey **Python 3.8 veya üstü**. Başka paket kurulmaz, derleme adımı yoktur, yönetici yetkisi istemez.

#### Windows

1. Başlat menüsüne **PowerShell** yaz ve aç (yönetici olarak açman gerekmez).
2. Şu satırı yapıştır, Enter'a bas:

   ```powershell
   irm https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.ps1 | iex
   ```

3. Masaüstüne gelen **Depoloma** kısayoluna çift tıkla.

Python yoksa kurulum onu `winget` ile kurmayı teklif eder. Kendin kurmak istersen:

```powershell
winget install -e --id Python.Python.3.12
```

Güncellemek için 2. adımdaki satırı yeniden çalıştır. Kaldırmak için:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\Depoloma\install.ps1" -Uninstall
```

#### Ubuntu / Linux ve macOS

1. Terminali aç (Ubuntu'da `Ctrl+Alt+T`).
2. Şu satırı yapıştır, Enter'a bas:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh
   ```

   `curl` yoksa:

   ```bash
   wget -qO- https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh
   ```

3. Uygulamalar menüsünde **Depoloma**'yı ara ya da terminalde şunu yaz:

   ```bash
   depoloma
   ```

Root yetkisi ve ek paket gerekmez; Ubuntu'daki hazır Python 3 yeterli. Python yoksa: `sudo apt install python3`.
Güncellemek için 2. adımı yeniden çalıştır. Kaldırmak için:

```bash
sh ~/.local/share/depoloma/install.sh --uninstall
```

Ubuntu'da Depoloma şunları tanır: apt / snap / flatpak paketleri ve önbellekleri, `~/.cache` ve `~/.config` altındaki
uygulama önbellekleri, sistem günlükleri, Docker, takas dosyası, Timeshift görüntüleri, Çöp Sepeti. Yalnızca root'un
okuyabildiği klasörleri (ör. `/var/lib/docker`) görmek için uygulamanın gösterdiği `sudo` komutunu kullan.

#### Git ile, kurmadan çalıştırmak (her sistem)

```bash
git clone https://github.com/musakartalengin/depoloma
```

```bash
cd depoloma
```

```bash
python -m depoloma
```

Linux ve macOS'ta son komut `python3 -m depoloma`. Windows'ta `Depoloma.bat` dosyasına çift tıklamak da olur.
Git yoksa GitHub sayfasındaki **Code › Download ZIP** ile indirip aynı klasörde çalıştırabilirsin.

#### pipx / uv ile

```bash
uvx --from git+https://github.com/musakartalengin/depoloma depoloma
```

```bash
pipx install git+https://github.com/musakartalengin/depoloma
```

#### Claude Code ile

Şunu yazman yeter:

> `github.com/musakartalengin/depoloma` deposunu klonla ve çalıştır.

Claude'un analizi senin için okumasını istersen penceresiz rapor modunu kullanabilir:

```bash
python -m depoloma --report
```

### Kullanım

| Komut | Ne yapar |
|---|---|
| `python -m depoloma` | Pencereyi açar (Edge/Chrome varsa uygulama penceresi olarak) |
| `python -m depoloma C:\` | Açar ve hemen taramaya başlar |
| `python -m depoloma --report` | Penceresiz tarar, raporu terminale yazar |
| `python -m depoloma --json sonuc.json` | Tüm analizi JSON olarak kaydeder |
| `python -m depoloma --tab` | Normal tarayıcı sekmesinde açar |

Korumalı sistem klasörlerini de görmek için programı yönetici olarak çalıştırabilirsin
(uygulamadaki "Yönetici olarak yeniden başlat" düğmesi bunu yapar).

### Güvenlik ve gizlilik

- **Tarama salt okunur.** Tarama, raporlar ve komut satırı hiçbir dosyayı silmez, taşımaz, değiştirmez.
- **Silme dar kapsamlı ve onaylıdır.** Silen tek kod [`depoloma/cleaner.py`](depoloma/cleaner.py) dosyasındadır ve:
  - yalnızca kurallarda `clean=True` işaretli, içeriğinin tamamı kendiliğinden yeniden oluşan önbellek klasörlerini boşaltır;
  - yalnızca kendi kullanıcı klasörünün içinde çalışır; Windows'a ait klasörlere dokunmaz;
  - **yapay zekâ araçlarına hiç dokunmaz:** Claude Code, Claude, Codex / ChatGPT, Antigravity, Gemini, Copilot, Cursor
    gibi araçların sohbet geçmişi, oturumları ve çalışma dosyaları (önbellekleri dahil) korunur ve "Dokunma" olarak gösterilir;
  - adına güvenmez: "Cache" adlı bir klasörün içinde tarayıcı profili, veritabanı ya da program kodu varsa, veya klasör
    kurulu bir programın içindeyse onu temizliğe sunmaz;
  - silinecek listeyi sunucu kendisi doğrular, sana gösterir ve yalnızca onayladığın o listeyi çalıştırır;
  - klasörün kendisini bırakır, kısayol ve bağlantıları takip etmez, kullanımdaki dosyaları atlar;
  - geçici dosyalarda son 7 günde dokunulmuş hiçbir şeye el sürmez;
  - son bir haftada kullandığın uygulamaları onay penceresinde ayrıca gösterir ("bu uygulamada yakın zamanda çalıştın")
    ve tek tıkla listeden çıkarmanı sağlar;
  - Geri Dönüşüm Kutusu'nu kullanmaz (yoksa yer açılmaz); bu yüzden onay penceresi geri alınamayacağını açıkça söyler;
  - her temizliği bir metin dosyasına yazar: ne zaman, hangi klasörler, ne kadar yer açıldı, nelere dokunulmadı.
    "Neyi silmiştim?" sorusunun cevabı hep oradadır ("Geçmiş temizlikler" düğmesi). Dosyanın yeri:
    Windows'ta `%LOCALAPPDATA%\Depoloma\cleanup-log.txt`, Ubuntu'da `~/.local/state/depoloma/cleanup-log.txt`,
    macOS'ta `~/Library/Logs/Depoloma/cleanup-log.txt`.
- **Komut satırından silme yoktur.** `--report` ve `--json` yalnızca okur; silmek için birinin pencerede listeyi görüp onaylaması gerekir.
- **Her şey yerelde.** İnternete hiçbir istek gitmez; arayüz yalnızca `127.0.0.1` üzerinde, rastgele bir
  anahtarla korunarak çalışır. Başka siteler veya başka bilgisayarlar verine erişemez.
- **Bağımlılık yok.** Yalnızca Python standart kütüphanesi ve düz HTML/CSS/JavaScript.

### Nasıl çalışır?

- Windows'ta dizinleri tek sistem çağrısıyla yüzlerce kayıt döndüren hızlı bir yöntemle okur
  (2 milyon dosyalı bir disk ≈ yarım dakika).
- Boyutlar **diskte gerçekten kaplanan alandır**: yalnızca bulutta duran OneDrive dosyaları 0 sayılır,
  sıkıştırılmış dosyalar gerçek boyutuyla sayılır, WinSxS'teki sabit bağlantılar bir kez sayılır.
- Disk doluluğu ile taranan toplam arasındaki farkı ("görünmeyen alan": geri yükleme noktaları, korumalı
  klasörler) ayrıca gösterir.

### Yeni bir klasör türü tanıtmak

Tüm bilgi [`depoloma/rules.py`](depoloma/rules.py) dosyasındadır. Bir kural tek bir kayıttır:

```python
R("npm_cache", ["~/AppData/Local/npm-cache", "~/.npm"], "dev", "safe", clean=True,
  tr=("npm önbelleği", "npm'in indirdiği paketlerin önbelleği.",
      "Yalnızca kurulumları hızlandırır.", "npm cache clean --force"),
  en=("npm cache", "Cache of packages npm downloaded.",
      "Only speeds up installs.", "npm cache clean --force"))
```

`clean=True` yalnızca içeriğinin **tamamı** gözden çıkarılabilir olan ve kendiliğinden geri gelen klasörlere verilir
(ayar, kimlik bilgisi, kurulu araç içermeyen). Emin değilsen verme: klasör yine gösterilir, yalnızca elle temizlenir.

Testler: `python -m unittest discover -s tests`

### Sınırlar

- En çok Windows 10/11'de denendi. Ubuntu/Linux tarafı, sahte bir Linux dosya sistemiyle çalışan otomatik testlerle
  (klasör tanıma, gerçek disk boyutu, başka disk bölümlerine girmeme, temizlenebilir klasörler) doğrulanır; depodaki
  GitHub Actions iş akışı aynı testleri gerçek Ubuntu'da da çalıştırır. macOS desteği deneyseldir.
- Yönetici (Linux'ta root) olmadan bazı sistem klasörleri okunamaz; bunlar "görünmeyen alan" olarak raporlanır.
- WSL'in içine bakmak için dağıtımın başlatılabilmesi gerekir.

---

## English

Depoloma scans your computer, shows **which folders your disk space went to**, and explains in plain
language **what each one is, whether you still need it, and the proper way to free it**.

> **Depoloma deletes nothing unless you confirm.** Scanning only reads. Safe caches can be ticked and cleared
> in bulk after you confirm the list; games, projects, downloads and everything else are only ever touched by you.

### What you get

- **Overview** — free space, where the space goes (personal files, programs & games, developer tools,
  app data, virtual disks, system) and the biggest hotspots.
- **Folders** — a treemap plus a size-sorted list you can drill into.
- **Suggestions** in four classes: **safe to clear** (caches, temp files), **can be regenerated**
  (`node_modules`, virtualenvs, build output), **review** (old downloads, forgotten projects, games,
  emulators, phone backups, AI models) and **keep** (Windows, page file… with an explanation of why they are big).
- **Bulk clean-up** of the "safe to clear" caches (browser and app caches, npm / pip / uv / Gradle / NuGet / Cargo /
  Go caches, old temp files…): tick, read the list, confirm — Depoloma empties them and reports what was freed.
- **Forgotten projects**, **large files**, **installed programs** and a look **inside WSL** virtual disks.
- For every item: *What is it? · Do you need it? · The proper way to free it.*
- Turkish and English UI, light and dark theme.

### Install

All you need is **Python 3.8+**: no packages, no build step, no administrator rights.

#### Windows

1. Open **PowerShell** from the Start menu (no need to run it as administrator).
2. Paste this line and press Enter:

   ```powershell
   irm https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.ps1 | iex
   ```

3. Double-click the **Depoloma** shortcut on your desktop.

No Python? The installer offers to install it with `winget`, or do it yourself:

```powershell
winget install -e --id Python.Python.3.12
```

To update, run step 2 again. To remove it:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\Depoloma\install.ps1" -Uninstall
```

#### Ubuntu / Linux and macOS

1. Open a terminal (`Ctrl+Alt+T` on Ubuntu).
2. Paste this line and press Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh
   ```

   No `curl`?

   ```bash
   wget -qO- https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh
   ```

3. Find **Depoloma** in the applications menu, or run:

   ```bash
   depoloma
   ```

No root and no extra packages needed; Ubuntu's stock Python 3 is enough (otherwise `sudo apt install python3`).
To update, run step 2 again. To remove it:

```bash
sh ~/.local/share/depoloma/install.sh --uninstall
```

On Ubuntu it knows apt / snap / flatpak packages and caches, app caches under `~/.cache` and `~/.config`, system logs,
Docker, the swap file, Timeshift snapshots and the Trash.

#### With git, without installing (any system)

```bash
git clone https://github.com/musakartalengin/depoloma
```

```bash
cd depoloma
```

```bash
python -m depoloma
```

On Linux and macOS the last command is `python3 -m depoloma`. On Windows you can also double-click `Depoloma.bat`.
No git? Use **Code › Download ZIP** on the GitHub page and run the same command in the unpacked folder.

#### With pipx / uv

```bash
uvx --from git+https://github.com/musakartalengin/depoloma depoloma
```

```bash
pipx install git+https://github.com/musakartalengin/depoloma
```

### Use

| Command | What it does |
|---|---|
| `python -m depoloma` | Opens the window |
| `python -m depoloma --report` | No window: scans and prints a text report (handy for AI coding agents) |
| `python -m depoloma --json out.json` | Writes the full analysis as JSON |
| `python -m depoloma --tab` | Opens in a normal browser tab |

### Safety and privacy

- **Scanning is read-only.** Scans, reports and the command line never delete, move or modify a file.
- **Deleting is narrow and confirmed.** The only code that deletes is [`depoloma/cleaner.py`](depoloma/cleaner.py). It
  empties only cache folders whose rule is marked `clean=True`, only inside your own user folder, and only the exact
  list the server validated and you confirmed. The folder itself stays, links are never followed, files in use are
  skipped, and in temp folders nothing touched in the last 7 days is removed. It does not use the Recycle Bin
  (that would free nothing), so the confirmation says clearly that it cannot be undone.
- **Every clean-up is logged.** When, which folders, how much was freed and what was left alone go into a plain
  text file ("Past clean-ups" button): `%LOCALAPPDATA%\Depoloma\cleanup-log.txt` on Windows,
  `~/.local/state/depoloma/cleanup-log.txt` on Linux, `~/Library/Logs/Depoloma/cleanup-log.txt` on macOS.
- **AI tools are off limits.** Chat history, sessions and working files of Claude Code, Claude, Codex / ChatGPT,
  Antigravity, Gemini, Copilot, Cursor and the like — caches included — are never offered for cleaning.
- **A name is not enough.** A folder called "Cache" that holds a browser profile, a database or program code, or
  that sits inside an installed program, is not offered. Apps you used in the last week are pointed out in the
  confirmation ("you were working in this recently") and can be left out with one click.
- **No deleting from the command line.** `--report` and `--json` only read; deleting needs a person to see and confirm the list.
- **Local only.** No network requests. The UI is served on `127.0.0.1` and protected by a random token.
- **No dependencies.** Python standard library and plain HTML/CSS/JavaScript.

### Limits

Tested mostly on Windows 10/11. The Ubuntu/Linux side is covered by automated tests that run against a simulated
Linux filesystem; the GitHub Actions workflow in this repo runs the same tests on real Ubuntu. macOS support is experimental. Without administrator (root) rights some
system folders cannot be read — they are reported as "space we cannot see".

### License

[MIT](LICENSE)
