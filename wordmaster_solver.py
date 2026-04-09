#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word Master Otomatik Çözücü
════════════════════════════════════════════════════════════════════
Telefon ekranındaki hexagonal grid'i ADB ile yakalar,
OpenCV ile altıgenleri tespit eder, EasyOCR ile harfleri okur,
Trie+DFS ile tüm Türkçe kelimeleri bulur ve en uzun kelimeyi
uiautomator2 (veya ADB fallback) ile otomatik swipe eder.

Gereksinimler:
  pip install opencv-python numpy uiautomator2
  python -m uiautomator2 init   ← telefon bağlıyken bir kez çalıştır

Kullanım:
  python wordmaster_solver.py              # en uzun kelimeyi oynar
  python wordmaster_solver.py --dry-run    # swipe yapmadan test eder
  python wordmaster_solver.py --debug      # debug_detected.png kaydeder
  python wordmaster_solver.py --all        # tüm kelimeleri sırayla oynar
  python wordmaster_solver.py --word ZİT   # belirli kelimeyi oynar
  python wordmaster_solver.py --list       # kelimeleri listeler, oynatmaz
════════════════════════════════════════════════════════════════════
"""

# ════════════════════════════════════════════════════════════════════
#  ⚙️  TELEFONA ÖZGÜ AYARLAR — BURASI SANA GÖRE DEĞİŞEBİLİR
# ════════════════════════════════════════════════════════════════════

ADB_PATH = "adb"
DEVICE_ID = None
WORD_LIST_PATH = "tdk.txt"

MIN_WORD_LENGTH = 3

SWIPE_STEP_MS = 10

SCREENSHOT_PATH = "screen.png"

GRAY_THRESH = 230
HEX_AREA_MIN = 15_000
HEX_AREA_MAX = 70_000
NEIGHBOR_TOLERANCE = 1.3

TEMPLATE_DIR = "templates"

# ════════════════════════════════════════════════════════════════════

import argparse, math, os, shutil, subprocess, sys, time
from collections import defaultdict

import cv2
import numpy as np

# ────────────────────────────────────────────────────────────────────
#  Türkçe alfabe sabitleri
# ────────────────────────────────────────────────────────────────────

TR_UPPER = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"
_TO_UPPER = {
    'a':'A','b':'B','c':'C','ç':'Ç','d':'D','e':'E','f':'F','g':'G',
    'ğ':'Ğ','h':'H','ı':'I','i':'İ','j':'J','k':'K','l':'L','m':'M',
    'n':'N','o':'O','ö':'Ö','p':'P','r':'R','s':'S','ş':'Ş','t':'T',
    'u':'U','ü':'Ü','v':'V','y':'Y','z':'Z',
}
_TO_UPPER.update({v: v for v in _TO_UPPER.values()})

def tr_upper(s: str) -> str:
    return ''.join(_TO_UPPER.get(c, c.upper()) for c in s)

# ────────────────────────────────────────────────────────────────────
#  Trie — prefix ağacı (hızlı kelime arama için)
# ────────────────────────────────────────────────────────────────────

class TrieNode:
    __slots__ = ('children', 'is_end')
    def __init__(self):
        self.children: dict = {}
        self.is_end: bool = False

class Trie:
    def __init__(self):
        self.root = TrieNode()
        self.count = 0

    def insert(self, word: str):
        node = self.root
        for ch in word:
            node = node.children.setdefault(ch, TrieNode())
        if not node.is_end:
            node.is_end = True
            self.count += 1

def load_trie(path: str) -> Trie:
    """Kelime listesini Trie'ye yükle."""
    if not os.path.exists(path):
        sys.exit(f"❌  Kelime listesi bulunamadı: {path}")
    trie = Trie()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            w = tr_upper(line.strip())
            if 2 <= len(w) <= 25 and all(c in TR_UPPER for c in w):
                trie.insert(w)
    print(f"✅  {trie.count:,} kelime Trie'ye yüklendi.")
    return trie

# ────────────────────────────────────────────────────────────────────
#  ADB yardımcıları
# ────────────────────────────────────────────────────────────────────

def _resolve_adb() -> str:
    """
    ADB çalıştırılabilirini bul.
    1. ADB_PATH ayarı (kullanıcı doldurduysa)
    2. sistem PATH'i
    3. Android SDK'nın tipik Windows konumları
    """
    # Kullanıcı açıkça yol verdiyse onu kullan
    if ADB_PATH != "adb":
        if os.path.isfile(ADB_PATH):
            return ADB_PATH
        sys.exit(
            f"❌  ADB bulunamadı: {ADB_PATH}\n"
            "   ADB_PATH ayarını kontrol et."
        )

    # PATH'te var mı?
    found = shutil.which("adb")
    if found:
        return found

    # Windows tipik Android SDK konumları
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        r"C:\Program Files\Android\android-sdk\platform-tools\adb.exe",
        r"C:\Android\platform-tools\adb.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            print(f"   ADB otomatik bulundu: {c}")
            return c

    sys.exit(
        "❌  ADB bulunamadı!\n\n"
        "   Çözüm seçenekleri:\n"
        "   1) Android Studio kuruluysa PATH genellikle otomatik eklenir — \n"
        "      yeni bir terminal aç ve tekrar dene.\n"
        "   2) Dosyanın en üstündeki ADB_PATH değişkenine tam yolu yaz:\n"
        r'      ADB_PATH = r"C:\Users\Yunus\AppData\Local\Android\Sdk\platform-tools\adb.exe"'
        "\n   3) Sadece ADB istiyorsan platform-tools'u indir:\n"
        "      https://developer.android.com/tools/releases/platform-tools"
    )

_ADB_EXE: str | None = None   # çözülmüş yol — bir kez bulunca önbelleğe al

def _adb(*args) -> subprocess.CompletedProcess:
    """ADB komutunu çalıştır. DEVICE_ID varsa -s flag ekle."""
    global _ADB_EXE
    if _ADB_EXE is None:
        _ADB_EXE = _resolve_adb()

    cmd = [_ADB_EXE]
    if DEVICE_ID:
        cmd += ['-s', DEVICE_ID]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True)   # binary mod — text=False

def take_screenshot(path: str = SCREENSHOT_PATH) -> str:
    """Telefon ekranını yakala ve yerel diske kaydet."""
    print("📸  Ekran görüntüsü alınıyor…")

    # exec-out: telefon PNG'yi stdout'a yazar, biz binary olarak alıyoruz
    r = _adb('exec-out', 'screencap', '-p')
    if r.returncode == 0 and len(r.stdout) > 1000:
        with open(path, 'wb') as f:
            f.write(r.stdout)
    else:
        # Fallback: cihaza yaz, sonra çek
        _adb('shell', 'screencap', '-p', '/sdcard/_wm_screen.png')
        _adb('pull', '/sdcard/_wm_screen.png', path)
        _adb('shell', 'rm', '/sdcard/_wm_screen.png')

    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        sys.exit(
            "❌  Ekran görüntüsü alınamadı.\n"
            "   Kontrol listesi:\n"
            "   • Telefon USB ile bağlı mı?\n"
            "   • Ayarlar → Geliştirici Seçenekleri → USB Hata Ayıklama AÇIK mı?\n"
            "   • Telefon ekranda 'Bu bilgisayara güven?' diye soruyorsa Tamam de.\n"
            "   • 'adb devices' çalıştırınca cihazın 'device' olarak görünüyor mu?"
        )
    print(f"   Kaydedildi: {path}  ({os.path.getsize(path)//1024} KB)")
    return path

# ────────────────────────────────────────────────────────────────────
#  Hexagon tespiti (OpenCV)
# ────────────────────────────────────────────────────────────────────

def detect_hexagons(img_bgr: np.ndarray, debug: bool = False) -> list[dict]:
    """
    BGR görüntüden oyun hexagonlarının merkezlerini ve yarıçaplarını bul.
    Döndürür: [{'id': int, 'cx': int, 'cy': int, 'r': float}, ...]
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Hexler arka plandan ~15 birim daha açık — sabit eşik yeterli
    _, thresh = cv2.threshold(blur, GRAY_THRESH, 255, cv2.THRESH_BINARY)

    # Morfoloji: küçük gürültüleri temizle, hexlerin iç boşluklarını kapat
    k = np.ones((7, 7), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  k)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Alan ve en-boy oranı filtresi
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if debug:
            x,y,bw,bh = cv2.boundingRect(cnt)
            if area > 5000:
                print(f"  kontur alan={area:.0f}  boyut={bw}x{bh}  oran={bw/bh if bh else 0:.2f}")
        if not (HEX_AREA_MIN < area < HEX_AREA_MAX):
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if not (0.80 < bw / bh < 1.30):
            continue
        M = cv2.moments(cnt)
        if M['m00'] == 0:
            continue
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])
        r  = math.sqrt(area / 2.598)     # altıgen alan = 2.598 * r²
        candidates.append({'cx': cx, 'cy': cy, 'r': r, 'area': int(area)})

    if not candidates:
        sys.exit(
            "❌  Hiç hexagon bulunamadı!\n"
            "   → --debug modunda tüm kontur alanları yazdırılır.\n"
            "   → GRAY_THRESH değerini 225-235 aralığında dene.\n"
            "   → HEX_AREA_MIN/MAX değerlerini ayarla."
        )

    # Ortalama yarıçap ile komşuluk mesafesini hesapla
    avg_r    = sum(c['r'] for c in candidates) / len(candidates)
    max_dist = avg_r * math.sqrt(3) * NEIGHBOR_TOLERANCE

    # Komşusu olmayan nesneler UI elemanlarıdır (alt butonlar vb.) — çıkar
    adj_count = defaultdict(int)
    for i, c1 in enumerate(candidates):
        for j, c2 in enumerate(candidates):
            if i >= j:
                continue
            if math.hypot(c1['cx'] - c2['cx'], c1['cy'] - c2['cy']) < max_dist:
                adj_count[i] += 1
                adj_count[j] += 1

    hexes = []
    for i, c in enumerate(candidates):
        if adj_count[i] > 0:
            hexes.append({'id': 0, 'cx': c['cx'], 'cy': c['cy'], 'r': c['r']})

    hexes.sort(key=lambda h: (h['cy'], h['cx']))
    for i, h in enumerate(hexes):
        h['id'] = i

    print(f"🔷  {len(hexes)} hexagon tespit edildi  (avg r={avg_r:.0f}px)")
    return hexes

def build_adjacency(hexes: list[dict]) -> dict[int, list[int]]:
    """Hexagonlar arası komşuluk grafiği oluştur."""
    if not hexes:
        return {}
    avg_r    = sum(h['r'] for h in hexes) / len(hexes)
    max_dist = avg_r * math.sqrt(3) * NEIGHBOR_TOLERANCE

    adj = {h['id']: [] for h in hexes}
    for i, h1 in enumerate(hexes):
        for j, h2 in enumerate(hexes):
            if i >= j:
                continue
            if math.hypot(h1['cx'] - h2['cx'], h1['cy'] - h2['cy']) < max_dist:
                adj[h1['id']].append(h2['id'])
                adj[h2['id']].append(h1['id'])
    return adj

# ────────────────────────────────────────────────────────────────────
#  Görüntü ön işleme — OCR ve şablon eşleştirme için ortak
# ────────────────────────────────────────────────────────────────────

def _crop_hex(img_bgr: np.ndarray, cx: int, cy: int, r: float) -> np.ndarray | None:
    """
    Hex merkezini kırp, normalize et.
    Döndürür: 100x100 gri-tonlamalı, normalize edilmiş görüntü.
    """
    pad = int(r * 0.58)
    x1  = max(0, cx - pad);  y1 = max(0, cy - pad)
    x2  = min(img_bgr.shape[1], cx + pad)
    y2  = min(img_bgr.shape[0], cy + pad)
    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    gray  = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    gray  = clahe.apply(gray)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Harfin siyah, zeminin beyaz olduğunu garantile
    if bw[bw.shape[0]//2, bw.shape[1]//2] == 0:
        bw = cv2.bitwise_not(bw)
    return cv2.resize(bw, (100, 100), interpolation=cv2.INTER_AREA)


# ────────────────────────────────────────────────────────────────────
#  Şablon eşleştirme (Template Matching) — birincil yöntem
# ────────────────────────────────────────────────────────────────────

_templates: dict[str, np.ndarray] = {}   # harf → 100x100 görüntü
_templates_loaded = False

def load_templates() -> bool:
    """
    TEMPLATE_DIR klasöründen şablonları yükle.
    Klasör yoksa veya boşsa False döndür.
    """
    global _templates, _templates_loaded
    if not os.path.isdir(TEMPLATE_DIR):
        return False
    _templates.clear()
    for fname in os.listdir(TEMPLATE_DIR):
        if not fname.endswith('.png'):
            continue
        letter = fname.replace('.png', '')
        if letter in TR_UPPER:
            path = os.path.join(TEMPLATE_DIR, fname)
            # cv2.imread Unicode yolu okuyamaz; fromfile+imdecode kullan
            buf = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                _templates[letter] = cv2.resize(img, (100, 100))
    _templates_loaded = True
    if _templates:
        print(f"📂  {len(_templates)} harf şablonu yüklendi: {sorted(_templates.keys())}")
    return bool(_templates)

def save_template(letter: str, crop_norm: np.ndarray):
    """Normalize edilmiş krop görüntüsünü şablon olarak kaydet.
    cv2.imwrite yerine imencode+open kullanilir: Windows'ta Unicode
    dosya adlari (Ş, Ç, İ, vb.) imwrite ile kaydilamaz."""
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    path = os.path.join(TEMPLATE_DIR, f"{letter}.png")
    ok, buf = cv2.imencode('.png', crop_norm)
    if ok:
        with open(path, 'wb') as f:
            f.write(buf.tobytes())

def match_letter_template(crop_norm: np.ndarray) -> tuple[str, float]:
    """
    Normalize edilmiş krop görüntüsünü tüm şablonlarla karşılaştır.
    Döndürür: (en iyi eşleşen harf, benzerlik skoru 0-1)
    NCC (Normalized Cross-Correlation) kullanılır: 1.0 = mükemmel eşleşme.
    """
    if not _templates:
        return '?', 0.0
    best_letter, best_score = '?', -1.0
    query = crop_norm.astype(np.float32)
    for letter, tmpl in _templates.items():
        # NCC: iki görüntünün piksel piksel korelasyonu
        result = cv2.matchTemplate(query, tmpl.astype(np.float32),
                                    cv2.TM_CCOEFF_NORMED)
        score = float(result[0][0])
        if score > best_score:
            best_score, best_letter = score, letter
    return best_letter, best_score

TEMPLATE_MIN_SCORE = 0.75



# ────────────────────────────────────────────────────────────────────
#  Şablon kurulum — bilinmeyen harf geldiğinde otomatik açılır
# ────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────
#  Ana harf okuma fonksiyonu
# ────────────────────────────────────────────────────────────────────

def teach_all(img_bgr, hexes):
    """
    --teach modu: ekrandaki tum hexleri sor, sablon kaydet.
    Mevcut sablonlar silinmez; guncellenmek istenmiyorsa Enter yeterli.
    """
    letters = {}
    print("\n  Ogretme modu: her hex icin Enter=mevcut sablonu koru, harf=guncelle\n")

    for h in sorted(hexes, key=lambda x: (x['cy'], x['cx'])):
        hid  = h['id']
        crop = _crop_hex(img_bgr, h['cx'], h['cy'], h['r'])
        if crop is None:
            letters[hid] = '?'
            continue

        # Mevcut sablon varsa goster
        if _templates:
            cur_ch, score = match_letter_template(crop)
            hint = f"mevcut sablon: '{cur_ch}' ({score:.2f})"
        else:
            cur_ch = '?'
            hint   = "sablon yok"

        try:
            raw = input(f"  hex_{hid:2d}  [{hint}]  ->  harf (Enter=koru): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Iptal edildi.")
            letters[hid] = cur_ch
            continue

        if raw.lower() == 'q':
            print("  Cikiliyor.")
            break

        if raw:
            confirmed = tr_upper(raw[0])
            if confirmed not in TR_UPPER:
                print(f"  '{raw}' gecersiz, atlandi.")
                letters[hid] = cur_ch
                continue
            save_template(confirmed, crop)
            _templates[confirmed] = crop
            letters[hid] = confirmed
            print(f"  OK  hex_{hid:2d} -> '{confirmed}' guncellendi.")
        else:
            # Enter: sadece mevcut degeri kullan, sablona dokunma
            letters[hid] = cur_ch

    saved = sorted(_templates.keys())
    print(f"\n  Toplam {len(saved)} sablon: {saved}\n")
    return letters


def read_all_letters(img_bgr, hexes, debug=False):
    """
    Her hex icin:
      1. Sablon eslestir (varsa ve skor yeterince yuksekse)
      2. Sablon yoksa veya skor dusukse: EasyOCR ile tahmin yap,
         terminalde goster, kullanicidan onayla/duzelt, kaydet.
    Boylece sablon kutuphanesi her calistirmada otomatik buyur.
    """
    letters = {}
    newly_saved = 0
    print("Harfler okunuyor...")

    for h in sorted(hexes, key=lambda x: (x['cy'], x['cx'])):
        hid  = h['id']
        crop = _crop_hex(img_bgr, h['cx'], h['cy'], h['r'])
        if crop is None:
            letters[hid] = '?'
            continue

        ch, score = match_letter_template(crop) if _templates else ('?', 0.0)

        if score >= TEMPLATE_MIN_SCORE:
            # Sablon guvenilir -> direkt kullan
            letters[hid] = ch
            if debug:
                print(f"  OK  hex_{hid:2d} -> '{ch}'  (sablon {score:.2f})")
        else:
            # Bilinmeyen harf -> kullanicidan al
            hint = f"en yakin: '{ch}' ({score:.2f})" if score > 0.2 else "sablon yok"
            try:
                raw = input(f"  hex_{hid:2d}  [{hint}]  ->  harfi gir: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Giris iptal edildi.")
                letters[hid] = '?'
                continue

            confirmed = tr_upper(raw[0]) if raw else '?'
            if not raw:
                letters[hid] = '?'
                continue
            if confirmed not in TR_UPPER:
                print(f"  '{raw}' gecersiz, '?' olarak isaretlendi.")
                letters[hid] = '?'
                continue
            letters[hid] = confirmed
            save_template(confirmed, crop)
            _templates[confirmed] = crop
            newly_saved += 1
            print(f"  OK  hex_{hid:2d} -> '{confirmed}' kaydedildi.")

    unknown = sum(1 for c in letters.values() if c == '?')
    if newly_saved:
        print(f"  {newly_saved} yeni sablon kaydedildi -> toplam {len(_templates)}: {sorted(_templates.keys())}")
    if unknown:
        print(f"  Uyari: {unknown} harf taninamadi (?)")
    return letters


# ────────────────────────────────────────────────────────────────────
#  Kelime arama — Trie + DFS
# ────────────────────────────────────────────────────────────────────

def find_words(letters: dict[int, str],
               adj:     dict[int, list[int]],
               trie:    Trie,
               min_len: int = 3) -> list[tuple[str, list[int]]]:
    """
    Trie destekli DFS: geçersiz prefixler anında budanır.
    Döndürür: [(kelime, [hex_id_yolu]), ...] uzunluğa göre azalan sırada
    """
    filled = {hid: ch for hid, ch in letters.items() if ch != '?'}
    found:  dict[str, list[int]] = {}

    def dfs(hid: int, visited: set, word: str, node: TrieNode, path: list):
        ch    = filled[hid]
        child = node.children.get(ch)
        if child is None:
            return   # bu prefixten kelime çıkmaz → dal buda
        new_word = word + ch
        path.append(hid)
        if child.is_end and len(new_word) >= min_len and new_word not in found:
            found[new_word] = list(path)
        for nb in adj.get(hid, []):
            if nb not in visited and nb in filled:
                visited.add(nb)
                dfs(nb, visited, new_word, child, path)
                visited.discard(nb)
        path.pop()

    for start in filled:
        dfs(start, {start}, '', trie.root, [])

    return sorted(found.items(), key=lambda x: -len(x[0]))

# ────────────────────────────────────────────────────────────────────
#  Gesture — uiautomator2 (birincil) + ADB fallback
# ────────────────────────────────────────────────────────────────────

def _swipe_u2(centers: list[tuple[int, int]]):
    """uiautomator2 ile sürekli tek-dokunuş swipe."""
    import uiautomator2 as u2
    d = u2.connect(DEVICE_ID)
    x0, y0 = centers[0]
    d.touch.down(x0, y0)
    time.sleep(0.05)
    for x, y in centers[1:]:
        d.touch.move(x, y)
        time.sleep(SWIPE_STEP_MS / 1000)
    d.touch.up(*centers[-1])

def _swipe_adb(centers: list[tuple[int, int]]):
    """ADB input swipe ile segment-segment swipe (fallback)."""
    per_ms = SWIPE_STEP_MS
    for i in range(len(centers) - 1):
        x1, y1 = centers[i]
        x2, y2 = centers[i + 1]
        _adb('shell', 'input', 'swipe',
             str(x1), str(y1), str(x2), str(y2), str(per_ms))

def execute_swipe(path_ids: list[int], hexes: list[dict],
                  dry_run: bool = False):
    """hex_id listesini piksel merkezlerine çevir ve swipe et."""
    id_to_hex = {h['id']: h for h in hexes}
    centers   = [(id_to_hex[hid]['cx'], id_to_hex[hid]['cy']) for hid in path_ids]
    print(f"👆  Swipe: {' → '.join(f'({x},{y})' for x,y in centers)}")

    if dry_run:
        print("   [DRY-RUN] Swipe yapılmadı.")
        return

    try:
        _swipe_u2(centers)
        print("   ✅  uiautomator2 ile swipe tamamlandı.")
    except Exception as e:
        print(f"   ⚠️  uiautomator2 hatası ({e}), ADB fallback kullanılıyor…")
        _swipe_adb(centers)
        print("   ✅  ADB swipe tamamlandı.")

# ────────────────────────────────────────────────────────────────────
#  Debug görüntüsü
# ────────────────────────────────────────────────────────────────────

def save_debug_image(img_bgr: np.ndarray, hexes: list[dict],
                     letters: dict[int, str], path: str = "debug_detected.png"):
    """Hexleri ve okunan harfleri anotasyonlu olarak kaydet."""
    out = img_bgr.copy()
    for h in hexes:
        cx, cy, r = h['cx'], h['cy'], int(h['r'])
        ch = letters.get(h['id'], '?')
        cv2.circle(out, (cx, cy), r, (0, 200, 0), 2)
        cv2.circle(out, (cx, cy), 4,  (0, 0, 255), -1)
        cv2.putText(out, f"{h['id']}:{ch}", (cx - r + 4, cy - r + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 80, 0), 2)
    cv2.imwrite(path, out)
    print(f"🖼   Debug görüntüsü kaydedildi: {path}")

# ────────────────────────────────────────────────────────────────────
#  İnteraktif harf doğrulama
# ────────────────────────────────────────────────────────────────────

def verify_letters(letters: dict[int, str], hexes: list[dict]) -> dict[int, str]:
    """
    Terminalde her hex'i göster; kullanıcı Enter'la onaylar
    veya doğru harfi yazarak düzeltir.
    --verify bayrağı ya da '?' olan harf varsa otomatik açılır.
    """
    print("\n✏️   Harf doğrulama — Enter = onayla, harf yaz = düzelt, q = çık")
    print("    (Değişmesi gerekenler '❓' ile işaretlidir)\n")
    corrected = dict(letters)
    for h in sorted(hexes, key=lambda x: (x['cy'], x['cx'])):
        hid = h['id']
        current = corrected.get(hid, '?')
        flag = '❓' if current == '?' else '  '
        try:
            raw = input(f"  {flag} hex_{hid:2d} → [{current}]  yeni harf (Enter=onayla): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n   Doğrulama iptal edildi.")
            break
        if raw.lower() == 'q':
            print("   Doğrulama çıkıldı.")
            break
        if raw:
            new_ch = tr_upper(raw[0])
            if new_ch in TR_UPPER:
                corrected[hid] = new_ch
                print(f"       ✅  hex_{hid} → '{new_ch}' olarak güncellendi.")
            else:
                print(f"       ⚠️  '{raw[0]}' Türkçe alfabede yok, değiştirilmedi.")
    print()
    return corrected


# ────────────────────────────────────────────────────────────────────
#  Ana orkestratör
# ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Word Master Otomatik Çözücü")
    parser.add_argument('--dry-run',    action='store_true',
                        help='Swipe yapmadan test et')
    parser.add_argument('--debug',      action='store_true',
                        help='Konturları ve harfleri yazdır, debug_detected.png kaydet')
    parser.add_argument('--all',         action='store_true',
                        help='Tüm kelimeleri sırayla oyna (uzundan kısaya)')
    parser.add_argument('--all_reverse', action='store_true',
                        help='Tüm kelimeleri sırayla oyna (kısadan uzuna)')
    parser.add_argument('--list',       action='store_true',
                        help='Kelimeleri listele, swipe yapma')
    parser.add_argument('--word',       type=str, default=None,
                        help='Belirli bir kelimeyi oyna (örnek: --word ZİT)')
    parser.add_argument('--screenshot', type=str, default=None,
                        help='Yeni çekmek yerine mevcut ekran görüntüsü kullan')
    parser.add_argument('--verify',      action='store_true',
                        help='Harfleri okuduktan sonra terminalde göster, yanlışları düzelt')
    parser.add_argument('--recalibrate', action='store_true',
                        help='Tum sablonlari sil, sifirdan ogren')
    parser.add_argument('--teach',       action='store_true',
                        help='Ekrandaki tum harfleri sor ve sablon olarak kaydet (mevcut data silinmez)')
    args = parser.parse_args()

    # 1. Trie yükle
    trie = load_trie(WORD_LIST_PATH)

    # 1b. Şablonları yükle (varsa)
    if getattr(args, 'recalibrate', False):
        import shutil as _shutil
        if os.path.isdir(TEMPLATE_DIR):
            _shutil.rmtree(TEMPLATE_DIR)
            print(f'🗑   Şablon klasörü silindi: {TEMPLATE_DIR}')
    load_templates()

    # 2. Ekran görüntüsü al (veya mevcut dosyayı kullan)
    if args.screenshot:
        img_path = args.screenshot
        print(f"📂  Mevcut görüntü kullanılıyor: {img_path}")
    else:
        img_path = take_screenshot(SCREENSHOT_PATH)

    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        sys.exit(f"❌  Görüntü okunamadı: {img_path}")
    print(f"   Görüntü boyutu: {img_bgr.shape[1]}x{img_bgr.shape[0]} px")

    # 3. Hexagonları tespit et
    hexes = detect_hexagons(img_bgr, debug=args.debug)
    adj   = build_adjacency(hexes)

    # 4. Harfleri oku
    # --teach: o ekrandaki TUM hexleri sor (mevcut sablonlar silinmez)
    if getattr(args, 'teach', False):
        letters = teach_all(img_bgr, hexes)
    else:
        letters = read_all_letters(img_bgr, hexes, debug=args.debug)

    # Debug görüntüsünü kaydet
    if args.debug:
        save_debug_image(img_bgr, hexes, letters)

    # Harfleri terminalde göster
    print("\n🔠  Tespit edilen tahta:")
    for h in sorted(hexes, key=lambda x: (x['cy'], x['cx'])):
        ch = letters.get(h['id'], '?')
        flag = '❓' if ch == '?' else '  '
        print(f"   {flag} hex_{h['id']:2d}  ({h['cx']:4d},{h['cy']:4d})  →  '{ch}'")

    # --verify: kullanıcı yanlış harfleri düzeltebilir
    if args.verify or any(c == '?' for c in letters.values()):
        letters = verify_letters(letters, hexes)


    # 5. Kelimeleri bul
    print("\n🔍  Kelimeler aranıyor…")
    results = find_words(letters, adj, trie, MIN_WORD_LENGTH)

    if not results:
        print("⚠️   Hiç kelime bulunamadı.")
        print("   Harfler doğru okunduysa kelime listesini kontrol et.")
        return

    # Uzunluğa göre grupla ve göster
    by_len: dict[int, list] = defaultdict(list)
    for word, path in results:
        by_len[len(word)].append((word, path))

    print(f"\n✅  Toplam {len(results)} kelime bulundu:\n")
    for length in sorted(by_len.keys(), reverse=True):
        wlist = by_len[length]
        print(f"  {length} harfli ({len(wlist)} adet):")
        for w, _ in wlist:
            print(f"    {w}")
    print()

    if args.list:
        return

    # 6. Swipe et
    # Eger bu turde kullanicidan harf girisi alindiysa (egitim/bilinmeyen harf)
    # ilk swipe oncesi kisa bir bekleme yap; kullanicinin telefona
    # odaklanmasi ve terminalden cikiyor olmasi icin.
    first_swipe_delay = 0
    if getattr(args, 'teach', False) or any(c == '?' for c in letters.values()):
        first_swipe_delay = 2.0
    elif sum(1 for c in letters.values() if c != '?') < len(hexes):
        first_swipe_delay = 1.5
    # Harf girisinin yapildigi durumlarda kullaniciya hazirlik suresi ver
    if first_swipe_delay > 0 and not args.dry_run:
        try:
            input(f'\n  Swipe baslamak uzere. Telefona gec ve Enter a bas... ')
        except (EOFError, KeyboardInterrupt):
            time.sleep(first_swipe_delay)
    if args.word:
        target = tr_upper(args.word)
        match  = [(w, p) for w, p in results if w == target]
        if not match:
            print(f"❌  '{target}' kelimesi tahta üzerinde bulunamadı.")
            return
        word, path = match[0]
        print(f"▶   Oynanacak kelime: {word}")
        execute_swipe(path, hexes, dry_run=args.dry_run)

    elif args.all or args.all_reverse:
        ordered = list(reversed(results)) if args.all_reverse else list(results)
        for i, (word, path) in enumerate(ordered):
            print(f"▶  [{i+1}/{len(ordered)}] {word}")
            execute_swipe(path, hexes, dry_run=args.dry_run)
            if not args.dry_run:
                time.sleep(0.05)   # oyun animasyonunun bitmesini bekle

    else:
        word, path = results[0]
        print(f"▶   En uzun kelime: {word}  ({len(word)} harf)")
        execute_swipe(path, hexes, dry_run=args.dry_run)


if __name__ == '__main__':
    main()