# jfinder

Bir abstract'tan yayına uygun dergi öneren, yerel veri tabanlı komut satırı aracı.

Dergi seçimini **LLM yapmaz**: LLM yalnızca (a) abstract'tan yapılandırılmış bir
profil çıkarır ve (b) yerel BM25 aramasının bulduğu adayları yeniden sıralar.
Aday listesi her zaman yerel `journals.parquet` dosyasından gelir — halüsinasyon
riski yoktur. LLM katmanı isteğe bağlı bir iyileştirmedir; araç `--offline` ile
API key'siz de çalışır.

---

## Kurulum

```bash
pip install -e ".[dev]"          # geliştirme (test + lint)
# opsiyonel: pdf/docx abstract okumak için
pip install "jfinder[docs]"
```

## Kullanım

```bash
jfinder init            # çalışma dizininde abstract.md şablonu oluşturur
# şablonu doldur, sonra:

jfinder find            # abstract.md'yi bulur, 5 dergi önerir (LLM ile)
jfinder find --offline  # LLM'siz: BM25 + abstract'ın kendi kelimeleri
jfinder find -f yol/abstract.txt -t "..." --cost free-to-publish --quartile Q1,Q2
jfinder find --json | jq '.journals[].name'   # JSON çıktısı (stdout)
jfinder info            # index tarihi, dergi sayısı, model, key durumu
```

### Filtreler

- `--cost all|free-to-publish|free-to-read` — varsayılan `all`
- `--max-apc N` — USD cinsinden üst sınır (APC'si **bilinmeyen** dergiler elenmez; "bilinmiyor" ≠ "ücretsiz")
- `--quartile Q1,Q2` — alan-içi h-index quartile'ı
- `--show-flagged` — varsayılan olarak gizlenen "unverified" dergileri göster
- `-k N` — gösterilecek dergi sayısı (varsayılan 5)

### LLM

- Model: `JFINDER_MODEL` ortam değişkeni veya `--model` flag'i (varsayılan: `deepseek-ai/deepseek-v4-flash-0731`)
- API key: `NVIDIA_API_KEY` ortam değişkeni (ücretsiz: https://build.nvidia.com)
- LLM başarısız olursa araç otomatik olarak offline sıralamaya düşer
- Sonuçlar cache'lenir (`--no-cache` ile atlanır); filtre değişince yalnızca yeniden sıralama yeniden çalışır

## Gizlilik

Abstract yalnızca **kendi NVIDIA_API_KEY'inizle** NVIDIA NIM'e gönderilir.
Başka hiçbir yere veri gönderilmez; telemetri yoktur; sonuçlar yerel cache
dizininde saklanır.

## Veri ve lisans

- Kod: MIT (`LICENSE`)
- Dergi verisi: OpenAlex (CC0) — ayrıntılar için `DATA.md`
- SCImago kaynaklı hiçbir kolon repoda yer almaz

**Not:** Bu araç bir öneri aracıdır, karar aracı değildir. Gönderim öncesinde
derginin aims & scope'unu kendi sitesinden doğrulayın.

---

## English

`jfinder` suggests target journals for a paper abstract, grounded in local
OpenAlex data. The LLM never picks journals: it only (a) extracts a structured
profile from the abstract and (b) reranks candidates found by local BM25
search. Candidates always come from the bundled `journals.parquet`.

- `jfinder init` — create an `abstract.md` template
- `jfinder find` — top 5 journals with fit scores and reasons
- `jfinder find --offline` — no API key required (BM25 over the abstract's words)
- `jfinder find --json` — JSON on stdout (pipeable with `jq`)
- `jfinder info` — index date, journal count, model, key status

Filters: `--cost all|free-to-publish|free-to-read`, `--max-apc N`,
`--quartile Q1,Q2`, `--show-flagged`, `-k N`.

**Privacy:** the abstract is sent only to NVIDIA NIM with your own
`NVIDIA_API_KEY`; no telemetry, no other data leaves the machine.

License: MIT (code), OpenAlex CC0 (data, see `DATA.md`). This is a suggestion
tool — always verify aims & scope on the journal site before submitting.
