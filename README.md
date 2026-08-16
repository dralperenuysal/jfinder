# jfinder

A CLI that suggests target journals for your paper abstract, grounded in local OpenAlex data.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Data: OpenAlex CC0](https://img.shields.io/badge/data-OpenAlex%20CC0-green.svg)](DATA.md)

<details>
<summary>🇹🇷 Türkçe</summary>

Bir abstract'tan yayına uygun dergi öneren, yerel veri tabanlı komut satırı aracı.

Dergi seçimini **LLM yapmaz**: LLM yalnızca (a) abstract'tan yapılandırılmış bir
profil çıkarır ve (b) yerel BM25 aramasının bulduğu adayları yeniden sıralar.
Aday listesi her zaman yerel `journals.parquet` dosyasından gelir — halüsinasyon
riski yoktur. LLM katmanı isteğe bağlı bir iyileştirmedir; araç `--offline` ile
API key'siz de çalışır.

### Kurulum

```bash
pip install .                # normal kurulum
pip install -e ".[dev]"      # geliştirme (test + lint)
pip install ".[docs]"        # opsiyonel: pdf/docx abstract okumak için
```

### Quick start

```bash
jfinder init                 # çalışma dizininde abstract.md şablonu oluşturur
# şablonu doldur, sonra:

jfinder find                 # 5 dergi önerir (LLM + gerekçeler)
jfinder find --offline       # LLM'siz: BM25 + abstract'ın kendi kelimeleri
jfinder find --json | jq '.journals[].name'   # JSON çıktısı (stdout)
jfinder find --report        # düz metin liste: tam dergi adları, tablo yok
jfinder key                  # kayıtlı API key durumu (ilk çalıştırmada sorulur)
jfinder info                 # index tarihi, dergi sayısı, model, key durumu
```

### Örnek çıktı

```
Top 3 target journals
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━┳━━━━━┳━━━━━━━━━━━━━━┳━━━━━┓
┃ # ┃ Journal                ┃ Q  ┃ Fit ┃ Cost         ┃ Flags┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━╇━━━━━╇━━━━━━━━━━━━━━╇━━━━━┩
│ 1 │ JMIR Medical Informat.  │ Q1 │  95 │ OA  $2,300   │ DOAJ │
│ 2 │ JAMIA                   │ Q1 │  90 │ Subscription │ hybrid OA possible │
│ 3 │ npj Digital Medicine    │ Q1 │  88 │ OA  $3,590   │ DOAJ │
└───┴────────────────────────┴────┴─────┴──────────────┴─────┘

1. JMIR Medical Informatics                          fit 95
   ▸ High relevance to clinical informatics and ML in healthcare...
   ⚠ May have a slower first decision than specialized journals.

  ⚠ 11 candidates removed as unverified (show with --show-flagged)
  Index built 2026-08-16 · APC data from OpenAlex/DOAJ, list prices only
  Always verify aims & scope on the journal site before submitting.
```

### Filtreler

- `--cost all|free-to-publish|free-to-read|diamond` — varsayılan `all`
- `--max-apc N` — USD cinsinden üst sınır (APC'si **bilinmeyen** dergiler elenmez; "bilinmiyor" ≠ "ücretsiz")
- `--quartile Q1,Q2` — alan-içi h-index quartile'ı
- `--show-flagged` — varsayılan olarak gizlenen "unverified" dergileri göster
- `-k N` — gösterilecek dergi sayısı (varsayılan 5)
- `--report` — tablo yerine düz metin liste; dergi adları kırpılmadan tam gösterilir

### LLM

- Model: `JFINDER_MODEL` ortam değişkeni veya `--model` flag'i (varsayılan: `deepseek-ai/deepseek-v4-flash-0731`)
- API key (ücretsiz: https://build.nvidia.com):
  - İlk `jfinder find` çalıştırmasında key yoksa araç yapıştırmanızı ister ve `~/.config/jfinder/config.json` dosyasına kaydeder (0600 izinli); boş geçip offline devam edebilirsiniz
  - `NVIDIA_API_KEY` ortam değişkeni her zaman config dosyasından önceliklidir
  - Yönetim: `jfinder key --set` / `--remove` / `jfinder key` (durum)
- LLM başarısız olursa araç otomatik olarak offline sıralamaya düşer
- Sonuçlar cache'lenir (`--no-cache` ile atlanır); filtre değişince yalnızca yeniden sıralama yeniden çalışır

### Gizlilik

Abstract yalnızca **kendi NVIDIA_API_KEY'inizle** NVIDIA NIM'e gönderilir.
Başka hiçbir yere veri gönderilmez; telemetri yoktur; sonuçlar yerel cache
dizininde saklanır.

### Veri ve lisans

- Kod: MIT (`LICENSE`)
- Dergi verisi: OpenAlex (CC0) — ayrıntılar için `DATA.md`

**Not:** Bu araç bir öneri aracıdır, karar aracı değildir. Gönderim öncesinde
derginin aims & scope'unu kendi sitesinden doğrulayın.

</details>

<details>
<summary>🇬🇧 English</summary>

`jfinder` suggests target journals for a paper abstract, grounded in local
OpenAlex data. The LLM never picks journals: it only (a) extracts a structured
profile from the abstract and (b) reranks candidates found by local BM25
search. Candidates always come from the bundled `journals.parquet`. The LLM
layer is an optional refinement — the tool works with `--offline` and no API
key.

### Install

```bash
pip install .                # regular install
pip install -e ".[dev]"      # development (tests + lint)
pip install ".[docs]"        # optional: pdf/docx abstract reading
```

### Quick start

```bash
jfinder init                 # create an abstract.md template
# fill in the template, then:

jfinder find                 # top 5 journals with fit scores and reasons
jfinder find --offline       # no LLM: BM25 over the abstract's own words
jfinder find --json | jq '.journals[].name'   # JSON output (stdout)
jfinder find --report        # plain-text list: full journal names, no table
jfinder key                  # stored API key status (prompted on first run)
jfinder info                 # index date, journal count, model, key status
```

### Filters

- `--cost all|free-to-publish|free-to-read|diamond` — default `all`
- `--max-apc N` — max APC in USD (journals with an **unknown** APC are kept; unknown ≠ free)
- `--quartile Q1,Q2` — within-field h-index quartile
- `--show-flagged` — include journals flagged as unverified (hidden by default)
- `-k N` — number of journals to show (default 5)
- `--report` — plain-text list instead of the table; journal names are never truncated

### LLM

- Model: `JFINDER_MODEL` env var or `--model` flag (default: `deepseek-ai/deepseek-v4-flash-0731`)
- API key (free: https://build.nvidia.com):
  - On the first `jfinder find` without a key, the tool asks you to paste one and stores it in `~/.config/jfinder/config.json` (0600); press Enter to continue offline
  - The `NVIDIA_API_KEY` env var always takes precedence over the stored key
  - Manage it: `jfinder key --set` / `--remove` / `jfinder key` (status)
- If the LLM fails, the tool automatically falls back to offline ranking
- Results are cached (`--no-cache` skips); changing filters reruns only the rerank

### Privacy

The abstract is sent only to NVIDIA NIM with your own `NVIDIA_API_KEY`.
No telemetry; nothing else leaves the machine; results live in the local cache.

### Data and license

- Code: MIT (`LICENSE`)
- Journal data: OpenAlex (CC0) — see `DATA.md`

**Note:** this is a suggestion tool, not a decision tool — always verify aims &
scope on the journal site before submitting.

</details>

---

**Yazar / Author:** [Alperen Uysal, MD, PhD](https://github.com/dralperenuysal)
