# 🔷 Hex Kelime Bulucu

**Word Master** ve benzeri hexagonal grid Türkçe kelime bulmaca oyunları için yardımcı masaüstü uygulaması. Tahtadaki harflerden oluşturulabilecek tüm geçerli Türkçe kelimeleri **Trie + DFS** algoritmasıyla hızlıca bulur.

> Bu uygulama Word Master ile resmi bir bağlantısı olmayan bağımsız bir açık kaynak projedir.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python) ![Tkinter](https://img.shields.io/badge/GUI-Tkinter-orange) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Ekran Görüntüsü

> Uygulamayı çalıştırıp tahtayı doldurduktan sonra buraya bir ekran görüntüsü ekleyebilirsin.

---

## Özellikler

- Tıklanabilir hexagonal tahta editörü — hücreye tıkla, harf bas
- Tahta boyutu serbestçe ayarlanabilir (satır × sütun)
- Türkçe karakterlerin tamamı desteklenir (Ç, Ğ, İ, Ö, Ş, Ü…)
- Kelime veritabanı Trie'ye yüklenir → arama anlık hızda
- Sonuçlar uzundan kısaya gruplandırılmış olarak listelenir
- Tahta `.hexgrid` dosyasına kaydedilip tekrar yüklenebilir

---

## Kurulum

Python 3.9 veya üzeri gereklidir. Harici bağımlılık yoktur; tkinter Python ile birlikte gelir.

```bash
# Repoyu klonla
git clone https://github.com/KULLANICI_ADIN/hex-kelime-bulucu.git
cd hex-kelime-bulucu

# Uygulamayı başlat
python hex_kelime_bulucu.py
```

> **Ubuntu / Debian** kullanıcıları tkinter eksikse:
> ```bash
> sudo apt-get install python3-tk
> ```

---

## Kelime Veritabanı

Repodaki `turkish_words.txt` dosyası TDK Güncel Türkçe Sözlük'ten derlenmiştir. Her satırda bir kelime, UTF-8 kodlamasında.

Uygulamayı açtıktan sonra sağ panelde **📁 TXT Dosyası Yükle** butonuyla dosyayı seç.

---

## Kullanım

| İşlem | Nasıl |
|---|---|
| Hücre seç | Tıkla |
| Harf gir | Hücreyi seçip klavyede harf tuşuna bas |
| Harf sil | `Backspace` veya `Delete` |
| Hücreler arası geçiş | `← → ↑ ↓` ok tuşları |
| Tahta boyutunu değiştir | Satır/Sütun kutularını ayarla → *Yeniden Boyutla* |
| Kelime ara | Veritabanını yükle → **🔍 Tüm Kelimeleri Bul** |

---

## Nasıl Çalışır

1. Tahta harfleri girildiğinde her hücrenin komşuları hesaplanır.
2. **Trie** — kelime veritabanı prefix ağacına yüklenir; geçersiz prefixler anında budanır.
3. **DFS** — her hücreden başlayarak komşulara derinlemesine gidilir; aynı hücreye iki kez geçilmez.
4. Bulunan kelimeler uzunluğa göre gruplanıp listelenir.

---

## Lisans

MIT
