#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔷 Türkçe Hex Kelime Bulucu
Hexagonal grid üzerinde Türkçe kelime bulan masaüstü uygulaması.
Trie + DFS ile hızlı arama.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math
import json
import os
import threading
from collections import defaultdict

# ──────────────────────────────────────────────────────────────────────────────
# Türkçe alfabe & normalizasyon
# ──────────────────────────────────────────────────────────────────────────────

TR_UPPER = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"
TR_LOWER = "abcçdefgğhıijklmnoöprsştuüvyz"

_TO_UPPER = {
    'a':'A','b':'B','c':'C','ç':'Ç','d':'D','e':'E','f':'F','g':'G',
    'ğ':'Ğ','h':'H','ı':'I','i':'İ','j':'J','k':'K','l':'L','m':'M',
    'n':'N','o':'O','ö':'Ö','p':'P','r':'R','s':'S','ş':'Ş','t':'T',
    'u':'U','ü':'Ü','v':'V','y':'Y','z':'Z',
    'A':'A','B':'B','C':'C','Ç':'Ç','D':'D','E':'E','F':'F','G':'G',
    'Ğ':'Ğ','H':'H','I':'I','İ':'İ','J':'J','K':'K','L':'L','M':'M',
    'N':'N','O':'O','Ö':'Ö','P':'P','R':'R','S':'S','Ş':'Ş','T':'T',
    'U':'U','Ü':'Ü','V':'V','Y':'Y','Z':'Z',
}

def tr_upper(s):
    return ''.join(_TO_UPPER.get(c, c.upper()) for c in s)


# ──────────────────────────────────────────────────────────────────────────────
# Trie
# ──────────────────────────────────────────────────────────────────────────────

class TrieNode:
    __slots__ = ('children', 'is_end')
    def __init__(self):
        self.children: dict = {}
        self.is_end: bool = False


class Trie:
    def __init__(self):
        self.root = TrieNode()
        self.word_count = 0

    def insert(self, word: str):
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        if not node.is_end:
            node.is_end = True
            self.word_count += 1


# ──────────────────────────────────────────────────────────────────────────────
# Renkler
# ──────────────────────────────────────────────────────────────────────────────

C = {
    'bg':           '#1A1C24',
    'panel':        '#22252F',
    'canvas_bg':    '#1E2130',
    'hex_empty':    '#2E3348',
    'hex_empty_dot':'#454D6B',
    'hex_filled':   '#EAE6D6',
    'hex_selected': '#F5A623',
    'hex_outline':  '#141620',
    'text_filled':  '#1A1C24',
    'text_empty':   '#454D6B',
    'text':         '#CDD3EE',
    'subtext':      '#6B738F',
    'accent':       '#5B9CF6',
    'success':      '#50C878',
    'danger':       '#FF5555',
    'warning':      '#FFA040',
}


# ──────────────────────────────────────────────────────────────────────────────
# Ana uygulama
# ──────────────────────────────────────────────────────────────────────────────

class HexWordApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🔷 Türkçe Hex Kelime Bulucu")
        self.root.configure(bg=C['bg'])
        self.root.minsize(1150, 680)
        self.root.geometry('1280x780')

        self.trie = Trie()
        self.words_loaded = False

        self.grid_rows = 5
        self.grid_cols = 5
        self.hex_size  = 44
        self.grid_data: dict = {}   # (row,col) → büyük harf
        self.hex_tags:  dict = {}
        self.selected:  tuple | None = None
        self._search_running = False

        self._build_ui()
        self._redraw_all()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        left = tk.Frame(self.root, bg=C['bg'])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12,5), pady=12)

        hdr = tk.Frame(left, bg=C['bg'])
        hdr.pack(fill=tk.X, pady=(0,8))
        tk.Label(hdr, text="🔷 HEX KELİME BULUCU",
                 bg=C['bg'], fg=C['accent'],
                 font=('Arial', 15, 'bold')).pack(side=tk.LEFT)

        ctrl = tk.Frame(left, bg=C['panel'])
        ctrl.pack(fill=tk.X, pady=(0,6), ipady=6)

        self._label(ctrl, "Satır:").pack(side=tk.LEFT, padx=(10,2))
        self.rows_var = tk.IntVar(value=5)
        self._spin(ctrl, self.rows_var, 2, 14).pack(side=tk.LEFT, padx=(0,10))

        self._label(ctrl, "Sütun:").pack(side=tk.LEFT, padx=(0,2))
        self.cols_var = tk.IntVar(value=5)
        self._spin(ctrl, self.cols_var, 2, 14).pack(side=tk.LEFT, padx=(0,10))

        self._btn(ctrl, "⬡ Yeniden Boyutla", self._resize,    C['accent']).pack(side=tk.LEFT, padx=3)
        self._btn(ctrl, "✕ Temizle",         self._clear,     C['danger']).pack(side=tk.LEFT, padx=3)
        self._btn(ctrl, "💾 Kaydet",          self._save_grid, '#8B5CF6').pack(side=tk.LEFT, padx=3)
        self._btn(ctrl, "📂 Yükle",           self._load_grid, '#0EA5E9').pack(side=tk.LEFT, padx=3)

        self._label(ctrl, "Boyut:").pack(side=tk.RIGHT, padx=(0,2))
        self.size_var = tk.IntVar(value=44)
        tk.Scale(ctrl, from_=28, to=70, variable=self.size_var,
                 orient=tk.HORIZONTAL, command=self._on_size_change,
                 bg=C['panel'], fg=C['text'],
                 highlightthickness=0, length=100, showvalue=False
                 ).pack(side=tk.RIGHT, padx=(0,8))

        canvas_wrap = tk.Frame(left, bg=C['canvas_bg'], bd=0)
        canvas_wrap.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_wrap, bg=C['canvas_bg'],
                                 highlightthickness=0, cursor='hand2')
        vs = tk.Scrollbar(canvas_wrap, orient=tk.VERTICAL,   command=self.canvas.yview)
        hs = tk.Scrollbar(canvas_wrap, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side=tk.RIGHT,  fill=tk.Y)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind('<Button-1>',   self._canvas_click)
        self.canvas.bind('<MouseWheel>', self._canvas_scroll)
        self.root.bind('<Key>', self._key_press)

        status_bar = tk.Frame(left, bg=C['panel'])
        status_bar.pack(fill=tk.X, pady=(5,0), ipady=5)
        self._label(status_bar, "Seçili:").pack(side=tk.LEFT, padx=(10,4))
        self.sel_lbl = tk.Label(status_bar, text="—  (bir hücreye tıklayın)",
                                 bg=C['panel'], fg=C['warning'], font=('Arial', 10))
        self.sel_lbl.pack(side=tk.LEFT)
        self._label(status_bar,
                    "  ·  Harf tuşu = yaz  ·  Boşluk/Del = sil  ·  ← → ↑ ↓ = gezin",
                    color=C['subtext']).pack(side=tk.LEFT)

        # ── Sağ panel ──────────────────────────────────────────────────────
        right = tk.Frame(self.root, bg=C['panel'], width=360)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,12), pady=12)
        right.pack_propagate(False)

        self._section(right, "KELİME VERİTABANI")

        self.db_lbl = tk.Label(right, text="❌  Henüz kelime yüklenmedi",
                                bg=C['panel'], fg=C['danger'],
                                font=('Arial', 10), wraplength=330, justify='left')
        self.db_lbl.pack(padx=14, anchor='w', pady=(0,6))

        db_btns = tk.Frame(right, bg=C['panel'])
        db_btns.pack(fill=tk.X, padx=14, pady=(0,6))
        self._btn(db_btns, "📁 TXT Dosyası Yükle",
                  self._load_words_file, C['accent']).pack(side=tk.LEFT)

        # Progress bar (başlangıçta gizli)
        self.pb_frame = tk.Frame(right, bg=C['panel'])
        self.pb_var = tk.DoubleVar()
        self.pb = ttk.Progressbar(self.pb_frame, variable=self.pb_var,
                                   maximum=100, length=330)
        self.pb.pack(padx=14, pady=4)

        self._sep(right)
        self._section(right, "ARAMA AYARLARI")

        opt_row = tk.Frame(right, bg=C['panel'])
        opt_row.pack(fill=tk.X, padx=14, pady=(0,8))
        self._label(opt_row, "Min. kelime uzunluğu:").pack(side=tk.LEFT)
        self.min_len_var = tk.IntVar(value=3)
        self._spin(opt_row, self.min_len_var, 2, 15).pack(side=tk.LEFT, padx=8)

        tk.Button(right, text="🔍   TÜM KELİMELERİ BUL",
                  command=self._find_words,
                  bg='#D97706', fg='white',
                  activebackground='#B45309', activeforeground='white',
                  font=('Arial', 13, 'bold'),
                  relief=tk.FLAT, pady=13, cursor='hand2'
                  ).pack(fill=tk.X, padx=14, pady=(0,10))

        self._sep(right)

        res_hdr = tk.Frame(right, bg=C['panel'])
        res_hdr.pack(fill=tk.X, padx=14, pady=(4,2))
        self._section_label(res_hdr, "BULUNAN KELİMELER").pack(side=tk.LEFT)
        self.count_lbl = tk.Label(res_hdr, text="", bg=C['panel'],
                                   fg=C['accent'], font=('Arial', 9, 'bold'))
        self.count_lbl.pack(side=tk.RIGHT)

        txt_frame = tk.Frame(right, bg=C['panel'])
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0,14))

        self.result_txt = tk.Text(txt_frame, bg='#141620', fg=C['text'],
                                   font=('Consolas', 10), state=tk.DISABLED,
                                   relief=tk.FLAT, padx=10, pady=10,
                                   wrap=tk.WORD, cursor='arrow')
        rscroll = tk.Scrollbar(txt_frame, command=self.result_txt.yview)
        self.result_txt.configure(yscrollcommand=rscroll.set)
        rscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_txt.pack(fill=tk.BOTH, expand=True)

        self.result_txt.tag_configure('title',   foreground='#F5A623',
                                       font=('Consolas', 11, 'bold'))
        self.result_txt.tag_configure('len_hdr', foreground=C['accent'],
                                       font=('Consolas', 10, 'bold'))
        self.result_txt.tag_configure('sep',     foreground=C['subtext'])
        self.result_txt.tag_configure('word',    foreground=C['text'])

    # ── Widget yardımcıları ────────────────────────────────────────────────

    def _label(self, parent, text, color=None):
        return tk.Label(parent, text=text, bg=parent['bg'],
                        fg=color or C['text'], font=('Arial', 10))

    def _spin(self, parent, var, lo, hi):
        return tk.Spinbox(parent, from_=lo, to=hi, textvariable=var,
                          width=4, font=('Arial', 10),
                          bg='#2E3348', fg=C['text'],
                          buttonbackground='#3D4466',
                          relief=tk.FLAT, highlightthickness=0)

    def _btn(self, parent, text, cmd, color):
        return tk.Button(parent, text=text, command=cmd,
                         bg=color, fg='white', activebackground=color,
                         font=('Arial', 9, 'bold'), relief=tk.FLAT,
                         padx=8, pady=5, cursor='hand2')

    def _sep(self, parent):
        tk.Frame(parent, bg=C['subtext'], height=1).pack(fill=tk.X, padx=14, pady=8)

    def _section(self, parent, text):
        self._section_label(parent, text).pack(padx=14, pady=(6,4), anchor='w')

    def _section_label(self, parent, text):
        return tk.Label(parent, text=text, bg=C['panel'],
                        fg=C['subtext'], font=('Arial', 8, 'bold'))

    # ── Hex geometrisi — FLAT-TOP ──────────────────────────────────────────
    #
    # Flat-top: düz kenar üstte/altta, köşe solda/sağda.
    # Sütunlar dikey düzgün hizalı; tek sütunlar aşağı kayar.
    #
    #   Col 0   Col 1   Col 2
    #   [  ]            [  ]
    #        [  ]
    #   [  ]            [  ]
    #        [  ]
    #   [  ]            [  ]

    def _hex_center(self, row, col):
        """Flat-top hex merkezini hesapla (odd-col-down offset)."""
        s  = self.hex_size
        # Sütun aralığı: 1.5 * s  (yatay)
        # Satır aralığı: sqrt(3) * s (dikey)
        # Tek sütunlar (1,3,5…) yarım satır aşağı kayar
        x = col * s * 1.5 + s + 20
        y = row * s * math.sqrt(3) + (col % 2) * (s * math.sqrt(3) / 2) \
            + s * math.sqrt(3) / 2 + 20
        return x, y

    def _hex_corners(self, cx, cy):
        """Flat-top altıgen köşeleri (açı offsetsiz, 0° = sağ)."""
        s   = self.hex_size
        pts = []
        for i in range(6):
            a = math.pi / 3 * i   # 0°, 60°, 120°, 180°, 240°, 300°
            pts.append((cx + s * math.cos(a),
                        cy + s * math.sin(a)))
        return pts

    def _neighbors(self, row, col):
        """
        Flat-top odd-col-down offset komşuları.

        Çift sütun (col % 2 == 0):
          Aynı sütun: (r-1, c), (r+1, c)
          Sol  sütun: (r-1, c-1), (r, c-1)
          Sağ  sütun: (r-1, c+1), (r, c+1)

        Tek sütun (col % 2 == 1):
          Aynı sütun: (r-1, c), (r+1, c)
          Sol  sütun: (r, c-1),  (r+1, c-1)
          Sağ  sütun: (r, c+1),  (r+1, c+1)
        """
        if col % 2 == 0:
            dirs = [(-1, 0), (1, 0), (-1, -1), (0, -1), (-1, 1), (0, 1)]
        else:
            dirs = [(-1, 0), (1, 0), (0, -1), (1, -1), (0, 1), (1, 1)]

        return [(row + dr, col + dc) for dr, dc in dirs
                if 0 <= row + dr < self.grid_rows
                and 0 <= col + dc < self.grid_cols]

    # ── Grid çizimi ───────────────────────────────────────────────────────

    def _redraw_all(self):
        self.canvas.delete('all')
        self.hex_tags.clear()
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                self._draw_hex(r, c)
        self._update_scroll_region()

    def _draw_hex(self, row, col):
        tag = f'hx_{row}_{col}'
        self.canvas.delete(tag)
        self.hex_tags[(row, col)] = tag

        cx, cy  = self._hex_center(row, col)
        corners = self._hex_corners(cx, cy)
        flat    = [v for pt in corners for v in pt]

        letter   = self.grid_data.get((row, col), '')
        selected = (row, col) == self.selected

        if selected:
            fill = C['hex_selected']
            tcol = C['text_filled']
        elif letter:
            fill = C['hex_filled']
            tcol = C['text_filled']
        else:
            fill = C['hex_empty']
            tcol = C['text_empty']

        self.canvas.create_polygon(flat, fill=fill,
                                   outline=C['hex_outline'], width=2, tags=tag)

        if letter:
            fsize = max(12, int(self.hex_size * 0.50))
            self.canvas.create_text(cx, cy, text=letter,
                                    font=('Arial', fsize, 'bold'),
                                    fill=tcol, tags=tag)
        else:
            self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3,
                                    fill=C['hex_empty_dot'], outline='', tags=tag)

    def _update_scroll_region(self):
        if self.grid_rows > 0 and self.grid_cols > 0:
            mx, my = self._hex_center(self.grid_rows - 1, self.grid_cols - 1)
            s = self.hex_size
            self.canvas.configure(
                scrollregion=(0, 0, mx + s * 2.5, my + s * 2.5))

    # ── Olaylar ──────────────────────────────────────────────────────────

    def _canvas_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        best_dist, best_cell = float('inf'), None
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                hx, hy = self._hex_center(r, c)
                d = math.hypot(cx - hx, cy - hy)
                if d < best_dist:
                    best_dist, best_cell = d, (r, c)

        if best_cell and best_dist < self.hex_size * 1.05:
            old = self.selected
            self.selected = best_cell
            if old:
                self._draw_hex(*old)
            self._draw_hex(*best_cell)
            r, c = best_cell
            self.sel_lbl.config(
                text=f"Satır {r+1}  ·  Sütun {c+1}"
                     + (f"  ·  '{self.grid_data[(r,c)]}'" if (r,c) in self.grid_data else ""))
            self.root.focus_set()

    def _canvas_scroll(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

    def _key_press(self, event):
        if self.selected is None:
            return
        row, col = self.selected

        nav_map = {
            'Left': (0,-1), 'Right': (0,1),
            'Up':   (-1,0), 'Down':  (1,0),
        }
        if event.keysym in nav_map:
            dr, dc = nav_map[event.keysym]
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.grid_rows and 0 <= nc < self.grid_cols:
                self._move_selection(nr, nc)
            return

        if event.keysym in ('BackSpace', 'Delete', 'space'):
            self.grid_data.pop(self.selected, None)
            self._draw_hex(*self.selected)
            self.sel_lbl.config(text=f"Satır {row+1}  ·  Sütun {col+1}")
            return

        ch = event.char
        if not ch:
            return
        up = tr_upper(ch)
        if up and up in TR_UPPER:
            self.grid_data[self.selected] = up
            self._draw_hex(*self.selected)
            nc, nr = col + 1, row
            if nc >= self.grid_cols:
                nc, nr = 0, row + 1
            if nr < self.grid_rows:
                self._move_selection(nr, nc)

    def _move_selection(self, nr, nc):
        old = self.selected
        self.selected = (nr, nc)
        if old:
            self._draw_hex(*old)
        self._draw_hex(nr, nc)
        self.sel_lbl.config(
            text=f"Satır {nr+1}  ·  Sütun {nc+1}"
                 + (f"  ·  '{self.grid_data[(nr,nc)]}'" if (nr,nc) in self.grid_data else ""))

    def _on_size_change(self, _=None):
        self.hex_size = self.size_var.get()
        self._redraw_all()

    # ── Grid işlemleri ────────────────────────────────────────────────────

    def _resize(self):
        self.grid_rows = self.rows_var.get()
        self.grid_cols = self.cols_var.get()
        self.grid_data = {k: v for k, v in self.grid_data.items()
                         if k[0] < self.grid_rows and k[1] < self.grid_cols}
        self.selected = None
        self.sel_lbl.config(text="—  (bir hücreye tıklayın)")
        self._redraw_all()

    def _clear(self):
        if messagebox.askyesno("Temizle", "Tüm harfleri silmek istiyor musunuz?"):
            self.grid_data.clear()
            self._redraw_all()
            self.sel_lbl.config(text="—  (bir hücreye tıklayın)")

    def _save_grid(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.hexgrid',
            filetypes=[('Hex Grid', '*.hexgrid'), ('JSON', '*.json')])
        if not path:
            return
        payload = {
            'rows': self.grid_rows, 'cols': self.grid_cols,
            'cells': {f"{r},{c}": v for (r,c), v in self.grid_data.items()}
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _load_grid(self):
        path = filedialog.askopenfilename(
            filetypes=[('Hex Grid', '*.hexgrid'), ('JSON', '*.json')])
        if not path:
            return
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        self.grid_rows = d['rows']
        self.grid_cols = d['cols']
        self.rows_var.set(self.grid_rows)
        self.cols_var.set(self.grid_cols)
        self.grid_data = {
            (int(k.split(',')[0]), int(k.split(',')[1])): v
            for k, v in d['cells'].items()
        }
        self.selected = None
        self._redraw_all()

    # ── Kelime veritabanı ─────────────────────────────────────────────────

    def _load_words_file(self):
        path = filedialog.askopenfilename(
            filetypes=[('Metin Dosyası', '*.txt'), ('Tüm Dosyalar', '*.*')],
            title="Türkçe kelime listesi seç")
        if path:
            threading.Thread(target=self._load_file_thread,
                             args=(path,), daemon=True).start()

    def _load_file_thread(self, path):
        self._ui(self.db_lbl, dict(text="⏳  Yükleniyor...", fg=C['warning']))
        self._show_pb()
        try:
            trie  = Trie()
            count = 0
            fsize = os.path.getsize(path)
            bread = 0
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    bread += len(line.encode('utf-8', errors='replace'))
                    w = tr_upper(line.strip())
                    if 2 <= len(w) <= 25 and all(c in TR_UPPER for c in w):
                        trie.insert(w)
                        count += 1
                    if count % 10_000 == 0:
                        self.pb_var.set(min(99, bread / fsize * 100))
            self.trie = trie
            self.words_loaded = True
            self.pb_var.set(100)
            self._ui(self.db_lbl,
                     dict(text=f"✅  {count:,} Türkçe kelime yüklendi", fg=C['success']))
        except Exception as e:
            self._ui(self.db_lbl, dict(text=f"❌  Hata: {e}", fg=C['danger']))
        finally:
            self.root.after(2500, self._hide_pb)

    # ── Kelime arama (Trie + DFS) ─────────────────────────────────────────

    def _find_words(self):
        if not self.words_loaded:
            messagebox.showwarning(
                "Veritabanı Eksik",
                "Önce bir kelime veritabanı yükleyin.\n\n"
                "📁 TXT Dosyası Yükle: Her satırda bir kelime olacak\n"
                "şekilde bir .txt dosyası seçin.")
            return

        filled = {k: v for k, v in self.grid_data.items() if v}
        if len(filled) < 2:
            messagebox.showwarning("Yetersiz Harf",
                                   "Lütfen haritaya en az 2 harf girin.")
            return

        if self._search_running:
            return
        self._search_running = True

        self._write_result("🔍  Aranıyor…\n", clear=True)
        self.count_lbl.config(text="")

        min_len = self.min_len_var.get()
        threading.Thread(target=self._search_thread,
                         args=(dict(filled), min_len), daemon=True).start()

    def _search_thread(self, filled: dict, min_len: int):
        found: set = set()
        trie_root = self.trie.root

        adj: dict = {
            cell: [n for n in self._neighbors(*cell) if n in filled]
            for cell in filled
        }

        def dfs(cell, visited, word, node):
            letter = filled[cell]
            child  = node.children.get(letter)
            if child is None:
                return
            new_word = word + letter
            if child.is_end and len(new_word) >= min_len:
                found.add(new_word)
            for nb in adj[cell]:
                if nb not in visited:
                    visited.add(nb)
                    dfs(nb, visited, new_word, child)
                    visited.discard(nb)

        for start_cell in filled:
            dfs(start_cell, {start_cell}, '', trie_root)

        self._search_running = False
        self.root.after(0, lambda: self._show_results(found))

    def _show_results(self, words: set):
        by_len = defaultdict(list)
        for w in words:
            by_len[len(w)].append(w)

        total = len(words)
        self.count_lbl.config(text=f"{total:,} kelime")

        self.result_txt.configure(state=tk.NORMAL)
        self.result_txt.delete('1.0', tk.END)

        if not words:
            self.result_txt.insert(tk.END,
                "Hiç kelime bulunamadı.\n\nİpucu: haritadaki harfleri kontrol edin\n"
                "ve veritabanının doğru yüklendiğinden emin olun.", 'sep')
            self.result_txt.configure(state=tk.DISABLED)
            return

        self.result_txt.insert(tk.END, f"Toplam  {total:,}  kelime bulundu\n", 'title')
        self.result_txt.insert(tk.END, '─' * 34 + '\n', 'sep')

        for length in sorted(by_len.keys(), reverse=True):
            wlist = sorted(by_len[length])
            self.result_txt.insert(tk.END,
                f"\n  {length} harfli  ·  {len(wlist)} kelime\n", 'len_hdr')
            self.result_txt.insert(tk.END, '  ' + '─' * 28 + '\n', 'sep')
            for w in wlist:
                self.result_txt.insert(tk.END, f"  {w}\n", 'word')

        self.result_txt.configure(state=tk.DISABLED)
        self.result_txt.see('1.0')

    # ── Yardımcılar ──────────────────────────────────────────────────────

    def _ui(self, widget, kw: dict):
        self.root.after(0, lambda: widget.config(**kw))

    def _write_result(self, text: str, clear=False):
        self.result_txt.configure(state=tk.NORMAL)
        if clear:
            self.result_txt.delete('1.0', tk.END)
        self.result_txt.insert(tk.END, text)
        self.result_txt.configure(state=tk.DISABLED)

    def _show_pb(self):
        self.pb_var.set(0)
        self.root.after(0, lambda: self.pb_frame.pack(fill=tk.X, padx=14, pady=(0,6)))

    def _hide_pb(self):
        self.pb_frame.pack_forget()


# ──────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.geometry('1280x780')
    root.resizable(True, True)
    HexWordApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
