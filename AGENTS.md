# jfinder — Geliştirme Talimatı

Bu dosya, `jfinder` paketini sıfırdan yazacak coding agent için spesifikasyondur.
Sırayla ilerle, her milestone sonunda testleri çalıştır ve commit at.

---

## 1. Amaç

Araştırmacı, proje klasöründe bir `abstract.md` dosyası oluşturur ve terminalde
`jfinder find` çalıştırır. Araç, yayına uygun 5 dergiyi gerekçeleriyle birlikte
terminalde tablo olarak gösterir.

**Kritik tasarım kararı:** Dergi seçimini LLM yapmaz. LLM yalnızca (a) abstract'tan
yapılandırılmış bir profil çıkarır ve (b) yerel arama ile bulunmuş adayları yeniden
sıralar. Aday listesi her zaman yerel veri dosyasından gelir. Bu, halüsinasyon
riskini ortadan kaldırır.

**Non-goals (v0.1'de YAPMA):**
- Web arayüzü
- Kabul oranı / hakem süresi tahmini (bu veri açık kaynaklarda yok)
- Kullanıcı hesabı, telemetri, herhangi bir sunucu bileşeni
- Otomatik klasör tarama (bilinçli olarak kaldırıldı)

---

## 2. Teknoloji

- Python >= 3.10
- CLI: `typer`
- Tablo/çıktı: `rich`
- Veri: `pandas` + `pyarrow` (parquet)
- Arama: `rank_bm25`
- LLM: `openai` SDK, NVIDIA NIM endpoint'ine yönlendirilmiş
- Test: `pytest`
- Lint/format: `ruff`
- Paketleme: `hatchling`, `pyproject.toml`

Opsiyonel extra `[docs]`: `pypdf`, `python-docx`

---

## 3. Dosya yapısı

```
jfinder/
├── pyproject.toml
├── README.md
├── LICENSE                 # MIT (kod)
├── DATA.md                 # veri kaynakları + çekilme tarihi
├── jfinder/
│   ├── __init__.py
│   ├── cli.py              # typer app, komutlar
│   ├── input.py            # abstract.md bulma, okuma, doğrulama
│   ├── data.py             # parquet yükleme, filtreler
│   ├── retrieve.py         # BM25 shortlist
│   ├── llm.py              # NIM client, profile(), rerank()
│   ├── render.py           # rich tablo + gerekçe bloğu + json çıktı
│   ├── cache.py            # abstract hash → sonuç cache
│   └── data/
│       └── journals.parquet
├── scripts/
│   └── build_index.py      # OpenAlex'ten parquet üretir (runtime'da ÇAĞRILMAZ)
└── tests/
    ├── fixtures/
    │   ├── abstract_good.md
    │   ├── abstract_template.md
    │   ├── abstract_short.md
    │   └── journals_mini.parquet   # 200 satır
    ├── test_input.py
    ├── test_data.py
    ├── test_retrieve.py
    ├── test_llm.py         # HTTP mock'lu
    └── test_cli.py
```

---

## 4. Veri sözleşmesi

`jfinder/data/journals.parquet` şeması. Kod bu kolonlara güvenir; eksikse
anlaşılır hata ver.

| kolon | tip | açıklama |
|---|---|---|
| `openalex_id` | str | `S137773608` |
| `name` | str | dergi adı |
| `issn_l` | str | linking ISSN |
| `issn` | list[str] | tüm ISSN'ler |
| `publisher` | str | host organization adı |
| `country` | str | ISO-2, null olabilir |
| `topics` | list[str] | konu etiketleri, BM25 için |
| `h_index` | int | |
| `citedness_2y` | float | |
| `works_count` | int | |
| `quartile` | str | `Q1`–`Q4`, alan-içi hesaplanmış |
| `is_oa` | bool | |
| `in_doaj` | bool | |
| `apc_usd` | float | null = bilinmiyor (ücretsiz DEĞİL) |
| `built_at` | str | ISO tarih, tüm satırlarda aynı |

`scripts/build_index.py` bu dosyayı OpenAlex `/sources` endpoint'inden cursor
pagination ile üretir. Filtre: `type:journal,works_count:>100`.
Quartile'ı **alan içinde** hesapla: birincil topic'e göre grupla, her grupta
`h_index` üzerinden `qcut(4)`.

---

## 5. Maliyet sınıflandırması

Bu projenin en kolay yanlış yapılan yeri. Üç ayrı kavram var, karıştırma:

```python
def cost_class(row) -> str:
    if row.is_oa and row.apc_usd and row.apc_usd > 0:
        return "oa_paid"          # OA, yazar öder
    if row.is_oa and row.in_doaj and (pd.isna(row.apc_usd) or row.apc_usd == 0):
        return "diamond"          # OA, kimse ödemez
    if row.is_oa:
        return "oa_unknown"       # OA ama APC bilgisi yok
    return "subscription"         # abonelik; yazar ödemez, okuyucu öder
```

`--cost` seçenekleri:

| değer | kapsanan sınıflar |
|---|---|
| `free-to-publish` | `diamond`, `subscription` |
| `free-to-read` | `oa_paid`, `diamond`, `oa_unknown` |
| `all` (varsayılan) | hepsi |

`apc_usd` null olması **ücretsiz anlamına gelmez**, sadece DOAJ'da kayıt yok
demektir. `oa_unknown` sınıfı çıktıda "APC bilinmiyor" olarak gösterilir,
asla "ücretsiz" denmez.

Hybrid dergiler (abonelik + opsiyonel OA ücreti) `subscription` olarak sınıflanır;
çıktıda "hybrid OA seçeneği olabilir" notu düşülür.

---

## 6. Girdi (`input.py`)

Öncelik sırası:

1. `--text/-t "..."` — doğrudan metin
2. `--file/-f <path>` — belirli dosya
3. Çalışma dizininde (veya verilen `path` içinde) sırayla:
   `abstract.md`, `abstract.txt`, `ABSTRACT.md`

Hiçbiri yoksa `typer.BadParameter` ile şu mesaj:

```
<dizin> içinde abstract.md bulunamadı.

  Oluştur:  jfinder init
  Veya:     jfinder find -f path/to/abstract.txt
```

### `jfinder init` şablonu

```markdown
# Title
<çalışmanın başlığı>

# Abstract
<200-300 kelime: amaç, yöntem, bulgular, sonuç>

# Keywords
<virgülle ayrılmış, 4-8 adet>

# Study type
<ör: methods paper / RCT / retrospective cohort / review / case report>

# Notes (opsiyonel)
<hedef kitle, dil kısıtı, süre baskısı, kaçınmak istediğin yayıncılar>
```

`init` var olan dosyanın üzerine yazmaz; `--force` gerekir.

### Doğrulama

- İçerikte `<...>` yer tutucusu varsa → hata: "şablon doldurulmamış"
- < 60 kelime → hata
- \> 900 kelime → sarı uyarı, devam eder
- `# Notes` bölümü varsa ayrı parse edilir ve rerank prompt'una geçirilir

### Format okuma

`read_any(path)`: `.md/.txt/.tex/.rst` doğrudan; `.pdf` → `pypdf` (ilk 6 sayfa);
`.docx` → `python-docx`. Extra kurulu değilse: "pip install jfinder[docs]" öner.

---

## 7. LLM katmanı (`llm.py`)

```python
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
                api_key=os.environ["NVIDIA_API_KEY"])
MODEL = os.getenv("JFINDER_MODEL", "deepseek-ai/deepseek-v3.1")
```

Key yoksa program başında net hata ver:

```
NVIDIA_API_KEY tanımlı değil.
Ücretsiz key: https://build.nvidia.com  →  Get API Key
  export NVIDIA_API_KEY=nvapi-...
```

`--model` flag'i `JFINDER_MODEL`'i ezer. Model id'sini koda gömme — NIM kataloğu
sık değişiyor.

### JSON parse dayanıklılığı

Reasoning modelleri `<think>...</think>` bloğu döndürebilir ve markdown fence
ekleyebilir. Ortak yardımcı yaz:

```python
def parse_json(raw: str) -> dict:
    t = raw.split("</think>")[-1]
    t = t.replace("```json", "").replace("```", "")
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise LLMError("Model JSON döndürmedi")
    return json.loads(t[i:j + 1])
```

Parse hatasında bir kez `temperature=0` ile retry et, yine olmazsa
`--offline` sonucuna düş ve kullanıcıya bunu söyle.

### `profile(text) -> dict`

Şema:
```json
{"field": str, "subfields": [str], "study_type": str,
 "keywords": [str], "audience": str, "novelty_1_5": int, "summary": str}
```

### `rerank(profile, candidates, notes, k) -> dict`

Adayları `{"i": int, "name":..., "topics":..., "quartile":..., "cost":...}`
olarak ver. Sistem prompt'unda **açıkça** belirt: sadece verilen listeden seç,
yeni dergi adı üretme, `i` alanı listedeki indeks olmalı.

Şema:
```json
{"picks": [{"i": int, "fit": int, "why": str, "risk": str}]}
```

Dönen `i` değerlerini doğrula: aralık dışındaysa veya tekrar ediyorsa o kaydı at
ve BM25 sırasından tamamla. Kullanıcıya kaç tanesinin düzeltildiğini söyleme
gereği yok, ama `--verbose` ile logla.

---

## 8. Arama (`retrieve.py`)

```python
def shortlist(df, profile, n=40):
    corpus = (df["name"] + " " + df["topics"].str.join(" ")).str.lower().str.split()
    bm25 = BM25Okapi(corpus.tolist())
    q = " ".join([profile["field"], *profile["subfields"],
                  *profile["keywords"]]).lower().split()
    return df.assign(_score=bm25.get_scores(q)).nlargest(n, "_score")
```

Sıra önemli: **önce maliyet/quartile filtresi, sonra BM25**. Tersi olursa
filtre sonrası aday sayısı 5'in altına düşebilir. Filtre sonrası df boşsa
anlaşılır hata ver.

---

## 9. Predatory bayrağı

Kesin liste yok, heuristik kullan ve bunu çıktıda **açıkça belirt**:

```python
def flag(row) -> str | None:
    if not row.in_doaj and row.is_oa and (row.apc_usd or 0) > 1500 and row.h_index < 15:
        return "unverified"
    return None
```

Bayraklı dergiler varsayılan olarak listeden çıkarılır. Alt bilgide sayısı
yazılır: `⚠ 3 aday elendi (--show-flagged ile göster)`. Sessizce eleme yapma.

Bu bir suçlama değil, bir uyarı. Metinde "predatory" kelimesini kullanma,
"doğrulanmamış / DOAJ'da kayıtlı değil" de.

---

## 10. CLI arayüzü

```
jfinder init [PATH] [--force]
jfinder find [PATH] [-f FILE] [-t TEXT] [-k 5]
             [--cost all|free-to-publish|free-to-read]
             [--max-apc N] [--quartile Q1,Q2]
             [--show-flagged] [--offline] [--json] [--model ID]
             [--no-cache] [--verbose]
jfinder info          # index tarihi, dergi sayısı, model, key durumu
```

`--offline`: LLM'e hiç gitmez. Profil yerine abstract'ın kendi kelimelerini
BM25 sorgusu yapar, gerekçe üretmez, sadece tabloyu basar. Key'i olmayan
kullanıcı da araçtan faydalanabilmeli.

`--json`: tabloyla aynı veriyi stdout'a JSON verir, `rich` çıktısı stderr'e
gider. `jq` ile boru hattına sokulabilmeli.

`built_at` 12 aydan eskiyse çıktı altında sarı uyarı bas.

---

## 11. Cache (`cache.py`)

Anahtar: `sha256(abstract_text + model_id)`. Konum:
`platformdirs.user_cache_dir("jfinder")`. Profil ve rerank sonucu ayrı
saklanır — filtre değişince rerank yeniden çalışır ama profil çağrısı tekrar
etmez. `--no-cache` atlar.

---

## 12. Çıktı formatı

Örnek hedef:

```
                          Top 5 target journals
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━┳━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ # ┃ Journal                ┃ Q  ┃ Fit ┃ Cost          ┃ Flags ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━╇━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 1 │ Briefings in Bioinf.   │ Q1 │  91 │ Subscription  │       │
│ 2 │ BMC Bioinformatics     │ Q2 │  82 │ OA  $2,690    │ DOAJ  │
└───┴────────────────────────┴────┴─────┴───────────────┴───────┘

1. Briefings in Bioinformatics                         fit 91
   ▸ <why — tek cümle>
   ⚠ <risk — tek cümle>

  Index built 2026-08-01 · APC data from OpenAlex/DOAJ, list prices only
  Always verify aims & scope on the journal site before submitting.
```

Alt bilgi satırı her zaman basılır. Araç bir öneri aracı, karar aracı değil;
çıktı bunu yansıtmalı.

---

## 13. Lisans

- Kod: MIT (`LICENSE`)
- Veri: `journals.parquet` OpenAlex kaynaklı (CC0). `DATA.md`'de kaynak,
  endpoint, filtre ve çekilme tarihi yazılı olmalı.
- **SCImago kaynaklı hiçbir kolon repoya girmez** (SJR, SJR quartile,
  Scimago kategorileri, cites-per-doc). SCImago verisi non-commercial
  kısıtlıdır ve MIT ile çelişir. Quartile alan-içi h-index'ten hesaplanır.

README'de gizlilik notu bulunmalı: abstract yalnızca kullanıcının kendi API
key'iyle NVIDIA'ya gider; başka hiçbir yere veri gönderilmez, telemetri yoktur.

---

## 14. Testler

`tests/fixtures/journals_mini.parquet` (200 satır) ile çalış, gerçek veri dosyasına
dokunma. LLM çağrılarını mock'la — testler ağ erişimi ve API key gerektirmemeli.

Kapsanacak durumlar:

- `abstract.md` yok → doğru hata mesajı
- şablon doldurulmamış → hata
- 40 kelimelik abstract → hata
- 1200 kelimelik abstract → uyarı ama devam
- `--cost free-to-publish` → sonuçta hiç `oa_paid` yok
- `--cost free-to-publish` → `subscription` ve `diamond` var
- `apc_usd` null olan dergi "ücretsiz" olarak etiketlenmiyor
- filtre sonrası 0 aday → anlaşılır hata, traceback değil
- LLM aralık dışı `i` döndürüyor → çökmüyor, BM25'ten tamamlıyor
- LLM bozuk JSON döndürüyor → retry, sonra offline'a düşüyor
- `--offline` → hiç HTTP çağrısı yapılmıyor
- `--json` → geçerli JSON, stdout'ta rich çıktısı yok
- flagged dergiler varsayılan gizli, `--show-flagged` ile görünür

---

## 15. Milestone sırası

Her adımda çalışan bir şey olsun; büyük patlama yapma.

1. **İskelet** — `pyproject.toml`, paket yapısı, `jfinder info` çalışıyor
2. **Veri** — `scripts/build_index.py`, `data.py`, `cost_class`, filtreler + testleri
3. **Girdi** — `init`, `input.py`, doğrulama + testleri
4. **Offline arama** — `retrieve.py` + `render.py`; `jfinder find --offline` uçtan uca çalışıyor
5. **LLM** — `llm.py`, profile + rerank, mock'lu testler
6. **Cilalama** — cache, `--json`, flags, uyarılar, README, DATA.md

4. adımdan sonra araç key olmadan kullanılabilir olmalı. Bu bilinçli: LLM
katmanı bir iyileştirme, bir bağımlılık değil.

---

## 16. Uymanı istediğim kurallar

- Her fonksiyonda tip anotasyonu
- Kullanıcıya asla ham traceback gösterme; `typer.BadParameter` veya
  yakalanmış hata + eylem önerisi
- Ağ çağrılarında timeout ve tek retry
- `print` yok, `rich.console` kullan; JSON modunda stderr'e ayır
- Yorumlar İngilizce, kullanıcıya görünen mesajlar İngilizce (README Türkçe+İngilizce)
- Bir milestone bitmeden diğerine geçme, her milestone sonunda `pytest` yeşil olsun
