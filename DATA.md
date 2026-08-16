# DATA.md — Veri kaynakları ve şema

## Kaynak

`jfinder/data/journals.parquet` dosyası **OpenAlex** `/sources` endpoint'inden
üretilir. OpenAlex verisi **CC0** lisanslıdır.

- Endpoint: `https://api.openalex.org/sources`
- Filtre: `type:journal,works_count:>100`
- Sayfalama: cursor pagination, 200 kayıt/sayfa
- Üretim scripti: `scripts/build_index.py` (runtime'da çağrılmaz)
- **Çekilme tarihi: 2026-08-16** (122.851 dergi)
- Yeniden üretme: `python scripts/build_index.py`

Seçilen alanlar: `id, display_name, issn_l, issn, host_organization_name,
country_code, topics, summary_stats, works_count, is_oa, is_in_doaj, apc_usd`.

## Şema

| kolon | tip | açıklama |
|---|---|---|
| `openalex_id` | str | `S137773608` |
| `name` | str | dergi adı |
| `issn_l` | str | linking ISSN |
| `issn` | list[str] | tüm ISSN'ler |
| `publisher` | str | host organization adı (null olabilir) |
| `country` | str | ISO-2 (null olabilir) |
| `topics` | list[str] | konu etiketleri (BM25 corpus'u) |
| `h_index` | int | OpenAlex h-index |
| `citedness_2y` | float | 2-yıllık ortalama atıf |
| `works_count` | int | toplam yayın sayısı |
| `quartile` | str | `Q1`–`Q4`, alan-içi hesaplanmış |
| `is_oa` | bool | |
| `in_doaj` | bool | OpenAlex `is_in_doaj` alanı |
| `apc_usd` | float | null = **bilinmiyor** (ücretsiz değil) |
| `built_at` | str | ISO tarih; tüm satırlarda aynı |

## Türetilmiş alanlar

- **Quartile**: birincil topic'e (ilk topic) göre grupla, her grupta `h_index`
  üzerinden `qcut(4)`. Dörtten az farklı değere sahip gruplarda `Q4` kabul edilir.
- **Maliyet sınıfı** (`jfinder/data.py` → `cost_class`): `oa_paid` (OA, yazar
  öder), `diamond` (OA + DOAJ + APC yok/0), `oa_unknown` (OA ama APC bilgisi
  yok — çıktıda "APC bilinmiyor", asla "ücretsiz" denmez), `subscription`
  (hybrid OA seçeneği olabilir).
- **Unverified bayrağı** (`flag`): DOAJ'da kayıtlı olmayan, OA, APC > $1500 ve
  h-index < 15 olan dergiler için sezgisel bir **uyarıdır**, suçlama değildir.

## Uyarılar

- APC fiyatları list fiyatlarıdır (OpenAlex/DOAJ); gerçek fiyat derginin
  sitesinden teyit edilmelidir.
- **SCImago kaynaklı hiçbir kolon bu repoda yer almaz** (SJR, SJR quartile,
  Scimago kategorileri, cites-per-doc). SCImago verisi non-commercial kısıtlıdır
  ve MIT lisansıyla çelişir.
