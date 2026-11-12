"""Depoloma knowledge base: "what is this folder, and do I still need it?"

Each rule recognises a well-known folder and explains it in plain language:
  title – short name            what – what it is
  why   – why you may need it   how  – the proper way to free the space

Categories (`cat`) feed the "where does my space go" overview:
  system · apps · personal · dev · data · virtual · other
Advice class (`act`):
  safe   – caches / temp files, recreated automatically
  regen  – can be rebuilt with one command (node_modules, virtualenvs…)
  review – yours to judge (downloads, games, backups, old projects)
  keep   – don't touch, the system or an app needs it
  info   – just an explanation

Pattern syntax (case-insensitive, `/` separators):
  `node_modules`              matches that folder name anywhere
  `~/AppData/Local/Temp`      `~` = any user profile folder
  `#/Windows`                 `#` = a drive root (C:\\, D:\\ …) or `/`
  `~/AppData/**/Cache`        `*` = one path part, `**` = any number of parts
The last path part must be a literal name (that is how rules are indexed).

Adding a rule = adding one `R(...)` entry below. Rules label and explain.

Cleaning: a rule marked `clean=True` may be emptied by Depoloma, but only after
the user ticks it and confirms. Give that flag only to a `safe` folder whose
ENTIRE content is disposable and is recreated automatically — no settings, no
credentials, no installed tools, nothing that needs a manual command to return.
When in doubt leave it off: the folder is still shown, with instructions.
"""
from __future__ import annotations

import os
import re
import sys

CATS = ("system", "apps", "personal", "dev", "data", "virtual", "other")
ACTS = ("safe", "regen", "review", "keep", "info")

_RULES = []
_FILE_RULES = []


class Rule(object):
    __slots__ = ("id", "pats", "cat", "act", "text", "os", "has", "regen", "np", "dedupe",
                 "inproj", "home", "child", "hidden", "min", "reclaim", "clean", "keep_days", "nofind",
                 "generic", "guards")

    def __init__(self, rid, pats, cat, act, tr, en, os=None, has=None, np=False, dedupe=False,
                 inproj=False, home=False, child=None, hidden=False, min=0, clean=False, keep_days=0,
                 nofind=False, generic=False, guard=False):
        self.id = rid
        self.pats = pats
        self.cat = cat
        self.act = act
        self.text = {"tr": tr, "en": en}
        self.os = os
        self.has = has                  # folder must contain an entry with this name
        self.regen = act == "regen"     # rebuildable → never counts as "project activity"
        self.reclaim = act in ("safe", "regen")
        self.np = np                    # no project detection below this folder
        self.dedupe = dedupe            # count hard-linked files once below this folder
        self.inproj = inproj            # only matches inside a detected project
        self.home = home
        self.child = child              # rule id given to every direct sub-folder
        self.hidden = hidden            # technical rule, never shown as a finding
        self.min = min                  # minimum total bytes before it becomes a finding
        # clean=True: Depoloma may empty this folder when the user selects and confirms it.
        # Only for `safe` folders whose ENTIRE content is disposable and comes back by itself.
        self.clean = bool(clean) and act == "safe"
        self.keep_days = keep_days      # when cleaning, leave files changed in the last N days alone
        self.nofind = nofind            # labels the folder in the explorer but is never listed as a finding
        # generic=True: matches by folder NAME alone ("anything called Cache"). Such a rule is not
        # trusted on its name: it never applies beneath a guarded folder, and the folder's content
        # must look like a cache (see `looks_like_data`).
        self.generic = generic
        # A guarded folder (every `keep` rule, plus rules marked guard=True: installed programs,
        # AI tools, …) may contain folders that are merely *named* like caches. No generic rule applies inside.
        self.guards = guard or act == "keep"


def R(rid, pats, cat, act, tr=None, en=None, **kw):
    if isinstance(pats, str):
        pats = [pats]
    _RULES.append(Rule(rid, pats, cat, act, tr or ("", "", "", ""), en or ("", "", "", ""), **kw))


def F(rid, cat, act, tr, en, names=(), exts=()):
    _FILE_RULES.append({"id": rid, "cat": cat, "act": act, "text": {"tr": tr, "en": en},
                        "names": tuple(names), "exts": tuple(exts)})


MB = 1 << 20
GB = 1 << 30
PREFIX_KEY = 4              # "prefix*" names are indexed by their first four characters

# ═════════════════════════════════════════════════════════════════════════════
#  Windows — system
# ═════════════════════════════════════════════════════════════════════════════
R("windows", "#/Windows", "system", "keep", os="win", np=True, dedupe=True,
  tr=("Windows", "İşletim sisteminin kendisi.",
      "Bilgisayarın açılması ve çalışması için şart. Elle hiçbir şey silme.",
      "Yer açmak için: Ayarlar › Sistem › Depolama › Temizleme önerileri (veya Disk Temizleme › Sistem dosyalarını temizle)."),
  en=("Windows", "The operating system itself.",
      "Required for the computer to boot and run. Never delete anything here by hand.",
      "To trim it: Settings › System › Storage › Cleanup recommendations (or Disk Cleanup › Clean up system files)."))
R("winsxs", "#/Windows/WinSxS", "system", "keep", os="win",
  tr=("Windows bileşen deposu (WinSxS)", "Windows güncellemelerinin ve sistem bileşenlerinin yedek kopyaları.",
      "Güncelleme kaldırma ve sistem onarımı için gerekli. Dosyaların çoğu System32 ile ortak (sabit bağlantı), bu yüzden burada yalnızca ek yükü gösteriyoruz.",
      "Yönetici terminalinde: Dism /Online /Cleanup-Image /StartComponentCleanup"),
  en=("Windows component store (WinSxS)", "Backup copies of Windows updates and system components.",
      "Needed to uninstall updates and repair the system. Most files are hard-linked with System32, so only the extra cost is shown here.",
      "In an admin terminal: Dism /Online /Cleanup-Image /StartComponentCleanup"))
R("win_installer", "#/Windows/Installer", "system", "keep", os="win",
  tr=("Windows Installer önbelleği", "Kurulu programların .msi/.msp kurulum kayıtları.",
      "Programları onarmak, güncellemek ve kaldırmak için gerekli. Silersen programlar kaldırılamaz hâle gelir.",
      "Elle dokunma. Kullanmadığın programları Ayarlar › Uygulamalar'dan kaldırınca küçülür."),
  en=("Windows Installer cache", "The .msi/.msp records of installed programs.",
      "Needed to repair, update and uninstall programs. Deleting it breaks uninstallers.",
      "Don't touch. It shrinks when you uninstall programs from Settings › Apps."))
R("win_update_dl", "#/Windows/SoftwareDistribution/Download", "system", "safe", os="win",
  tr=("Windows Update indirmeleri", "İndirilmiş güncelleme paketleri.",
      "Güncelleme kurulduktan sonra gerekmez; Windows gerekirse yeniden indirir.",
      "Disk Temizleme › Sistem dosyalarını temizle › “Windows Update Temizleme”."),
  en=("Windows Update downloads", "Downloaded update packages.",
      "Not needed once updates are installed; Windows re-downloads if necessary.",
      "Disk Cleanup › Clean up system files › “Windows Update Cleanup”."))
R("win_delivery", ["#/Windows/ServiceProfiles/NetworkService/AppData/Local/Microsoft/Windows/DeliveryOptimization",
                   "#/Windows/SoftwareDistribution/DeliveryOptimization"], "system", "safe", os="win",
  tr=("Teslim İyileştirme önbelleği", "Güncellemeleri diğer bilgisayarlarla paylaşmak için tutulan kopyalar.",
      "Senin için bir işlevi yok; Windows kendisi de zamanla temizler.",
      "Disk Temizleme › “Teslim İyileştirme Dosyaları”."),
  en=("Delivery Optimization cache", "Copies of updates kept to share with other PCs.",
      "No use to you; Windows also clears it over time.",
      "Disk Cleanup › “Delivery Optimization Files”."))
R("win_temp", "#/Windows/Temp", "system", "safe", os="win",
  tr=("Windows geçici dosyaları", "Sistemin ve kurulum programlarının bıraktığı geçici dosyalar.",
      "Açık programların kullandıkları dışında gerekmez.", "Ayarlar › Sistem › Depolama › Geçici dosyalar."),
  en=("Windows temp files", "Temporary files left by the system and installers.",
      "Not needed, except what running programs hold open.", "Settings › System › Storage › Temporary files."))
R("win_logs", ["#/Windows/Logs", "#/Windows/Panther", "#/Windows/LiveKernelReports", "#/Windows/Minidump",
               "#/ProgramData/Microsoft/Windows/WER"], "system", "safe", os="win",
  tr=("Windows günlükleri ve hata dökümleri", "Güncelleme günlükleri, çökme raporları ve bellek dökümleri.",
      "Yalnızca bir sorunu araştırıyorsan işe yarar.", "Disk Temizleme › “Sistem hata bellek döküm dosyaları” ve “Windows günlük dosyaları”."),
  en=("Windows logs and crash dumps", "Update logs, crash reports and memory dumps.",
      "Only useful while you are debugging a problem.", "Disk Cleanup › “System error memory dump files” and “Windows log files”."))
R("win_old", ["#/Windows.old", "#/$WINDOWS.~BT", "#/$Windows.~WS", "#/$GetCurrent", "#/$SysReset",
              "#/Windows10Upgrade", "#/ESD"], "system", "safe", os="win", np=True,
  tr=("Eski Windows kurulumu kalıntıları", "Sürüm yükseltmesinden veya sıfırlamadan kalan eski sistem dosyaları.",
      "Yalnızca önceki Windows sürümüne geri dönmek istersen gerekir.",
      "Ayarlar › Sistem › Depolama › Geçici dosyalar › “Önceki Windows yüklemeleri”."),
  en=("Old Windows installation leftovers", "Old system files left by an upgrade or reset.",
      "Only needed if you want to roll back to the previous Windows version.",
      "Settings › System › Storage › Temporary files › “Previous Windows installation(s)”."))
R("recycle", "#/$Recycle.Bin", "system", "safe", os="win", np=True,
  tr=("Geri Dönüşüm Kutusu", "Sildiğin ama henüz kalıcı olarak silinmemiş dosyalar.",
      "Yanlışlıkla sildiğin bir şeyi geri almak istemiyorsan gerekmez.", "Masaüstünde Geri Dönüşüm Kutusu › sağ tık › Boşalt."),
  en=("Recycle Bin", "Files you deleted that are not permanently gone yet.",
      "Not needed unless you want to restore something.", "Right-click the Recycle Bin on the desktop › Empty."))
R("sysvol", "#/System Volume Information", "system", "keep", os="win", np=True,
  tr=("Sistem geri yükleme noktaları", "Sistem Geri Yükleme ve gölge kopyaların tutulduğu korumalı klasör.",
      "Bir güncelleme veya sürücü sistemi bozarsa geri dönmeni sağlar.",
      "Denetim Masası › Sistem › Sistem Koruması › Yapılandır: ayrılan alanı küçült veya eski noktaları sil."),
  en=("System restore points", "Protected folder holding System Restore points and shadow copies.",
      "Lets you roll back if an update or driver breaks the system.",
      "Control Panel › System › System Protection › Configure: reduce the reserved space or delete old points."))
R("recovery", ["#/Recovery", "#/system.sav"], "system", "keep", os="win", np=True,
  tr=("Kurtarma ortamı", "Windows açılmadığında kullanılan kurtarma araçları.",
      "Sistem bozulursa onarım için gerekir.", ""),
  en=("Recovery environment", "Recovery tools used when Windows cannot start.",
      "Needed to repair a broken system.", ""))
R("driverstore", "#/Windows/System32/DriverStore", "system", "keep", os="win",
  tr=("Sürücü deposu", "Kurulmuş tüm aygıt sürücülerinin paketleri (eski ekran kartı sürücüleri burada birikir).",
      "Aygıtların çalışması ve yeniden takıldığında tanınması için gerekli.",
      "Disk Temizleme › Sistem dosyalarını temizle › “Aygıt sürücü paketleri”."),
  en=("Driver store", "Packages of every installed device driver (old GPU drivers pile up here).",
      "Needed for devices to work and to be recognised when re-plugged.",
      "Disk Cleanup › Clean up system files › “Device driver packages”."))
R("gpu_installers", ["#/NVIDIA", "#/AMD", "#/Intel", "#/SWSetup", "#/Drivers", "#/MSOCache",
                     "#/ProgramData/NVIDIA Corporation/Downloader", "#/ProgramData/NVIDIA Corporation/NVIDIA app/UpdateFramework"],
  "system", "safe", os="win", np=True,
  tr=("Sürücü / kurulum kalıntıları", "Sürücü ve Office kurulumlarının açılmış kurulum dosyaları.",
      "Kurulum bittikten sonra gerekmez; gerekirse yeniden indirilir.", "Klasörü silebilirsin."),
  en=("Driver / setup leftovers", "Unpacked setup files of driver and Office installers.",
      "Not needed after installation; can be downloaded again.", "The folder can be deleted."))

# ── Windows — programs ───────────────────────────────────────────────────────
R("programfiles", ["#/Program Files", "#/Program Files (x86)"], "apps", "info", os="win", np=True, child="program",
  tr=("Kurulu programlar", "Bilgisayara kurulmuş programların dosyaları.",
      "Kullandığın programlar burada yaşar. Kullanmadıklarını kaldırarak yer açabilirsin.",
      "Klasörü silme; Ayarlar › Uygulamalar › Yüklü uygulamalar'dan kaldır."),
  en=("Installed programs", "Files of the programs installed on this PC.",
      "The programs you use live here. Uninstall the ones you don't to reclaim space.",
      "Don't delete folders; uninstall from Settings › Apps › Installed apps."))
R("program", [], "apps", "review", os="win",
  tr=("Kurulu program", "Bilgisayara kurulmuş bir program.",
      "Hâlâ kullanıyor musun? Kullanmıyorsan kaldırmak en temiz yoldur.",
      "Ayarlar › Uygulamalar › Yüklü uygulamalar › Kaldır."),
  en=("Installed program", "A program installed on this PC.",
      "Do you still use it? If not, uninstalling is the clean way.",
      "Settings › Apps › Installed apps › Uninstall."))
R("winget_packages", "~/AppData/Local/Microsoft/WinGet/Packages", "apps", "info", os="win", np=True, guard=True, nofind=True,
  tr=("WinGet ile kurulan programlar", "winget ile yalnızca senin hesabına kurulmuş taşınabilir programlar.",
      "Kullandığın komut satırı araçları burada durur.", "Kaldırmak için: winget uninstall AD"),
  en=("Programs installed with WinGet", "Portable programs winget installed for your account only.",
      "The command-line tools you use live here.", "To remove: winget uninstall NAME"))
R("user_programs", "~/AppData/Local/Programs", "apps", "info", os="win", child="program", guard=True,
  tr=("Kullanıcıya kurulu programlar", "Yalnızca senin hesabına kurulmuş programlar (VS Code, Python, Discord…).",
      "Kullandığın programlar burada.", "Ayarlar › Uygulamalar › Yüklü uygulamalar'dan kaldır."),
  en=("Per-user programs", "Programs installed only for your account (VS Code, Python, Discord…).",
      "The programs you use live here.", "Uninstall from Settings › Apps › Installed apps."))
R("windowsapps", "#/Program Files/WindowsApps", "apps", "keep", os="win",
  tr=("Microsoft Store uygulamaları", "Store'dan kurulan uygulamalar ve oyunlar.",
      "Kullandığın Store uygulamaları burada. Klasörü elle silme.", "Ayarlar › Uygulamalar'dan kullanmadıklarını kaldır."),
  en=("Microsoft Store apps", "Apps and games installed from the Store.",
      "Your Store apps live here. Never delete by hand.", "Uninstall unused ones from Settings › Apps."))
R("programdata", "#/ProgramData", "data", "info", os="win", np=True,
  tr=("Program verileri (ProgramData)", "Programların tüm kullanıcılar için tuttuğu ortak veriler.",
      "Programların ayarları, lisansları ve önbellekleri. İçindeki büyük klasörlere tek tek bak.", ""),
  en=("Program data (ProgramData)", "Shared data that programs keep for all users.",
      "Settings, licences and caches of programs. Check the large sub-folders individually.", ""))
R("package_cache", ["#/ProgramData/Package Cache", "~/AppData/Local/Package Cache"], "apps", "keep", os="win",
  tr=("Kurulum paketi önbelleği", "Visual Studio, .NET, C++ Redistributable gibi kurulumların sakladığı paketler.",
      "Bu programları onarmak, güncellemek ve kaldırmak için gerekir.", "Dokunma; ilgili programı kaldırınca gider."),
  en=("Installer package cache", "Packages kept by installers such as Visual Studio, .NET and C++ redistributables.",
      "Needed to repair, update and uninstall those programs.", "Leave it; it goes away when you uninstall the program."))
R("defender", "#/ProgramData/Microsoft/Windows Defender", "system", "keep", os="win",
  tr=("Windows Defender", "Virüs tanımları ve tarama geçmişi.", "Bilgisayarının korunması için gerekli.", ""),
  en=("Windows Defender", "Virus definitions and scan history.", "Needed to keep the PC protected.", ""))
R("search_index", "#/ProgramData/Microsoft/Search", "system", "info", os="win",
  tr=("Windows arama dizini", "Başlat menüsü ve Dosya Gezgini aramasını hızlandıran dizin.",
      "Silinirse arama yavaşlar ve dizin baştan oluşturulur.", "Ayarlar › Gizlilik ve güvenlik › Windows'da arama › Gelişmiş › Yeniden oluştur."),
  en=("Windows search index", "The index that makes Start menu and Explorer search fast.",
      "If removed, search gets slow until the index is rebuilt.", "Settings › Privacy & security › Searching Windows › Advanced › Rebuild."))

# ── Windows — user profile ───────────────────────────────────────────────────
R("users", ["#/Users", "/home"], None, "info", child="home",
  tr=("Kullanıcılar", "Her kullanıcının kişisel klasörü.", "", ""),
  en=("Users", "Each user's personal folder.", "", ""))
R("home", ["/root"], "personal", "info", home=True,
  tr=("Kullanıcı klasörü", "Belgelerin, indirdiklerin, masaüstün ve programlarının sana özel verileri.",
      "Tamamen sana ait. İçindeki büyük klasörleri tek tek incele.", ""),
  en=("User folder", "Your documents, downloads, desktop and the per-user data of your programs.",
      "It is all yours. Inspect the large folders one by one.", ""))
R("downloads", ["~/Downloads", "~/İndirilenler", "~/OneDrive/Downloads"], "personal", "review",
  tr=("İndirilenler", "İnternetten indirdiğin her şey.",
      "En çok unutulan klasör: kurulum dosyaları (.exe, .msi, .zip, .iso) kurduktan sonra bir daha gerekmez.",
      "Tarihe ve boyuta göre sırala; eski kurulum dosyalarını ve arşivleri sil."),
  en=("Downloads", "Everything you downloaded from the internet.",
      "The most forgotten folder: installers (.exe, .msi, .zip, .iso) are not needed again once installed.",
      "Sort by date and size; delete old installers and archives."))
R("desktop", ["~/Desktop", "~/Masaüstü", "~/OneDrive/Desktop", "~/OneDrive/Masaüstü"], "personal", "info",
  tr=("Masaüstü", "Masaüstündeki dosya ve klasörlerin.", "Kişisel dosyaların; büyük ve eski olanlara göz at.", ""),
  en=("Desktop", "The files and folders on your desktop.", "Your personal files; look at the large, old ones.", ""))
R("documents", ["~/Documents", "~/Belgeler", "~/OneDrive/Documents", "~/OneDrive/Belgeler"], "personal", "info",
  tr=("Belgeler", "Belgelerin ve birçok programın kayıt klasörü.",
      "Kişisel dosyaların. Bıraktığın eski projeler ve oyun kayıtları burada yer kaplıyor olabilir.", ""),
  en=("Documents", "Your documents and the save folder of many programs.",
      "Your personal files. Abandoned projects and game saves may be hiding here.", ""))
R("pictures", ["~/Pictures", "~/Resimler", "~/OneDrive/Pictures", "~/OneDrive/Resimler"], "personal", "info",
  tr=("Resimler", "Fotoğrafların ve ekran görüntülerin.",
      "Anıların — silmeden önce yedeği olduğundan emin ol. Yer için harici diske veya buluta taşıyabilirsin.", ""),
  en=("Pictures", "Your photos and screenshots.",
      "Your memories — make sure a backup exists before deleting. Move them to an external disk or the cloud to save space.", ""))
R("videos", ["~/Videos", "~/Videolar", "~/Movies"], "personal", "info",
  tr=("Videolar", "Videoların ve ekran kayıtların.",
      "Videolar çok yer kaplar; izlediklerini silmek veya harici diske taşımak en hızlı kazançtır.", ""),
  en=("Videos", "Your videos and screen recordings.",
      "Video is heavy; deleting watched ones or moving them to an external disk is the quickest win.", ""))
R("music", ["~/Music", "~/Müzik"], "personal", "info",
  tr=("Müzik", "Müzik dosyaların.", "Kişisel dosyaların.", ""),
  en=("Music", "Your music files.", "Your personal files.", ""))
R("onedrive", ["~/OneDrive", "~/Dropbox", "~/Google Drive", "~/iCloudDrive"], "personal", "info",
  tr=("Bulut klasörü", "Bulutla eşitlenen dosyaların bilgisayardaki kopyası.",
      "Dosyalar bulutta da duruyor; bilgisayarda yer kaplaması şart değil.",
      "Klasöre sağ tık › “Alan boşalt”: dosya bulutta kalır, diskten kalkar."),
  en=("Cloud folder", "The local copy of files synced with the cloud.",
      "The files also live in the cloud; they don't have to take local space.",
      "Right-click the folder › “Free up space”: the file stays in the cloud, leaves the disk."))
R("appdata", "~/AppData", "data", "info", os="win", np=True,
  tr=("Uygulama verileri (AppData)", "Programların sana özel ayarları, verileri ve önbellekleri.",
      "Gizli bir klasördür; çoğu zaman diskin en büyük sürpriz kaynağıdır. İçindeki bulgulara tek tek bak.", ""),
  en=("Application data (AppData)", "Per-user settings, data and caches of your programs.",
      "A hidden folder and usually the biggest surprise on the disk. Check its findings one by one.", ""))
R("user_temp", "~/AppData/Local/Temp", "data", "safe", os="win", clean=True, keep_days=7,
  tr=("Geçici dosyalar", "Programların çalışırken oluşturup bıraktığı geçici dosyalar.",
      "Kapalı programlar için gerekmez; açık olanlar hâlâ kullanıyor olabilir. Bu yüzden Depoloma yalnızca bir haftadır dokunulmamış olanları siler.",
      "Ayarlar › Sistem › Depolama › Geçici dosyalar (veya Win+R › %temp% › hepsini sil, silinmeyenleri atla)."),
  en=("Temporary files", "Temp files programs created and left behind.",
      "Not needed by closed programs; running ones may still use theirs. That is why Depoloma only removes what has been untouched for a week.",
      "Settings › System › Storage › Temporary files (or Win+R › %temp% › delete all, skip the locked ones)."))
R("inet_cache", ["~/AppData/Local/Microsoft/Windows/INetCache", "~/AppData/Local/Microsoft/Windows/Explorer",
                 "~/AppData/Local/Microsoft/Windows/WebCache", "~/AppData/Local/Microsoft/Windows/Caches"], "data", "safe", os="win",
  tr=("Windows önbellekleri", "Küçük resim (thumbnail) ve internet önbelleği.",
      "Yeniden oluşturulur; silmek yalnızca ilk açılışları biraz yavaşlatır.", "Disk Temizleme › “Küçük resimler” ve “Geçici İnternet Dosyaları”."),
  en=("Windows caches", "Thumbnail and internet caches.",
      "They are rebuilt; clearing only makes the first opens a bit slower.", "Disk Cleanup › “Thumbnails” and “Temporary Internet Files”."))
R("crash_dumps", ["~/AppData/Local/CrashDumps", "~/AppData/Local/Microsoft/Windows/WER"], "data", "safe", os="win", clean=True,
  tr=("Çökme dökümleri", "Çöken programların bıraktığı hata dökümleri.",
      "Yalnızca hatayı geliştiriciye bildirecekse işe yarar.", "Klasörün içini silebilirsin."),
  en=("Crash dumps", "Dumps left by crashed programs.",
      "Only useful if you report the crash to a developer.", "The contents can be deleted."))
R("shader_cache", ["~/AppData/Local/D3DSCache", "~/AppData/Local/NVIDIA/DXCache", "~/AppData/Local/NVIDIA/GLCache",
                   "~/AppData/LocalLow/NVIDIA/PerDriverVersion/DXCache", "~/AppData/Local/AMD/DxCache",
                   "~/AppData/Local/AMD/DxcCache", "~/AppData/Local/AMD/VkCache", "steamapps/shadercache"],
  "data", "safe", clean=True,
  tr=("Ekran kartı gölgelendirici önbelleği", "Oyunların derlenmiş gölgelendiricileri (shader).",
      "Silinirse oyunlar ilk açılışta yeniden derler; kısa süreli takılma olabilir.", "Disk Temizleme › “DirectX Gölgelendirici Önbelleği”."),
  en=("GPU shader cache", "Compiled shaders of your games.",
      "If cleared, games recompile on next launch; brief stutter is possible.", "Disk Cleanup › “DirectX Shader Cache”."))
R("store_data", "~/AppData/Local/Packages", "data", "info", os="win", child="store_app",
  tr=("Store uygulaması verileri", "Microsoft Store uygulamalarının (WhatsApp, Fotoğraflar, WSL…) verileri.",
      "Her alt klasör bir uygulamaya ait. Büyük olanın hangi uygulama olduğuna adından bakabilirsin.", ""),
  en=("Store app data", "Data of Microsoft Store apps (WhatsApp, Photos, WSL…).",
      "Each sub-folder belongs to one app; the name tells you which.", ""))
R("store_app", [], "data", "review", os="win",
  tr=("Store uygulaması verisi", "Bir Microsoft Store uygulamasının verileri ve önbelleği.",
      "Uygulamayı kullanıyorsan verileri burada. Kullanmıyorsan uygulamayı kaldırmak verisini de siler.",
      "Ayarlar › Uygulamalar › ilgili uygulama › Gelişmiş seçenekler › Sıfırla / Kaldır."),
  en=("Store app data", "Data and cache of one Microsoft Store app.",
      "If you use the app, its data lives here. If not, uninstalling removes the data too.",
      "Settings › Apps › the app › Advanced options › Reset / Uninstall."))
R("app_cache", ["~/AppData/**/Cache", "~/AppData/**/Code Cache", "~/AppData/**/GPUCache", "~/AppData/**/CacheStorage",
                "~/AppData/**/cache2", "~/AppData/**/DawnCache", "~/AppData/**/DawnWebGPUCache", "~/AppData/**/DawnGraphiteCache",
                "~/AppData/**/GrShaderCache", "~/AppData/**/ShaderCache", "~/AppData/**/CachedData", "~/AppData/**/Crashpad",
                "~/AppData/**/component_crx_cache", "~/AppData/**/CachedExtensionVSIXs", "~/AppData/**/Caches",
                "~/AppData/**/SquirrelTemp", "~/AppData/**/blob_storage",
                # Linux: Electron / Chromium apps keep their caches under ~/.config/<app>/
                "~/.config/**/Cache", "~/.config/**/Code Cache", "~/.config/**/GPUCache", "~/.config/**/CacheStorage",
                "~/.config/**/DawnCache", "~/.config/**/DawnWebGPUCache", "~/.config/**/DawnGraphiteCache",
                "~/.config/**/GrShaderCache", "~/.config/**/ShaderCache", "~/.config/**/CachedData",
                "~/.config/**/CachedExtensionVSIXs", "~/.config/**/Crashpad", "~/.config/**/component_crx_cache",
                "~/.config/**/blob_storage",
                # Linux: each snap and each flatpak app has a cache folder of its own
                "~/snap/*/common/.cache", "~/snap/*/*/.cache", "~/.var/app/*/cache",
                # Linux: well-known entries of the shared ~/.cache folder
                "~/.cache/google-chrome", "~/.cache/chromium", "~/.cache/mozilla", "~/.cache/BraveSoftware",
                "~/.cache/microsoft-edge", "~/.cache/vivaldi", "~/.cache/opera", "~/.cache/thumbnails", "~/.thumbnails",
                "~/.cache/mesa_shader_cache", "~/.cache/mesa_shader_cache_db", "~/.cache/nvidia", "~/.cache/fontconfig",
                "~/.cache/gstreamer-1.0", "~/.cache/typescript",
                "~/.cache/node-gyp", "~/.cache/electron", "~/.cache/ccache", "~/.cache/sccache"],
  "data", "safe", min=100 * MB, clean=True, generic=True,
  tr=("Uygulama önbellekleri", "Tarayıcıların ve masaüstü uygulamalarının (Chrome, Edge, Discord, VS Code, Teams…) önbellekleri.",
      "Silinirse uygulamalar yeniden oluşturur; yalnızca ilk açılış biraz yavaşlar. Oturumların ve ayarların etkilenmez.",
      "Önce ilgili uygulamayı kapat (açıkken dosyalar kilitlidir), sonra buradan işaretleyip temizle. Tarayıcıda Ctrl+Shift+Delete de aynı işi görür."),
  en=("Application caches", "Caches of browsers and desktop apps (Chrome, Edge, Discord, VS Code, Teams…).",
      "Apps rebuild them; only the first launch is slower. Logins and settings are not affected.",
      "Close the app first (its files are locked while it runs), then tick it here and clean. In browsers, Ctrl+Shift+Delete does the same."))
# Folders that are *named* like a cache but hold things that do not come back by themselves.
# A longer, anchored pattern wins over the generic one above, so these are never offered for cleaning.
R("not_a_cache", [
    # LibreOffice / OpenOffice: installed extensions
    "~/AppData/**/uno_packages/cache", "~/.config/**/uno_packages/cache",
    "~/Library/Application Support/**/uno_packages/cache",
    # a "cache" folder that is really a whole embedded-browser profile (logins, local storage)
    "~/AppData/Local/CapCut/User Data/CEF/Cache", "~/AppData/**/Kingsoft/**/cef/*/cache",
    "~/AppData/**/Kingsoft/office6/cache",               # WPS Office working files; not confirmed to be disposable
    # IDE file-system caches: clearing them by hand loses Local History
    "~/AppData/Local/Google/AndroidStudio*/caches", "~/AppData/Local/JetBrains/*/caches",
    # Windows sign-in tokens and system stores that only look like caches
    "~/AppData/Local/Microsoft/TokenBroker/Cache", "~/AppData/Local/Packages/*/AC/TokenBroker/Cache",
    "~/AppData/Local/Microsoft/Identity/Cache", "~/AppData/Local/Microsoft/Olk/cache",
    "~/AppData/Local/Microsoft/Internet Explorer/CacheStorage", "~/AppData/Local/Packages/*/AppData/CacheStorage",
    # OneNote keeps edits that are not synced yet in its "cache"
    "~/AppData/Local/Microsoft/OneNote/*/cache", "~/AppData/Local/Packages/Microsoft.Office.OneNote_*/**/cache",
], None, "info", hidden=True)
R("capcut_data", "~/AppData/Local/CapCut/User Data/Cache", "data", "review", os="win",
  tr=("CapCut çalışma verileri", "CapCut'ın indirdiği efektler, müzikler, şablonlar ve yapay zekâ çıktıları. Klasörün adı “Cache” olsa da taslakların bu dosyalara bağlıdır.",
      "Taslaklarını yeniden açacaksan gerekli: silinirse efekt ve müzikler eksik görünebilir. CapCut'ı artık kullanmıyorsan büyük bir alandır.",
      "CapCut › Ayarlar › Önbelleği temizle: uygulama hangi dosyaların güvenle silinebileceğini bilir. Klasörü elle boşaltma."),
  en=("CapCut working data", "Effects, music, templates and AI output CapCut downloaded. The folder is called “Cache”, but your drafts depend on these files.",
      "Needed if you will reopen your drafts: effects and music may go missing otherwise. A lot of space if you no longer use CapCut.",
      "CapCut › Settings › Clear cache: the app knows what is safe to remove. Don't empty the folder by hand."))
R("shared_cache", ["~/.cache", "~/Library/Caches"], "data", "info", np=True, child="cache_entry", nofind=True,
  tr=("Ortak önbellek klasörü", "Uygulamaların ve komut satırı araçlarının ortak kullandığı önbellek klasörü; her alt klasör bir araca aittir.",
      "Çoğu yeniden indirilir ya da yeniden oluşturulur. Tanınan önbellekler ayrı bulgular olarak listelenir.",
      "Topluca silme; içindeki bulgulara tek tek bak."),
  en=("Shared cache folder", "The cache folder apps and command-line tools share; each sub-folder belongs to one tool.",
      "Most of it is re-downloaded or rebuilt. Caches Depoloma recognises are listed as separate findings.",
      "Don't wipe it wholesale; look at the findings inside one by one."))
R("cache_entry", [], "data", "safe", min=100 * MB,
  tr=("Diğer araç önbellekleri", "Ortak önbellek klasöründe duran, Depoloma'nın tek tek tanımadığı araçlara ait klasörler.",
      "Genellikle yeniden indirilir ya da yeniden oluşturulur; ama bazı araçlar buraya çalışma dosyalarını da koyar (ör. Claude, Codex). Bu yüzden Depoloma bunları kendisi silmez.",
      "Klasör adından hangi araca ait olduğuna bak; aracı kapatıp klasörü elle silebilirsin."),
  en=("Other tool caches", "Folders in the shared cache folder that belong to tools Depoloma does not know individually.",
      "Usually re-downloaded or rebuilt; but some tools also keep working files here (e.g. Claude, Codex). That is why Depoloma does not delete these itself.",
      "The folder name tells you which tool owns it; close the tool and delete the folder by hand."))
R("browser_profile", ["~/AppData/Local/Google/Chrome/User Data", "~/AppData/Local/Microsoft/Edge/User Data",
                      "~/AppData/Local/BraveSoftware/Brave-Browser/User Data", "~/AppData/Roaming/Opera Software",
                      "~/AppData/Roaming/Mozilla/Firefox/Profiles", "~/AppData/Local/Mozilla/Firefox/Profiles",
                      "~/AppData/Local/Vivaldi/User Data", "~/AppData/Local/Yandex/YandexBrowser/User Data",
                      "~/.mozilla", "~/.thunderbird", "~/.config/google-chrome", "~/.config/chromium",
                      "~/.config/BraveSoftware", "~/.config/microsoft-edge", "~/.config/vivaldi", "~/.config/opera",
                      "~/snap/firefox/common/.mozilla", "~/snap/chromium/common/chromium",
                      "~/snap/thunderbird/common/.thunderbird"],
  "data", "info",
  tr=("Tarayıcı profili", "Tarayıcının geçmişi, uzantıları, oturumları ve önbelleği.",
      "Yer imlerin, kayıtlı oturumların ve uzantıların burada — klasörü silme. Yalnızca önbellek kısmı güvenle temizlenir.",
      "Tarayıcıda Ctrl+Shift+Delete › yalnızca “Önbelleğe alınan resimler ve dosyalar”."),
  en=("Browser profile", "The browser's history, extensions, sessions and cache.",
      "Your bookmarks, logins and extensions live here — don't delete the folder. Only the cache part is safe to clear.",
      "In the browser: Ctrl+Shift+Delete › only “Cached images and files”."))
R("vscode_data", ["~/AppData/Roaming/Code", "~/AppData/Roaming/Code - Insiders", "~/AppData/Roaming/VSCodium",
                  "~/.config/Code", "~/.config/Code - Insiders", "~/.config/VSCodium"], "dev", "info",
  tr=("Kod editörü verileri", "VS Code ayarları, çalışma alanı verileri, dosya geçmişi ve önbellekleri.",
      "Ayarların, yerel dosya geçmişin ve Copilot sohbetlerin burada durur (User klasörü). Bunlar silinirse geri gelmez.",
      "Yalnızca önbellek kısmı güvenle temizlenir (ayrı bir bulgu olarak listelenir); “User” klasörüne dokunma."),
  en=("Code editor data", "VS Code settings, workspace data, file history and caches.",
      "Your settings, local file history and Copilot chats live here (the User folder). They do not come back if deleted.",
      "Only the cache part is safe to clear (listed as a separate finding); leave the “User” folder alone."))
R("vscode_ext", ["~/.vscode/extensions", "~/.cursor/extensions", "~/.vscode-insiders/extensions", "~/.windsurf/extensions",
                 "~/.antigravity/extensions", "~/.antigravity-ide/extensions"],
  "dev", "info", guard=True,
  tr=("Editör eklentileri", "VS Code / Cursor eklentileri.", "Kullandığın eklentiler. Eski sürümler de burada kalabilir.",
      "Editörde kullanmadığın eklentileri kaldır."),
  en=("Editor extensions", "VS Code / Cursor extensions.", "The extensions you use; old versions can linger here.",
      "Uninstall unused extensions from the editor."))
# ── AI coding tools: their "data" is your working context. Depoloma never cleans inside these. ──
R("ai_context", [
    "~/.claude", "~/.codex", "~/.gemini", "~/.cline", "~/.copilot", "~/.cursor", "~/.codeium", "~/.continue",
    "~/.aider", "~/.kimi-code", "~/.local/share/opencode", "~/.config/opencode",
    "~/AppData/Local/Temp/claude",                       # Claude Code scratchpads of sessions that can still be resumed
    # VS Code and its forks (Cursor, Windsurf, Antigravity…): chats, checkpoints, local file history
    "~/AppData/Roaming/*/User/globalStorage", "~/AppData/Roaming/*/User/workspaceStorage", "~/AppData/Roaming/*/User/History",
    "~/.config/*/User/globalStorage", "~/.config/*/User/workspaceStorage", "~/.config/*/User/History",
    "~/Library/Application Support/*/User/globalStorage", "~/Library/Application Support/*/User/workspaceStorage",
    "~/Library/Application Support/*/User/History",
    "~/AppData/Roaming/Code/agentSessionData", "~/.config/Code/agentSessionData",
    "~/.vscode-server/data", "~/.cursor-server/data", "~/.windsurf-server/data"],
  "dev", "keep", np=True,
  tr=("Yapay zekâ aracı geçmişi ve bağlamı", "Claude Code, Codex, Antigravity, Gemini, Copilot, Cursor gibi araçların sohbet geçmişi, oturumları, hafızası ve çalışma dosyaları.",
      "Yarım kalan işlerine dönmeni ve aracın seni hatırlamasını sağlayan bağlam burada durur; silinirse geri gelmez. Depoloma bu klasörlere hiç dokunmaz.",
      "Yer açmak istersen eski oturumları aracın kendi içinden sil; klasörü elle boşaltma."),
  en=("AI tool history and context", "Chat history, sessions, memory and working files of tools such as Claude Code, Codex, Antigravity, Gemini, Copilot, Cursor.",
      "The context that lets you resume unfinished work and lets the tool remember you lives here; it does not come back if deleted. Depoloma never touches these folders.",
      "To free space, delete old sessions from inside the tool itself; don't empty the folder by hand."))
R("ai_app", [
    "~/AppData/Roaming/Claude", "~/AppData/Local/AnthropicClaude", "~/AppData/Local/Claude", "~/.config/Claude",
    "~/AppData/Local/claude-cli-nodejs", "~/.cache/claude-cli-nodejs", "~/.local/share/claude", "~/.cache/claude",
    "~/.cache/codex-runtimes", "~/AppData/Roaming/Codex", "~/.config/Codex",
    "~/AppData/Local/Packages/OpenAI.*", "~/AppData/Local/Packages/Claude_*", "~/AppData/Local/Packages/Anthropic*",
    "~/AppData/Roaming/Antigravity", "~/AppData/Roaming/Antigravity IDE", "~/.config/Antigravity",
    "~/.antigravity", "~/.antigravity-ide",
    "~/AppData/Roaming/Cursor", "~/.config/Cursor", "~/AppData/Roaming/Windsurf", "~/.config/Windsurf", "~/.windsurf",
    "~/Library/Application Support/Claude", "~/Library/Application Support/Cursor",
    "~/Library/Application Support/Windsurf", "~/Library/Application Support/Antigravity"],
  "data", "keep", np=True,
  tr=("Yapay zekâ uygulaması verileri", "Claude, Codex / ChatGPT, Antigravity, Cursor gibi yapay zekâ uygulamalarının verileri: oturumlar, giriş bilgileri, yerel çalışma ortamları ve önbellekler.",
      "Bu uygulamalarda bağlamın ve yarım kalan işlerin durur. İçlerindeki önbellekler zararsız olsa bile Depoloma bu klasörlerde hiçbir şeyi temizlemeye sunmaz.",
      "Yer açmak için uygulamanın kendi ayarlarını kullan; büyük alt klasörlere (ör. sanal makine imajları, eski çalışma zamanı kopyaları) tek tek bak."),
  en=("AI app data", "Data of AI apps such as Claude, Codex / ChatGPT, Antigravity, Cursor: sessions, sign-in, local workspaces and caches.",
      "Your context and unfinished work live in these apps. Even though the caches inside are harmless, Depoloma offers nothing in these folders for cleaning.",
      "Use the app's own settings to free space; look at large sub-folders (e.g. VM images, old runtime copies) one by one."))
R("chat_apps", ["~/AppData/Roaming/discord", "~/AppData/Roaming/Slack", "~/AppData/Local/Microsoft/Teams",
                "~/AppData/Roaming/Microsoft/Teams", "~/AppData/Roaming/Zoom", "~/AppData/Roaming/Signal",
                "~/AppData/Roaming/Telegram Desktop", "~/AppData/Roaming/WhatsApp", "~/AppData/Roaming/Element",
                "~/.config/discord", "~/.config/Slack", "~/.config/Signal", "~/.config/Element", "~/.zoom",
                "~/.local/share/TelegramDesktop"],
  "data", "info",
  tr=("Sohbet uygulaması verileri", "Discord, Slack, Teams, Telegram, Zoom gibi uygulamaların verileri ve medya önbelleği.",
      "Oturumun burada. Büyüklüğün çoğu genellikle indirilen medya ve önbellektir.",
      "Telegram: Ayarlar › Gelişmiş › Yerel depolamayı yönet. Diğerleri: uygulamayı kapatıp Cache klasörünü sil."),
  en=("Chat app data", "Data and media cache of apps such as Discord, Slack, Teams, Telegram, Zoom.",
      "Your session lives here. Most of the size is usually downloaded media and cache.",
      "Telegram: Settings › Advanced › Manage local storage. Others: close the app and delete its Cache folder."))
R("spotify", ["~/AppData/Local/Spotify", "~/AppData/Local/Packages/SpotifyAB.SpotifyMusic_zpdnekdrzrea0/LocalCache"], "data", "safe", os="win",
  tr=("Spotify önbelleği", "Dinlediğin şarkıların önbelleği ve çevrimdışı indirmeler.",
      "Silinirse şarkılar yeniden yayınlanır; çevrimdışı indirdiklerin yeniden indirilir.", "Spotify › Ayarlar › Depolama › Önbelleği temizle."),
  en=("Spotify cache", "Cache of played songs and offline downloads.",
      "If cleared, songs stream again; offline downloads are re-downloaded.", "Spotify › Settings › Storage › Clear cache."))
R("phone_backup", ["~/AppData/Roaming/Apple Computer/MobileSync/Backup", "~/Apple/MobileSync/Backup",
                   "~/Library/Application Support/MobileSync/Backup"], "personal", "review",
  tr=("iPhone / iPad yedekleri", "iTunes veya Apple Devices ile alınmış telefon yedekleri.",
      "Çoğu zaman unutulur ve onlarca GB tutar. Telefonun iCloud'a yedekleniyorsa ya da eski bir cihaza aitse gerekmez.",
      "iTunes / Apple Devices › Tercihler › Aygıtlar › yedeği seç › Sil."),
  en=("iPhone / iPad backups", "Phone backups made with iTunes or Apple Devices.",
      "Often forgotten and tens of GB. Not needed if the phone backs up to iCloud or the device is long gone.",
      "iTunes / Apple Devices › Preferences › Devices › select the backup › Delete."))
R("outlook", "~/AppData/Local/Microsoft/Outlook", "data", "keep", os="win",
  tr=("Outlook posta dosyaları", "E-postalarının bilgisayardaki kopyası (.ost / .pst).",
      "Outlook kullanıyorsan gerekli. .pst dosyaları tek kopya olabilir — silmeden önce emin ol.",
      "Outlook › Hesap Ayarları › “Çevrimdışı tutulacak posta” süresini kısalt."),
  en=("Outlook mail files", "Local copy of your e-mail (.ost / .pst).",
      "Needed if you use Outlook. .pst files may be the only copy — be sure before deleting.",
      "Outlook › Account Settings › shorten “Mail to keep offline”."))
R("adobe_cache", ["~/AppData/Roaming/Adobe/Common/Media Cache Files", "~/AppData/Roaming/Adobe/Common/Media Cache",
                  "~/AppData/Roaming/Adobe/Common/Peak Files"], "data", "safe", clean=True,
  tr=("Adobe medya önbelleği", "Premiere / After Effects'in oluşturduğu önizleme ve ses önbelleği.",
      "Silinirse projeyi açınca yeniden oluşturulur.", "Premiere › Tercihler › Medya Önbelleği › Sil."),
  en=("Adobe media cache", "Preview and audio caches created by Premiere / After Effects.",
      "Recreated when you reopen a project.", "Premiere › Preferences › Media Cache › Delete."))

# ═════════════════════════════════════════════════════════════════════════════
#  Developer tools (all platforms)
# ═════════════════════════════════════════════════════════════════════════════
R("node_modules", "node_modules", "dev", "regen", min=100 * MB,
  tr=("node_modules klasörleri", "JavaScript projelerinin indirilen bağımlılıkları.",
      "Yalnızca o proje üzerinde çalışırken gerekir. Bıraktığın projelerde boşuna yer tutar.",
      "Klasörü sil; projeye dönersen “npm install” (veya pnpm/yarn install) hepsini geri getirir."),
  en=("node_modules folders", "Downloaded dependencies of JavaScript projects.",
      "Only needed while you work on that project. In abandoned projects it is dead weight.",
      "Delete the folder; “npm install” (or pnpm/yarn install) brings everything back."))
R("py_venv", [".venv", "venv", "env", ".env", "virtualenv", ".virtualenv"], "dev", "regen", has="pyvenv.cfg", min=100 * MB,
  tr=("Python sanal ortamları", "Bir projeye özel Python paketleri (venv).",
      "Proje üzerinde çalışırken gerekir. Bıraktığın projede boşuna durur.",
      "Klasörü sil; gerekirse “python -m venv .venv” ve “pip install -r requirements.txt” ile yeniden kurulur."),
  en=("Python virtual environments", "Python packages installed for one project (venv).",
      "Needed while you work on the project; dead weight in an abandoned one.",
      "Delete the folder; recreate with “python -m venv .venv” and “pip install -r requirements.txt”."))
R("py_cache", ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".ipynb_checkpoints"],
  "dev", "regen", inproj=True, min=100 * MB,
  tr=("Python önbellekleri", "Derlenmiş bayt kodu ve test/lint araçlarının önbellekleri.",
      "Python gerektiğinde kendisi yeniden oluşturur.", "Güvenle silinebilir."),
  en=("Python caches", "Compiled bytecode and caches of test/lint tools.",
      "Python recreates them on demand.", "Safe to delete."))
R("rust_target", "target", "dev", "regen", has="CACHEDIR.TAG", min=100 * MB,
  tr=("Rust derleme çıktıları (target)", "Cargo'nun derleme sonuçları; proje başına GB'ları bulabilir.",
      "Yalnızca derleme süresini kısaltır.", "Proje klasöründe “cargo clean”."),
  en=("Rust build output (target)", "Cargo build artefacts; can reach GBs per project.",
      "Only saves compile time.", "Run “cargo clean” in the project."))
R("js_build_cache", [".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".angular", ".expo", ".docusaurus",
                     ".astro", ".vite", ".webpack", ".cache-loader", "storybook-static", ".dart_tool", ".gradle",
                     "DerivedData", "Pods", ".terraform"], "dev", "regen", inproj=True, min=100 * MB,
  tr=("Derleme önbellekleri", "Next.js, Nuxt, Gradle, Xcode, Flutter gibi araçların proje içi önbellek ve çıktıları.",
      "Bir sonraki derlemede yeniden oluşur.", "Klasörü silebilirsin; ilk derleme biraz uzun sürer."),
  en=("Build caches", "In-project caches and outputs of tools like Next.js, Nuxt, Gradle, Xcode, Flutter.",
      "Recreated by the next build.", "The folder can be deleted; the first build takes a bit longer."))
R("build_output", ["dist", "build", "out", "obj", "Intermediate", "DerivedDataCache", "cmake-build-debug",
                   "cmake-build-release"], "dev", "regen", inproj=True, min=200 * MB,
  tr=("Derleme çıktıları", "Projelerin içindeki derlenmiş çıktı klasörleri (dist, build, out, obj…).",
      "Kaynak koddan yeniden üretilir. Dikkat: elle koyduğun bir dosya varsa önce kontrol et.",
      "Projenin temizleme komutu (npm run clean, gradlew clean, dotnet clean…) veya klasörü silmek."),
  en=("Build outputs", "Compiled output folders inside projects (dist, build, out, obj…).",
      "Regenerated from source. Careful: check first if you ever put files there by hand.",
      "The project's clean command (npm run clean, gradlew clean, dotnet clean…) or delete the folder."))
R("unity_library", "Library", "dev", "regen", has="PackageCache", min=200 * MB,
  tr=("Unity Library önbelleği", "Unity'nin içe aktarılmış varlık önbelleği.",
      "Projeyi açınca yeniden oluşturulur (uzun sürebilir).", "Proje kapalıyken Library klasörünü sil."),
  en=("Unity Library cache", "Unity's imported asset cache.",
      "Rebuilt when the project is opened (can take a while).", "Delete the Library folder while the project is closed."))
R("git_dir", ".git", "dev", "info", np=True, min=500 * MB,
  tr=("Git geçmişi (.git)", "Projenin tüm sürüm geçmişi.",
      "Silersen geçmişi ve commit'lenmemiş dalları kaybedersin. Uzak depoda (GitHub) yedeği yoksa dokunma.",
      "Küçültmek için proje klasöründe “git gc --aggressive --prune=now”."),
  en=("Git history (.git)", "The project's entire version history.",
      "Deleting it loses history and unpushed branches. Don't touch unless it is backed up on a remote.",
      "To shrink: “git gc --aggressive --prune=now” in the project."))
R("site_packages", ["site-packages", "dist-packages"], None, "info", np=True, hidden=True, guard=True)   # program code
R("pnpm_virtual", ".pnpm", None, "info", np=True, dedupe=True, hidden=True)

R("npm_cache", ["~/AppData/Local/npm-cache", "~/.npm", "~/AppData/Roaming/npm-cache"], "dev", "safe", clean=True,
  tr=("npm önbelleği", "npm'in indirdiği paketlerin önbelleği.",
      "Yalnızca kurulumları hızlandırır; paketler gerektiğinde yeniden indirilir.", "npm cache clean --force"),
  en=("npm cache", "Cache of packages npm downloaded.",
      "Only speeds up installs; packages are re-downloaded when needed.", "npm cache clean --force"))
R("yarn_cache", ["~/AppData/Local/Yarn/Cache", "~/.cache/yarn", "~/.yarn/berry/cache", "~/Library/Caches/Yarn"], "dev", "safe", clean=True,
  tr=("Yarn önbelleği", "Yarn'ın indirdiği paketlerin önbelleği.", "Yalnızca kurulumları hızlandırır.", "yarn cache clean"),
  en=("Yarn cache", "Cache of packages Yarn downloaded.", "Only speeds up installs.", "yarn cache clean"))
R("pnpm_store", ["~/AppData/Local/pnpm/store", "~/.pnpm-store", "~/.local/share/pnpm/store", "~/Library/pnpm/store",
                 "#/.pnpm-store"], "dev", "safe", dedupe=True,
  tr=("pnpm deposu", "pnpm'in tüm projelerle paylaştığı paket deposu.",
      "Projelerindeki node_modules bu depoya bağlıdır; kullanılmayan paketler güvenle budanır.", "pnpm store prune"),
  en=("pnpm store", "The package store pnpm shares between all projects.",
      "Your projects' node_modules link into it; unused packages can be pruned safely.", "pnpm store prune"))
R("bun_cache", "~/.bun/install/cache", "dev", "safe", clean=True,
  tr=("Bun önbelleği", "Bun'ın indirdiği paketler.", "Gerektiğinde yeniden indirilir.", "bun pm cache rm"),
  en=("Bun cache", "Packages downloaded by Bun.", "Re-downloaded on demand.", "bun pm cache rm"))
R("deno_cache", ["~/AppData/Local/deno", "~/.cache/deno", "~/Library/Caches/deno"], "dev", "safe",
  tr=("Deno önbelleği", "Deno'nun indirdiği modüller ve derleme önbelleği; ayrıca programlarının Deno KV ve localStorage verileri (location_data).",
      "Modüller yeniden iner; ama “location_data” içindeki uygulama verisi geri gelmez. Bu yüzden Depoloma bu klasörü kendisi boşaltmaz.",
      "Yalnızca “deps”, “npm” ve “gen” alt klasörlerini sil; “location_data” klasörüne dokunma."),
  en=("Deno cache", "Modules Deno downloaded and its compile cache; also your programs' Deno KV and localStorage data (location_data).",
      "Modules download again; the app data in “location_data” does not. That is why Depoloma does not empty this folder itself.",
      "Delete only the “deps”, “npm” and “gen” sub-folders; leave “location_data” alone."))
R("pip_cache", ["~/AppData/Local/pip/cache", "~/.cache/pip", "~/Library/Caches/pip"], "dev", "safe", clean=True,
  tr=("pip önbelleği", "pip'in indirdiği Python paketlerinin önbelleği.",
      "Yalnızca kurulumları hızlandırır.", "pip cache purge"),
  en=("pip cache", "Cache of Python packages pip downloaded.", "Only speeds up installs.", "pip cache purge"))
R("uv_cache", ["~/AppData/Local/uv/cache", "~/.cache/uv", "~/Library/Caches/uv"], "dev", "safe", clean=True,
  tr=("uv önbelleği", "uv'nin indirdiği Python paketleri.", "Yalnızca kurulumları hızlandırır.", "uv cache clean"),
  en=("uv cache", "Python packages downloaded by uv.", "Only speeds up installs.", "uv cache clean"))
R("poetry_cache", ["~/AppData/Local/pypoetry/Cache", "~/.cache/pypoetry", "~/Library/Caches/pypoetry",
                   "~/AppData/Local/pdm/Cache"], "dev", "regen",
  tr=("Poetry / PDM önbelleği ve sanal ortamları", "Poetry'nin indirdiği paketler ve projelerin için kurduğu sanal ortamlar.",
      "Paketler yeniden iner; ama sanal ortamları her projede yeniden kurman gerekir.",
      "poetry cache clear --all .  ·  ortamlar için proje klasöründe: poetry env remove --all, sonra poetry install"),
  en=("Poetry / PDM cache and virtualenvs", "Packages Poetry downloaded and the virtualenvs it built for your projects.",
      "Packages download again; the virtualenvs must be rebuilt per project.",
      "poetry cache clear --all .  ·  for environments, in the project: poetry env remove --all, then poetry install"))
R("conda", ["~/anaconda3", "~/miniconda3", "~/miniforge3", "~/mambaforge", "#/ProgramData/anaconda3",
            "#/ProgramData/miniconda3", "#/anaconda3", "#/miniconda3", "~/.conda"], "dev", "info", np=True,
  tr=("Anaconda / Miniconda", "Conda Python dağıtımı, ortamları ve paket önbelleği.",
      "Veri bilimi / yapay zekâ projeleri için kullanıyorsan gerekli. “envs” altındaki eski ortamlar ve “pkgs” önbelleği büyür.",
      "conda clean --all  ·  kullanmadığın ortam için: conda env remove -n ORTAM"),
  en=("Anaconda / Miniconda", "The Conda Python distribution, its environments and package cache.",
      "Needed if you use it for data-science / AI work. Old environments under “envs” and the “pkgs” cache grow.",
      "conda clean --all  ·  for an unused environment: conda env remove -n NAME"))
R("python_install", ["~/AppData/Local/Programs/Python", "#/Python27", "#/Python38", "#/Python39", "#/Python310",
                     "#/Python311", "#/Python312", "#/Python313", "~/.pyenv", "~/AppData/Roaming/Python",
                     "~/.local/lib"], "dev", "keep", np=True,
  tr=("Python", "Python yorumlayıcısı ve kurulu paketleri.",
      "Yazılım geliştiriyorsan veya Python ile çalışan bir araç kullanıyorsan gerekli; pek çok proje buna dayanır.",
      "Birden fazla sürüm varsa kullanmadıklarını Ayarlar › Uygulamalar'dan kaldırabilirsin."),
  en=("Python", "The Python interpreter and its installed packages.",
      "Needed if you develop software or use tools that run on Python; many projects depend on it.",
      "If several versions are installed, uninstall the unused ones from Settings › Apps."))
R("node_install", ["#/Program Files/nodejs", "~/AppData/Roaming/npm", "~/AppData/Roaming/nvm", "~/.nvm",
                   "~/AppData/Local/fnm_multishells", "~/AppData/Roaming/fnm", "~/.volta", "~/AppData/Local/Volta"],
  "dev", "keep", np=True,
  tr=("Node.js ve global paketler", "Node.js çalışma zamanı, sürüm yöneticileri ve global npm paketleri.",
      "JavaScript projeleri ve Claude Code gibi birçok komut satırı aracı için gerekli.",
      "nvm kullanıyorsan: “nvm list” ile bak, kullanmadığın sürümü “nvm uninstall SÜRÜM” ile kaldır."),
  en=("Node.js and global packages", "The Node.js runtime, version managers and global npm packages.",
      "Needed for JavaScript projects and many CLI tools such as Claude Code.",
      "With nvm: check “nvm list”, remove unused versions with “nvm uninstall VERSION”."))
R("gradle_cache", ["~/.gradle/caches", "~/.gradle/wrapper/dists"], "dev", "safe", np=True, clean=True,
  tr=("Gradle önbelleği", "Java / Android derlemelerinin indirdiği kütüphaneler ve Gradle sürümleri.",
      "Bir sonraki derlemede gerekenler yeniden indirilir; ilk derleme uzun sürer ve internet ister.",
      "Android Studio ve çalışan derlemeler kapalıyken temizle. Ayar dosyaların (gradle.properties) bu klasörlerin dışındadır, etkilenmez."),
  en=("Gradle cache", "Libraries and Gradle versions downloaded by Java / Android builds.",
      "The next build re-downloads what it needs; the first build is slow and needs internet.",
      "Clean while Android Studio and running builds are closed. Your settings (gradle.properties) live outside these folders and are untouched."))
R("maven_repo", ["~/.m2/repository", "~/.ivy2/cache"], "dev", "safe", np=True,
  tr=("Maven yerel deposu", "Maven'in indirdiği kütüphaneler; ayrıca “mvn install” ile kendi kurduğun paketler.",
      "İndirilenler yeniden iner; ama kendi kurduğun, hiçbir yerde yayınlanmamış paketler geri gelmez. Bu yüzden Depoloma bunu kendisi boşaltmaz.",
      "Kullanmadığın grup klasörlerini elle sil ya da: mvn dependency:purge-local-repository"),
  en=("Maven local repository", "Libraries Maven downloaded; also packages you installed yourself with “mvn install”.",
      "Downloads come back; packages you installed yourself and never published do not. That is why Depoloma does not empty it itself.",
      "Delete group folders you no longer use by hand, or: mvn dependency:purge-local-repository"))
R("gradle_home", ["~/.gradle", "~/.m2", "~/.ivy2", "~/.sbt"], "dev", "info", np=True,
  tr=("Gradle / Maven kullanıcı klasörü", "Java derleme araçlarının ayarları (gradle.properties, settings.xml) ve indirdikleri önbellek.",
      "Ayar ve kimlik bilgileri burada durur; klasörün tamamını silme. Büyüklüğün neredeyse tamamı içindeki önbellektir.",
      "Yalnızca içindeki önbellek klasörlerini temizle (ayrı bir bulgu olarak listelenir)."),
  en=("Gradle / Maven user folder", "Settings of Java build tools (gradle.properties, settings.xml) and the cache they download.",
      "Settings and credentials live here; don't delete the whole folder. Nearly all of the size is the cache inside.",
      "Clean only the cache folders inside (listed as a separate finding)."))
R("nuget_cache", ["~/.nuget/packages", "~/AppData/Local/NuGet"], "dev", "safe", np=True, clean=True,
  tr=("NuGet önbelleği", ".NET projelerinin indirdiği paketler.", "Gerektiğinde yeniden indirilir.", "dotnet nuget locals all --clear"),
  en=("NuGet cache", "Packages downloaded by .NET projects.", "Re-downloaded on demand.", "dotnet nuget locals all --clear"))
R("cargo_cache", ["~/.cargo/registry", "~/.cargo/git"], "dev", "safe", np=True, clean=True,
  tr=("Cargo önbelleği", "Rust paketlerinin (crate) indirilen kaynakları.", "Gerektiğinde yeniden indirilir.", "Klasörü sil veya “cargo cache -a” (cargo-cache)."),
  en=("Cargo cache", "Downloaded sources of Rust crates.", "Re-downloaded on demand.", "Delete the folder or run “cargo cache -a” (cargo-cache)."))
R("rust_toolchains", ["~/.rustup", "~/.cargo"], "dev", "keep", np=True,
  tr=("Rust araç zinciri", "Rust derleyicisi, araçları ve kurulu komutlar.",
      "Rust ile geliştirme yapıyorsan gerekli.", "rustup toolchain list  ·  kullanmadığını: rustup toolchain uninstall AD"),
  en=("Rust toolchain", "The Rust compiler, tools and installed binaries.",
      "Needed if you develop in Rust.", "rustup toolchain list  ·  remove unused: rustup toolchain uninstall NAME"))
R("go_cache", ["~/go/pkg/mod", "~/AppData/Local/go-build", "~/.cache/go-build", "~/Library/Caches/go-build"], "dev", "safe",
  np=True, clean=True,
  tr=("Go önbelleği", "Go modülleri ve derleme önbelleği.", "Gerektiğinde yeniden indirilir / derlenir.", "go clean -modcache  ·  go clean -cache"),
  en=("Go cache", "Go modules and build cache.", "Re-downloaded / rebuilt on demand.", "go clean -modcache  ·  go clean -cache"))
R("android_sdk", ["~/AppData/Local/Android/Sdk", "~/Android/Sdk", "~/Library/Android/sdk"], "dev", "info", np=True,
  tr=("Android SDK", "Android geliştirme araçları, platformlar ve emülatör sistem imajları.",
      "Android uygulaması geliştiriyorsan gerekli. Eski platformlar ve sistem imajları çok yer tutar.",
      "Android Studio › SDK Manager'dan kullanmadığın platformları ve sistem imajlarını kaldır."),
  en=("Android SDK", "Android development tools, platforms and emulator system images.",
      "Needed for Android development. Old platforms and system images are heavy.",
      "Android Studio › SDK Manager: remove platforms and system images you don't use."))
R("android_avd", "~/.android/avd", "virtual", "review", np=True,
  tr=("Android emülatörleri (AVD)", "Android Studio sanal cihazları; her biri birkaç GB.",
      "Hâlâ test ettiğin cihazlar mı? Eski sanal cihazlar unutulup kalır.", "Android Studio › Device Manager › cihazı sil."),
  en=("Android emulators (AVD)", "Android Studio virtual devices; several GB each.",
      "Do you still test on these? Old virtual devices get forgotten.", "Android Studio › Device Manager › delete the device."))
R("flutter_sdk", "flutter", "dev", "keep", has="flutter_console.bat", np=True,
  tr=("Flutter SDK", "Flutter geliştirme kiti ve indirdiği araçlar.",
      "Flutter ile uygulama geliştiriyorsan gerekli.", "İçindeki “bin/cache” silinirse ilk komutta yeniden indirilir."),
  en=("Flutter SDK", "The Flutter development kit and the tools it downloads.",
      "Needed if you build apps with Flutter.", "Its “bin/cache” is re-downloaded on first use if removed."))
R("flutter_cache", ["~/AppData/Local/Pub/Cache", "~/.pub-cache"], "dev", "safe", np=True,
  tr=("Dart / Flutter paket önbelleği", "Flutter projelerinin indirdiği paketler.", "Gerektiğinde yeniden indirilir.", "flutter pub cache clean"),
  en=("Dart / Flutter package cache", "Packages downloaded by Flutter projects.", "Re-downloaded on demand.", "flutter pub cache clean"))
R("test_browsers", ["~/AppData/Local/ms-playwright", "~/.cache/ms-playwright", "~/Library/Caches/ms-playwright",
                    "~/.cache/puppeteer", "~/AppData/Local/Cypress/Cache", "~/.cache/Cypress", "~/AppData/Local/electron/Cache",
                    "~/AppData/Local/node-gyp/Cache", "~/AppData/Local/electron-builder/Cache"], "dev", "safe", np=True,
  tr=("Test tarayıcıları ve araç indirmeleri", "Playwright, Puppeteer, Cypress ve Electron'un indirdiği tarayıcılar ve ikili dosyalar.",
      "Test çalıştırırken gerekir. Silersen yeniden indirilir, ama Playwright ve Cypress için bunu bir komutla senin başlatman gerekir.",
      "npx playwright uninstall --all  ·  geri getirmek için: npx playwright install"),
  en=("Test browsers and tool downloads", "Browsers and binaries downloaded by Playwright, Puppeteer, Cypress and Electron.",
      "Needed when running tests. They can be downloaded again, but for Playwright and Cypress you have to start that with a command.",
      "npx playwright uninstall --all  ·  to restore: npx playwright install"))
R("jetbrains", ["~/AppData/Local/JetBrains", "~/Library/Caches/JetBrains", "~/.cache/JetBrains"], "dev", "info", np=True,
  tr=("JetBrains IDE verileri", "IntelliJ, PyCharm gibi IDE'lerin indeks ve önbellekleri; Toolbox ile kurduysan IDE'lerin kendisi de buradadır.",
      "Önbellek kısmı silinirse IDE projeyi yeniden indeksler. Kaldırdığın eski IDE sürümlerinin klasörleri burada kalabilir.",
      "IDE › File › Invalidate Caches. Artık kullanmadığın sürümlerin klasörlerini elle silebilirsin; “Toolbox” klasörüne dokunma."),
  en=("JetBrains IDE data", "Indexes and caches of IDEs such as IntelliJ and PyCharm; if installed through Toolbox, the IDEs themselves live here too.",
      "The IDE re-indexes if its cache is removed. Folders of old, uninstalled IDE versions may linger here.",
      "IDE › File › Invalidate Caches. Folders of versions you no longer use can be deleted by hand; leave “Toolbox” alone."))
R("visual_studio", ["#/Program Files/Microsoft Visual Studio", "#/Program Files (x86)/Microsoft Visual Studio",
                    "#/Program Files (x86)/Windows Kits", "#/Program Files (x86)/Microsoft SDKs",
                    "#/ProgramData/Microsoft/VisualStudio"], "dev", "info", os="win", np=True,
  tr=("Visual Studio ve Windows SDK", "Visual Studio, derleme araçları ve Windows geliştirme kitleri.",
      "C++/.NET geliştiriyorsan veya bazı Python/Node paketlerini derlemen gerekiyorsa lazım.",
      "Visual Studio Installer › Değiştir: kullanmadığın iş yüklerini kaldır."),
  en=("Visual Studio and Windows SDK", "Visual Studio, build tools and Windows development kits.",
      "Needed for C++/.NET development, or to compile some Python/Node packages.",
      "Visual Studio Installer › Modify: remove workloads you don't use."))
R("dotnet", ["#/Program Files/dotnet", "#/Program Files (x86)/dotnet", "~/.dotnet"], "dev", "keep", os="win", np=True,
  tr=(".NET çalışma zamanı ve SDK", ".NET uygulamalarını çalıştırmak ve geliştirmek için gereken dosyalar.",
      "Birçok program .NET ile çalışır. Eski SDK sürümleri kaldırılabilir.", "Ayarlar › Uygulamalar'dan eski .NET SDK sürümlerini kaldır."),
  en=(".NET runtime and SDK", "Files needed to run and build .NET applications.",
      "Many programs run on .NET. Old SDK versions can be uninstalled.", "Uninstall old .NET SDK versions from Settings › Apps."))
R("docker_data", ["~/AppData/Local/Docker", "#/ProgramData/Docker", "#/ProgramData/DockerDesktop", "/var/lib/docker",
                  "/var/lib/containerd", "/var/lib/containers", "~/.local/share/containers", "~/.local/share/docker",
                  "~/Library/Containers/com.docker.docker"], "virtual", "review", np=True,
  tr=("Docker verileri", "Docker imajları, konteynerleri, birimleri (volume) ve derleme önbelleği.",
      "Çalıştırdığın konteynerler için gerekli; eski imajlar ve derleme önbelleği sessizce onlarca GB olur.",
      "docker system df  ile bak;  docker system prune -a  ile kullanılmayanları temizle. Windows'ta sonra sanal diski sıkıştırmak gerekir."),
  en=("Docker data", "Docker images, containers, volumes and build cache.",
      "Needed for the containers you run; old images and build cache quietly reach tens of GB.",
      "Inspect with  docker system df;  clean unused data with  docker system prune -a. On Windows, compact the virtual disk afterwards."))
R("wsl_store", "~/AppData/Local/wsl", "virtual", "review", os="win", np=True,
  tr=("WSL (Linux) sanal diskleri", "Windows içindeki Linux dağıtımlarının (Ubuntu vb.) sanal diskleri.",
      "Linux ortamını kullanıyorsan gerekli. Dikkat: Linux içinde dosya silsen bile bu disk kendiliğinden küçülmez.",
      "“WSL ve sanal diskler” sayfasından içini incele; küçültmek için wsl --shutdown sonrası diski sıkıştır."),
  en=("WSL (Linux) virtual disks", "Virtual disks of the Linux distributions inside Windows (Ubuntu etc.).",
      "Needed if you use the Linux environment. Note: the disk does not shrink by itself when you delete files inside Linux.",
      "Inspect it on the “WSL & virtual disks” page; to shrink, compact the disk after wsl --shutdown."))
R("ai_models", ["~/.ollama", "~/.cache/huggingface", "~/.cache/torch", "~/.lmstudio", "~/.cache/lm-studio",
                "~/AppData/Local/nomic.ai", "~/.cache/whisper", "~/.keras", "~/.cache/modelscope",
                "~/AppData/Local/Ollama", "~/.cache/gpt4all", "~/.insightface", "~/.u2net",
                "/usr/share/ollama", "~/.local/share/nomic.ai"], "dev", "review", np=True,
  tr=("Yapay zekâ modelleri", "Ollama, Hugging Face, LM Studio, PyTorch gibi araçların indirdiği modeller.",
      "Her model birkaç GB'tır. Denediğin ama artık kullanmadığın modeller burada kalır.",
      "ollama list › ollama rm MODEL  ·  huggingface-cli delete-cache  ·  LM Studio › My Models."),
  en=("AI models", "Models downloaded by tools such as Ollama, Hugging Face, LM Studio, PyTorch.",
      "Each model is several GB. Models you tried once and no longer use stay here.",
      "ollama list › ollama rm MODEL  ·  huggingface-cli delete-cache  ·  LM Studio › My Models."))
R("unity_editors", ["#/Program Files/Unity/Hub/Editor", "#/Program Files/Unity Hub", "~/AppData/Local/Unity/cache",
                    "~/AppData/Local/UnrealEngine", "~/AppData/Roaming/Unity/Asset Store-5.x"], "dev", "review", os="win", np=True,
  tr=("Unity / Unreal sürümleri ve önbellekleri", "Kurulu oyun motoru sürümleri ve indirilen varlık önbellekleri.",
      "Her editör sürümü birkaç GB'tır; artık kullanmadığın sürümler kaldırılabilir.", "Unity Hub › Installs › sürümü kaldır."),
  en=("Unity / Unreal versions and caches", "Installed game-engine versions and downloaded asset caches.",
      "Each editor version is several GB; versions you no longer use can go.", "Unity Hub › Installs › uninstall the version."))

# ═════════════════════════════════════════════════════════════════════════════
#  Games, emulators, virtual machines
# ═════════════════════════════════════════════════════════════════════════════
R("steam_games", ["steamapps/common", "#/XboxGames", "#/Program Files/Epic Games", "#/Epic Games", "#/Riot Games",
                  "#/Program Files (x86)/Origin Games", "#/Program Files/EA Games", "#/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/games",
                  "#/Program Files (x86)/GOG Galaxy/Games", "#/Games", "#/Program Files (x86)/Battle.net", "#/Program Files/Rockstar Games"],
  "apps", "review", np=True, child="game",
  tr=("Oyunlar", "Steam, Epic, Xbox, Riot gibi mağazalardan kurulu oyunlar.",
      "Oyunlar diskin en büyük tüketicisidir. Artık oynamadıkların var mı? Kayıtların çoğunlukla bulutta durur.",
      "Oyunu kendi mağazasından (Steam › Kütüphane › sağ tık › Yönet › Kaldır) kaldır."),
  en=("Games", "Games installed from stores such as Steam, Epic, Xbox, Riot.",
      "Games are the biggest disk consumers. Any you no longer play? Saves usually live in the cloud.",
      "Uninstall from the game's own store (Steam › Library › right-click › Manage › Uninstall)."))
R("game", [], "apps", "review",
  tr=("Oyun", "Kurulu bir oyun.", "Hâlâ oynuyor musun? Oynamıyorsan kaldır; istersen sonra yeniden indirirsin.",
      "Oyunu kendi mağazasından kaldır."),
  en=("Game", "An installed game.", "Still playing it? If not, uninstall; you can download it again later.",
      "Uninstall it from its own store."))
R("minecraft", ["~/AppData/Roaming/.minecraft", "~/AppData/Roaming/.tlauncher"], "apps", "review", os="win", np=True,
  tr=("Minecraft", "Minecraft sürümleri, dünyaları, modları ve kaynak paketleri.",
      "Dünyaların “saves” klasöründe — silmeden önce yedekle. Eski sürümler ve modlar yer tutar.", ""),
  en=("Minecraft", "Minecraft versions, worlds, mods and resource packs.",
      "Your worlds are in “saves” — back up before deleting. Old versions and mods take space.", ""))
R("android_emulators", ["#/LDPlayer", "#/Program Files/BlueStacks_nxt", "#/ProgramData/BlueStacks_nxt", "#/ProgramData/BlueStacks",
                        "#/Program Files/Nox", "#/Program Files (x86)/Nox", "#/Program Files/Microvirt", "#/XuanZhi", "#/XuanZhi9",
                        "~/AppData/Local/Nox", "~/.BigNox", "#/Program Files/MuMu", "#/LDPlayer9", "#/Program Files/Netease"],
  "virtual", "review", os="win", np=True,
  tr=("Android emülatörü", "LDPlayer, BlueStacks, Nox gibi Android emülatörleri ve sanal cihaz diskleri.",
      "Hâlâ kullanıyor musun? Emülatörler içindeki oyunlarla birlikte onlarca GB'a ulaşır.",
      "Emülatörün çoklu örnek yöneticisinden kullanmadığın örnekleri sil veya emülatörü Ayarlar › Uygulamalar'dan kaldır."),
  en=("Android emulator", "Android emulators such as LDPlayer, BlueStacks, Nox and their virtual device disks.",
      "Still using it? With the games inside, emulators reach tens of GB.",
      "Delete unused instances in the emulator's multi-instance manager, or uninstall it from Settings › Apps."))
R("vm_disks", ["~/VirtualBox VMs", "~/Documents/Virtual Machines", "~/Virtual Machines", "#/ProgramData/Microsoft/Windows/Hyper-V",
               "#/Users/Public/Documents/Hyper-V", "~/.vagrant.d", "~/Parallels", "~/.lima", "~/.colima", "~/.multipass",
               "/var/lib/libvirt/images", "~/.local/share/gnome-boxes", "~/.local/share/libvirt", "/var/lib/lxd",
               "/var/snap/lxd", "/var/snap/multipassd",
               "~/AppData/Local/Packages/MicrosoftCorporationII.WindowsSubsystemForAndroid_8wekyb3d8bbwe"],
  "virtual", "review", np=True,
  tr=("Sanal makineler", "VirtualBox, VMware, Hyper-V gibi programların sanal makine diskleri.",
      "Her sanal makine tam bir işletim sistemi kadar yer tutar. Hâlâ açıp kullandığın makineler mi?",
      "Sanallaştırma programının içinden makineyi “tüm dosyalarıyla sil”."),
  en=("Virtual machines", "Virtual machine disks of VirtualBox, VMware, Hyper-V and similar.",
      "Each VM takes as much as a full operating system. Do you still boot these?",
      "Delete the VM “with all files” from inside the virtualisation program."))

# ═════════════════════════════════════════════════════════════════════════════
#  macOS
# ═════════════════════════════════════════════════════════════════════════════
R("mac_system", ["#/System", "#/Library", "#/private", "#/usr", "#/bin", "#/sbin"], "system", "keep", os="mac", np=True,
  tr=("macOS sistemi", "İşletim sistemi dosyaları.", "Mac'in çalışması için gerekli; dokunma.", ""),
  en=("macOS system", "Operating system files.", "Required for the Mac to run; don't touch.", ""))
R("mac_apps", "#/Applications", "apps", "info", os="mac", np=True, child="mac_app",
  tr=("Uygulamalar", "Kurulu uygulamalar.", "Kullanmadıklarını Çöp Sepeti'ne sürükleyerek kaldırabilirsin.", ""),
  en=("Applications", "Installed applications.", "Remove the ones you don't use by dragging them to the Trash.", ""))
R("mac_app", [], "apps", "review", os="mac",
  tr=("Uygulama", "Kurulu bir uygulama.", "Hâlâ kullanıyor musun?", "Çöp Sepeti'ne sürükle."),
  en=("Application", "An installed application.", "Do you still use it?", "Drag it to the Trash."))
R("mac_library", "~/Library", "data", "info", os="mac", np=True,
  tr=("Kitaplık (Library)", "Uygulamaların sana özel ayarları, verileri ve önbellekleri.",
      "Gizli bir klasördür; büyük alt klasörlere tek tek bak.", ""),
  en=("Library", "Per-user settings, data and caches of your apps.", "A hidden folder; check large sub-folders one by one.", ""))
R("mac_xcode", ["~/Library/Developer/Xcode/DerivedData", "~/Library/Developer/Xcode/iOS DeviceSupport",
                "~/Library/Developer/Xcode/watchOS DeviceSupport", "~/Library/Developer/CoreSimulator/Caches"],
  "dev", "safe", os="mac", clean=True,
  tr=("Xcode önbellekleri", "Xcode derleme çıktıları ve cihaz destek dosyaları.",
      "Bir sonraki derlemede / cihaz bağlandığında yeniden oluşur.", "Klasörleri silebilirsin."),
  en=("Xcode caches", "Xcode build output and device-support files.",
      "Recreated by the next build / when a device connects.", "The folders can be deleted."))
R("mac_simulators", ["~/Library/Developer/CoreSimulator", "~/Library/Developer/Xcode/Archives"], "dev", "review", os="mac",
  tr=("iOS simülatörleri ve arşivler", "Simülatör cihazları ve eski uygulama arşivleri.",
      "Eski iOS sürümlerinin simülatörleri unutulup kalır.", "xcrun simctl delete unavailable"),
  en=("iOS simulators and archives", "Simulator devices and old app archives.",
      "Simulators of old iOS versions are easily forgotten.", "xcrun simctl delete unavailable"))
R("mac_trash", ["~/.Trash", "~/.local/share/Trash"], "personal", "safe", os="posix",
  tr=("Çöp Sepeti", "Sildiğin ama henüz kalıcı olarak silinmemiş dosyalar.", "Geri almak istediğin bir şey yoksa gerekmez.", "Çöp Sepeti'ni boşalt."),
  en=("Trash", "Files you deleted that are not permanently gone yet.", "Not needed unless you want something back.", "Empty the Trash."))
R("homebrew", ["#/opt/homebrew", "#/usr/local/Cellar", "#/home/linuxbrew"], "dev", "info", os="posix", np=True,
  tr=("Homebrew", "Homebrew ile kurulan paketler.", "Kurduğun komut satırı araçları burada.", "brew cleanup -s  ·  brew autoremove"),
  en=("Homebrew", "Packages installed with Homebrew.", "Your command-line tools live here.", "brew cleanup -s  ·  brew autoremove"))

# ═════════════════════════════════════════════════════════════════════════════
#  Linux (also used to explain what is inside WSL)
# ═════════════════════════════════════════════════════════════════════════════
R("lin_system", ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/boot"], "system", "keep", os="linux", np=True,
  tr=("Linux sistemi", "Dağıtımın kendisi ve kurulu paketler.",
      "Sistemin çalışması için gerekli. Yer açmak için kullanmadığın paketleri paket yöneticisiyle kaldır.",
      "sudo apt autoremove --purge  ·  eski çekirdekler de böyle temizlenir."),
  en=("Linux system", "The distribution itself and installed packages.",
      "Required for the system to run. To save space, remove unused packages with the package manager.",
      "sudo apt autoremove --purge  ·  this also removes old kernels."))
R("lin_apt_cache", ["/var/cache/apt", "/var/lib/apt/lists", "/var/cache/pacman", "/var/cache/dnf", "/var/cache/yum",
                    "/var/cache/apk", "/var/cache/zypp"], "system", "safe", os="linux",
  tr=("Paket yöneticisi önbelleği", "İndirilmiş kurulum paketleri (.deb vb.).", "Kurulumdan sonra gerekmez.", "sudo apt clean"),
  en=("Package manager cache", "Downloaded install packages (.deb etc.).", "Not needed after installation.", "sudo apt clean"))
R("lin_logs", ["/var/log", "/var/crash", "/var/lib/systemd/coredump"], "system", "safe", os="linux",
  tr=("Sistem günlükleri", "Sistem ve servis günlükleri, çökme dökümleri.",
      "Yalnızca bir sorunu araştırırken işe yarar.", "sudo journalctl --vacuum-size=200M"),
  en=("System logs", "System and service logs, crash dumps.", "Only useful while debugging.", "sudo journalctl --vacuum-size=200M"))
R("lin_tmp", ["/tmp", "/var/tmp"], "system", "safe", os="linux",
  tr=("Geçici dosyalar", "Programların geçici dosyaları.", "Çalışan programlarınkiler dışında gerekmez.", "Yeniden başlatınca /tmp temizlenir."),
  en=("Temporary files", "Temp files of programs.", "Not needed except by running programs.", "/tmp is cleared on reboot."))
R("lin_snap", ["/var/lib/snapd", "/snap", "/var/lib/flatpak"], "apps", "info", os="linux", np=True,
  tr=("Snap / Flatpak uygulamaları", "Snap ve Flatpak paketleri; her uygulamanın eski sürümleri de saklanır.",
      "Kurduğun uygulamalar burada. Eski revizyonlar boşuna yer tutar.",
      "sudo snap set system refresh.retain=2  ·  flatpak uninstall --unused"),
  en=("Snap / Flatpak apps", "Snap and Flatpak packages; old revisions of every app are kept too.",
      "Your installed apps live here. Old revisions waste space.",
      "sudo snap set system refresh.retain=2  ·  flatpak uninstall --unused"))
R("lin_opt", ["/opt", "/usr/local"], "apps", "info", os="linux", np=True,
  tr=("Elle kurulan yazılımlar", "Paket yöneticisi dışında kurulmuş programlar.", "Kendi kurduğun araçlar burada.", ""),
  en=("Manually installed software", "Programs installed outside the package manager.", "Tools you installed yourself live here.", ""))
R("vscode_server", ["~/.vscode-server", "~/.cursor-server", "~/.vscode-remote", "~/.windsurf-server"], "dev", "info", os="linux", np=True,
  tr=("VS Code sunucu dosyaları", "VS Code / Cursor'ın WSL veya uzak bağlantı için kurduğu sunucu, eklentiler ve uzak oturum verileri.",
      "Her editör güncellemesinde yeni bir sunucu sürümü iner, eskiler “bin” altında birikir. “data” klasöründe ise sohbet ve çalışma alanı verilerin durur.",
      "Yalnızca “bin” altındaki eski sürüm klasörlerini sil; “data” klasörüne dokunma."),
  en=("VS Code server files", "The server, extensions and remote-session data VS Code / Cursor install for WSL or remote connections.",
      "Every editor update downloads a new server copy and old ones pile up under “bin”. The “data” folder holds your chats and workspace data.",
      "Delete only old version folders under “bin”; leave “data” alone."))
R("lin_wsl_mounts", ["/mnt", "/media", "/proc", "/sys", "/dev", "/run"], None, "info", os="linux", np=True, hidden=True)
R("lin_var", ["/var", "/srv"], "system", "info", os="linux", np=True, nofind=True,
  tr=("Sistem verileri (/var)", "Günlükler, paket veritabanları, servislerin verileri ve sistem önbellekleri.",
      "Sistemin kendi çalışma verileri. İçindeki büyük kalemler (Docker, snap, günlükler…) ayrı bulgular olarak listelenir.", ""),
  en=("System data (/var)", "Logs, package databases, service data and system caches.",
      "The system's own working data. Large items inside (Docker, snap, logs…) are listed as separate findings.", ""))
R("lin_databases", ["/var/lib/mysql", "/var/lib/postgresql", "/var/lib/mongodb", "/var/lib/redis", "/var/lib/influxdb"],
  "data", "keep", os="linux", np=True,
  tr=("Veritabanı verileri", "MySQL, PostgreSQL, MongoDB gibi veritabanı sunucularının verileri.",
      "Veritabanlarının kendisi burada; silersen verin gider. Kullanmadığın bir sunucuysa paketini kaldır.",
      "Önce yedek al (mysqldump / pg_dump), sonra gereksiz veritabanlarını sunucunun kendi komutlarıyla sil."),
  en=("Database data", "Data of database servers such as MySQL, PostgreSQL, MongoDB.",
      "The databases themselves live here; deleting loses your data. If you no longer use the server, remove its package.",
      "Back up first (mysqldump / pg_dump), then drop unneeded databases with the server's own commands."))
R("timeshift", ["#/timeshift", "/run/timeshift"], "system", "review", os="linux", np=True,
  tr=("Timeshift anlık görüntüleri", "Sistemin eski hâllerine dönebilmen için alınmış anlık görüntüler.",
      "Sistem bozulursa geri dönmeni sağlar; ama eski görüntüler onlarca GB tutabilir.",
      "Timeshift uygulamasından eski görüntüleri sil (veya: sudo timeshift --list, sudo timeshift --delete --snapshot AD)."),
  en=("Timeshift snapshots", "Snapshots that let you roll the system back to an earlier state.",
      "They save you if the system breaks; but old snapshots can take tens of GB.",
      "Delete old snapshots in the Timeshift app (or: sudo timeshift --list, sudo timeshift --delete --snapshot NAME)."))
R("linux_config", ["~/.config", "~/.local/share", "~/.var"], "data", "info", os="linux", np=True,
  tr=("Uygulama ayarları ve verileri", "Programların sana özel ayarları ve verileri (~/.config, ~/.local/share, Flatpak için ~/.var).",
      "Gizli klasörlerdir; oturumların, ayarların ve bazen büyük veri klasörleri burada durur. İçindeki bulgulara tek tek bak.", ""),
  en=("Application settings and data", "Per-user settings and data of your programs (~/.config, ~/.local/share, ~/.var for Flatpak).",
      "Hidden folders holding your sessions, settings and sometimes large data folders. Check the findings inside one by one.", ""))
R("snap_home", "~/snap", "data", "info", os="linux", np=True,
  tr=("Snap uygulamalarının verileri", "Snap ile kurulan uygulamaların (Firefox, Chromium…) sana özel verileri.",
      "Uygulama güncellendikçe eski sürümlerin verileri de saklanır; önbellekleri ayrı bir bulgu olarak listelenir.",
      "Kullanmadığın uygulamayı “sudo snap remove AD” ile kaldır; verisini de silmek için “--purge” ekle."),
  en=("Snap app data", "Per-user data of apps installed as snaps (Firefox, Chromium…).",
      "Data of older revisions is kept as apps update; their caches are listed as a separate finding.",
      "Remove an unused app with “sudo snap remove NAME”; add “--purge” to delete its data too."))
R("wine_prefix", ["~/.wine", "~/.local/share/lutris", "~/.local/share/bottles", "~/Games"], "apps", "review",
  os="linux", np=True,
  tr=("Oyun ve Windows programı ortamları", "Wine, Lutris ve Bottles ile kurulan oyunlar ve Windows programları.",
      "Oyunlar diskin en büyük tüketicisidir. Artık oynamadıkların ya da kullanmadığın ortamlar var mı?",
      "Oyunu Steam / Lutris içinden kaldır; kullanmadığın Wine ortamının klasörünü silebilirsin."),
  en=("Game and Windows-program environments", "Games and Windows programs installed through Wine, Lutris and Bottles.",
      "Games are the biggest disk consumers. Any you no longer play, or environments you no longer use?",
      "Uninstall the game from Steam / Lutris; an unused Wine prefix folder can be deleted."))

# ═════════════════════════════════════════════════════════════════════════════
#  Notable files (matched by exact name or extension, only for large files)
# ═════════════════════════════════════════════════════════════════════════════
F("pagefile", "system", "keep", names=("pagefile.sys", "swapfile.sys"),
  tr=("Sayfa dosyası (sanal bellek)", "RAM dolduğunda Windows'un kullandığı disk alanı.",
      "Bellek yetmediğinde programların çökmemesini sağlar. Kaldırmak önerilmez.",
      "Gelişmiş sistem ayarları › Performans › Gelişmiş › Sanal bellek'ten boyutu sınırlandırabilirsin."),
  en=("Page file (virtual memory)", "Disk space Windows uses when RAM is full.",
      "Keeps programs from crashing when memory runs out. Removing it is not recommended.",
      "You can cap its size in Advanced system settings › Performance › Advanced › Virtual memory."))
F("swapfile", "system", "keep", names=("swapfile", "swap.img"),
  tr=("Takas dosyası (swap)", "RAM dolduğunda sistemin kullandığı disk alanı.",
      "Bellek yetmediğinde programların kapanmamasını sağlar; hazırda bekletme de bunu kullanır.",
      "Küçültmek için: sudo swapoff DOSYA, yeni boyutla yeniden oluştur (fallocate + mkswap), sudo swapon DOSYA."),
  en=("Swap file", "Disk space the system uses when RAM is full.",
      "Keeps programs from being killed when memory runs out; hibernation uses it too.",
      "To shrink: sudo swapoff FILE, recreate it at the new size (fallocate + mkswap), sudo swapon FILE."))
F("hiberfil", "system", "review", names=("hiberfil.sys",),
  tr=("Hazırda bekletme dosyası", "“Hazırda beklet” ve “Hızlı başlatma” için RAM'in diske yazıldığı dosya.",
      "Hazırda bekletmeyi hiç kullanmıyorsan tamamı geri kazanılabilir (Hızlı başlatma da kapanır; uyku modu etkilenmez).",
      "Yönetici terminalinde: powercfg /h off   (geri açmak için: powercfg /h on)"),
  en=("Hibernation file", "The file RAM is written to for “Hibernate” and “Fast startup”.",
      "If you never hibernate, all of it can be reclaimed (Fast startup turns off too; Sleep is unaffected).",
      "In an admin terminal: powercfg /h off   (to restore: powercfg /h on)"))
F("memory_dump", "system", "safe", names=("memory.dmp",), exts=("dmp", "mdmp", "hdmp"),
  tr=("Bellek dökümü", "Bir çökme anında belleğin diske yazılmış kopyası.",
      "Yalnızca çökmeyi inceleyeceksen gerekir.", "Silebilirsin (Disk Temizleme › “Sistem hata bellek döküm dosyaları”)."),
  en=("Memory dump", "A copy of memory written to disk at a crash.",
      "Only needed to analyse the crash.", "Can be deleted (Disk Cleanup › “System error memory dump files”)."))
F("vdisk", "virtual", "review", exts=("vhdx", "vhd", "avhdx", "vmdk", "vdi", "qcow2", "hdd"),
  tr=("Sanal disk", "Bir sanal makinenin, WSL dağıtımının, Docker'ın veya emülatörün diski.",
      "İçindeki sistem/veri bu dosyadadır. Hâlâ kullandığın bir ortama mı ait? İçinde dosya silinse bile kendiliğinden küçülmez.",
      "Ait olduğu programdan sil veya sıkıştır (WSL için: wsl --shutdown › Optimize-VHD / diskpart compact vdisk)."),
  en=("Virtual disk", "The disk of a virtual machine, WSL distribution, Docker or an emulator.",
      "The system/data inside lives in this file. Does it belong to something you still use? It never shrinks by itself.",
      "Delete or compact it from the owning program (WSL: wsl --shutdown › Optimize-VHD / diskpart compact vdisk)."))
F("disk_image", "personal", "review", exts=("iso", "img", "wim", "esd", "dmg"),
  tr=("Disk kalıbı / kurulum medyası", "İşletim sistemi veya program kurulum kalıbı.",
      "Kurulumu yaptıysan gerekmez; gerekirse yeniden indirilir.", "Silebilirsin."),
  en=("Disk image / install media", "An operating system or program install image.",
      "Not needed once installed; can be downloaded again.", "Can be deleted."))
F("ai_model", "dev", "review", exts=("gguf", "safetensors", "ckpt", "pth", "onnx", "tflite", "mlmodel"),
  tr=("Yapay zekâ modeli", "Yerel çalıştırılan bir yapay zekâ modelinin ağırlık dosyası.",
      "Hâlâ kullandığın bir model mi? Çoğu yeniden indirilebilir.", "Kullanmıyorsan silebilirsin."),
  en=("AI model", "Weights file of a locally run AI model.",
      "A model you still use? Most can be downloaded again.", "Delete it if unused."))
F("archive", "personal", "review", exts=("zip", "rar", "7z", "tar", "gz", "tgz", "xz", "zst", "bz2"),
  tr=("Arşiv dosyası", "Sıkıştırılmış arşiv.",
      "İçini zaten çıkardıysan aynı veriyi iki kez saklıyorsun.", "Çıkarılmış kopyası duruyorsa arşivi silebilirsin."),
  en=("Archive", "A compressed archive.",
      "If you already extracted it, you are storing the same data twice.", "Delete the archive if the extracted copy exists."))
F("installer", "personal", "review", exts=("exe", "msi", "msix", "msixbundle", "appx", "pkg", "deb", "rpm", "apk"),
  tr=("Kurulum dosyası", "Bir programın kurulum paketi.",
      "Program kurulduktan sonra gerekmez; yeni sürümü zaten yeniden indirilir.", "Silebilirsin."),
  en=("Installer", "A program's install package.",
      "Not needed once installed; a newer version would be downloaded anyway.", "Can be deleted."))
F("video", "personal", "review", exts=("mp4", "mkv", "mov", "avi", "wmv", "webm", "m4v", "flv", "mpg", "mpeg", "ts", "m2ts"),
  tr=("Video", "Video dosyası.", "İzlediysen veya yedeği varsa gerekmeyebilir.", "Sil veya harici diske / buluta taşı."),
  en=("Video", "A video file.", "May not be needed if watched or backed up.", "Delete or move to an external disk / the cloud."))
F("mail_store", "data", "keep", exts=("pst", "ost"),
  tr=("Outlook veri dosyası", "E-postalarının bulunduğu Outlook dosyası.",
      ".pst dosyası e-postalarının tek kopyası olabilir; emin olmadan silme.", ""),
  en=("Outlook data file", "The Outlook file holding your e-mail.",
      "A .pst may be the only copy of your mail; don't delete unless sure.", ""))
F("db_backup", "data", "review", exts=("bak", "sql", "dump", "backup", "old", "tmp", "log", "etl"),
  tr=("Yedek / günlük dosyası", "Veritabanı yedeği, döküm veya büyük bir günlük dosyası.",
      "Eski yedekler ve günlükler genellikle unutulur.", "İçeriğini biliyorsan ve gerekmiyorsa sil."),
  en=("Backup / log file", "A database backup, dump or large log file.",
      "Old backups and logs are usually forgotten.", "Delete if you know what it is and don't need it."))

# ── file type groups (for the "file types" chart) ────────────────────────────
TYPE_GROUPS = {
    "video": "mp4 mkv mov avi wmv webm flv m4v mpg mpeg ts m2ts 3gp vob",
    "image": "jpg jpeg png gif bmp tif tiff webp heic heif raw cr2 cr3 nef arw dng psd psb ai svg ico xcf kra exr tga",
    "audio": "mp3 wav flac aac ogg m4a wma opus aiff aif mid",
    "archive": "zip rar 7z tar gz tgz bz2 xz zst cab lz4 jar war nupkg whl",
    "document": "pdf doc docx xls xlsx ppt pptx odt ods odp txt rtf md epub mobi csv tex one",
    "code": "py js mjs cjs ts tsx jsx java kt c cc cpp h hpp cs go rs rb php swift html htm css scss json xml yaml yml "
            "toml sh ps1 bat sql ipynb lua dart vue svelte map",
    "program": "exe dll sys msi msix appx so dylib ocx drv pyd node mui winmd efi msp mum cat",
    "build": "o obj pdb class pyc gch pch ilk idb ipch tlog lib a rlib rmeta dex",
    "disk": "vhdx vhd avhdx vmdk vdi qcow2 iso img wim esd dmg hdd",
    "model": "gguf safetensors ckpt pth pt onnx tflite h5 pb mlmodel",
    "data": "db sqlite sqlite3 mdb accdb mdf ldf edb pst ost dat bak dmp log etl parquet npy npz pkl idx pack bin blob",
    "game": "pak ucas utoc vpk bsa unity3d assets bundle wad rpf upk uasset umap",
    "font": "ttf otf woff woff2 ttc",
}
_EXT_GROUP = {}
for _g, _exts in TYPE_GROUPS.items():
    for _e in _exts.split():
        _EXT_GROUP[_e] = _g


def ext_group(ext):
    return _EXT_GROUP.get(ext, "other")


# ── "named like a cache, but is it one?" ─────────────────────────────────────
# A real HTTP / code / GPU cache holds anonymous blobs. These are signs of something else:
# a whole browser profile, an application's database, or program code.
_PROFILE_NAMES = frozenset(("local storage", "session storage", "indexeddb", "network", "cookies", "databases",
                            "webstorage", "current", "__init__.py", "package.json"))
_STATE_EXTS = frozenset(("db", "sqlite", "sqlite3", "vscdb", "ldb", "tbres"))
_CODE_EXTS = frozenset(("py", "pyc", "pyd", "js", "mjs", "cjs", "dll", "exe", "so", "dylib", "node", "jar", "class"))


def looks_like_data(names):
    """True when a folder's entry names say "application data or program code", not "cache"."""
    for name in names:
        low = name.lower()
        if low in _PROFILE_NAMES:
            return True
        i = low.rfind(".")
        if i > 0:
            ext = low[i + 1:]
            if ext in _STATE_EXTS or ext in _CODE_EXTS:
                return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
#  Engine
# ═════════════════════════════════════════════════════════════════════════════

def platform_key(platform=None):
    p = platform or sys.platform
    if p.startswith("win"):
        return "win"
    if p == "darwin" or p == "mac":
        return "mac"
    return "linux"


def _part_rx(part):
    if part == "*":
        return "[^/]+"
    if "*" in part:
        return "[^/]*".join(re.escape(x) for x in part.split("*"))
    return re.escape(part)


class RuleSet(object):
    """Rules compiled for one platform, indexed by the folder name they end with."""

    def __init__(self, platform=None, home=None):
        self.platform = plat = platform_key(platform)
        self.rules = {}
        cands = {}
        pcands = {}                     # patterns whose last part ends in "*" (e.g. Packages/OpenAI.*)
        if plat == "win":
            home_rx = r"^[a-z]:/users/[^/]+"
            root_rx = r"^[a-z]:"
        elif plat == "mac":
            home_rx = r"^/users/[^/]+"
            root_rx = r"^"
        else:
            home_rx = r"^(?:/home/[^/]+|/root)"
            root_rx = r"^"
        if home:
            h = home.replace("\\", "/").rstrip("/").lower()
            if h and not re.match(home_rx + "$", h):
                home_rx = "(?:%s|^%s)" % (home_rx, re.escape(h))
        for rule in _RULES:
            if rule.os and not (rule.os == plat or (rule.os == "posix" and plat != "win")):
                continue
            self.rules[rule.id] = rule
            for pat in rule.pats:
                parts = [p for p in pat.replace("\\", "/").lower().split("/") if p]
                if not parts:
                    continue
                if parts[0] == "~":
                    prefix, parts = home_rx + "/", parts[1:]
                elif parts[0] == "#":
                    prefix, parts = root_rx + "/", parts[1:]
                elif pat.startswith("/"):
                    if plat == "win":
                        continue                              # absolute POSIX path: meaningless here
                    prefix = "^/"
                else:
                    prefix = "(?:^|/)"
                if not parts:
                    continue
                last = parts[-1]
                stem = last[:-1] if last.endswith("*") else None
                if "*" in last and (stem is None or "*" in stem or len(stem) < PREFIX_KEY):
                    continue                                  # only a literal name or "prefix*" can be indexed
                body = []
                for part in parts:
                    body.append("(?:[^/]+/)*" if part == "**" else _part_rx(part) + "/")
                rx = re.compile(prefix + "".join(body)[:-1] + "$")
                spec = len(parts) + (2 if prefix != "(?:^|/)" else 0) + (1 if rule.has else 0)
                if stem is None:
                    cands.setdefault(last, []).append((spec, rx, rule))
                else:
                    pcands.setdefault(stem[:PREFIX_KEY], []).append((spec, stem, rx, rule))
        self.cands = {}
        for name, lst in cands.items():
            lst.sort(key=lambda t: -t[0])
            self.cands[name] = tuple((rx, rule) for _s, rx, rule in lst)
        self.pcands = {}
        for key, lst in pcands.items():
            lst.sort(key=lambda t: -t[0])
            self.pcands[key] = tuple((stem, rx, rule) for _s, stem, rx, rule in lst)
        for rule in self.rules.values():                       # resolve child rule ids
            if isinstance(rule.child, str):
                rule.child = self.rules.get(rule.child)
        self.file_names = {}
        self.file_exts = {}
        for fr in _FILE_RULES:
            for n in fr["names"]:
                self.file_names[n] = fr
            for e in fr["exts"]:
                self.file_exts[e] = fr
        self.file_rules = {fr["id"]: fr for fr in _FILE_RULES}

    def match_path(self, path, hidden=False):
        """Best rule for a full path, without looking at the folder's contents
        (used for trees we did not walk ourselves, e.g. `du` output from WSL).
        `hidden=True` also returns technical rules — the cleaner wants to know about those."""
        lpath = path.replace("\\", "/").rstrip("/").lower()
        name = lpath.rsplit("/", 1)[-1]
        for rx, rule in self.cands.get(name, ()):
            if rule.inproj or rule.has:
                continue
            if rx.search(lpath):
                # a technical rule still "wins" the folder: it must not fall through to a broader rule
                return rule if (hidden or not rule.hidden) else None
        for stem, rx, rule in self.pcands.get(name[:PREFIX_KEY], ()):
            if name.startswith(stem) and rx.search(lpath):
                return rule if (hidden or not rule.hidden) else None
        return None

    def guard_above(self, path, stop):
        """The guarded folder (a `keep` rule, installed programs, an AI tool…) that `path` lies
        inside, looking only below `stop`; None when there is none."""
        probe = path.replace("\\", "/").rstrip("/")
        stop = stop.replace("\\", "/").rstrip("/")
        while True:
            probe = probe.rsplit("/", 1)[0]
            if len(probe) <= len(stop):
                return None
            rule = self.match_path(probe, hidden=True)
            if rule is not None and rule.guards:
                return rule

    def file_rule(self, name):
        lname = name.lower()
        fr = self.file_names.get(lname)
        if fr is None:
            i = lname.rfind(".")
            if i > 0:
                fr = self.file_exts.get(lname[i + 1:])
        return fr

    def texts(self):
        """All rule texts for the UI: {id: {cat, act, tr: [...], en: [...]}}."""
        out = {}
        for rule in self.rules.values():
            if not rule.hidden:
                out[rule.id] = {"cat": rule.cat, "act": rule.act, "clean": rule.clean, "keepDays": rule.keep_days,
                                "tr": rule.text["tr"], "en": rule.text["en"]}
        for fr in _FILE_RULES:
            out["file:" + fr["id"]] = {"cat": fr["cat"], "act": fr["act"], "tr": fr["text"]["tr"], "en": fr["text"]["en"]}
        return out
