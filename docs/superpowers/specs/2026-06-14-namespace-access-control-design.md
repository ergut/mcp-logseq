# Namespace Bazlı Erişim Kontrolü — Tasarım

**Tarih:** 2026-06-14
**Durum:** Onaylandı (uygulama planı bekliyor)

## Amaç

mcp-logseq sunucusuna namespace bazlı erişim kontrolü eklemek. Böylece farklı
agent'lara Logseq grafiğinin yalnızca belirli bölümlerine erişim verilebilir
(kısıtlı erişimli agent senaryosu) veya belirli namespace'ler tüm agent'lardan
gizlenebilir.

Mevcut durumda sadece **tag bazlı `exclude_tags`** (blacklist) mekanizması var ve
yalnızca okuma araçlarında uygulanıyor. Namespace merkezli bir kontrol ve
whitelist (allow-list) yok.

## Kararlar (brainstorming özeti)

1. **Erişim modeli:** Hem `include_namespaces` (allow-list) hem
   `exclude_namespaces` (deny-list) desteklenir.
2. **Eşleştirme:** Segment bazlı. `work` → `work` ve `work/...` eşleşir;
   `workshop` eşleşmez. Case-insensitive (Logseq sayfa adları zaten böyle).
3. **Öncelik:** Exclude kazanır. Önce include ile daralt, sonra exclude ile
   delik aç.
4. **Kapsam:** Tüm araçlar — okuma, yazma/silme ve vektör arama.
5. **Namespace'siz sayfalar:** Katı allow-list. `include_namespaces` ayarlıysa,
   namespace'i olmayan üst seviye sayfalar da gizlenir (gerçek izolasyon).
6. **Config yüzeyi:** `exclude_tags` ile simetrik — env değişkeni veya config
   dosyası kök anahtarı. Öncelik: env > config > boş.
7. **Tag ile ilişki:** Bağımsız katmanlar, mantıksal VEYA ile engelleme. Bir
   sayfa ya tag'inden ya namespace'inden dolayı bloklanabilir.
8. **Engelleme görünürlüğü:** Liste/arama/vektör sessizce gizler; doğrudan
   erişim ve yazma "Access denied" ile sert hata verir.

## 1. Config katmanı (`config.py`)

`load_exclude_tags()` ile birebir simetrik iki yeni yükleyici eklenir:

```
load_include_namespaces() -> list[str]   # LOGSEQ_INCLUDE_NAMESPACES > config "include_namespaces" > []
load_exclude_namespaces() -> list[str]   # LOGSEQ_EXCLUDE_NAMESPACES > config "exclude_namespaces" > []
```

Üçü de (mevcut `load_exclude_tags` dahil) ortak bir helper'a bağlanır:

```python
def _load_csv_config(env_var: str, config_key: str) -> list[str]:
    """env > config dosyası kökü > [] önceliği.
    env: virgülle ayrılmış string. config: list veya virgüllü string kabul eder.
    Boşları atar. Asla raise etmez."""
```

`load_exclude_tags()` bu helper'a `("LOGSEQ_EXCLUDE_TAGS", "exclude_tags")` ile
delege eder — küçük, odaklı refactor; davranışı değişmez.

Örnek config:

```json
{
  "logseq_graph_path": "/path/to/logseq/pages",
  "exclude_tags": ["private", "secret"],
  "include_namespaces": ["work", "projects"],
  "exclude_namespaces": ["work/secret"]
}
```

## 2. Eşleştirme mantığı (`tools.py`)

İki saf, test edilebilir fonksiyon:

```python
def _namespace_matches(page_name: str, ns: str) -> bool:
    """Segment bazlı, case-insensitive.
    'work' -> 'work' ve 'work/...' eşleşir; 'workshop' eşleşmez."""
    p, n = page_name.lower(), ns.lower().rstrip("/")
    return p == n or p.startswith(n + "/")

def _is_namespace_blocked(page_name: str,
                          include: list[str],
                          exclude: list[str]) -> bool:
    if any(_namespace_matches(page_name, n) for n in exclude):
        return True                       # exclude kazanır
    if include and not any(_namespace_matches(page_name, n) for n in include):
        return True                       # katı allow-list
    return False
```

Modül seviyesinde, mevcut `_exclude_tags` yanına:

```python
_include_namespaces = load_include_namespaces()
_exclude_namespaces = load_exclude_namespaces()
```

Birleşik karar fonksiyonu (tag VEYA namespace):

```python
def _is_page_blocked(page: dict | None, page_name: str) -> bool:
    if page and _is_page_excluded(page, _exclude_tags):   # mevcut tag mantığı
        return True
    return _is_namespace_blocked(page_name, _include_namespaces, _exclude_namespaces)
```

**Nüans:** Tag kontrolü sayfanın fetch edilmiş property'lerini gerektirir;
namespace kontrolü sadece sayfa adından çalışır. Bu yüzden namespace filtresi
daha ucuzdur ve içerik çekilmeden uygulanabilir — `list_pages` gibi yerlerde
önce isimden eleyip gereksiz fetch'ten kaçınılır.

## 3. Tool entegrasyon noktaları

### A. Sayfa adı doğrudan elde olanlar (pre-flight kontrol)

| Tool | Kontrol edilen | Engellenince |
|---|---|---|
| `get_page_content` | `page_name` | Access denied |
| `create_page` | `page_name` (hedef) | Access denied |
| `update_page` | `page_name` | Access denied |
| `delete_page` | `page_name` | Access denied |
| `rename_page` | **hem** `page_name` **hem** `new_name` | Access denied |
| `get_page_backlinks` | `page_name` | Access denied |
| `get_pages_from_namespace` | `namespace` arg | Access denied |
| `get_pages_tree_from_namespace` | `namespace` arg | Access denied |

`rename_page` özel: kaynak ve hedef adın ikisi de izinli olmalı; yasak
namespace'e taşıma engellenir.

### B. Block UUID ile çalışanlar (block → sahip sayfa çözümü)

`delete_block`, `update_block`, `get_block`, `insert_nested_block`,
`set_block_properties`. Bunlar sayfa adı taşımaz. Block'un sahip olduğu sayfa
adı API'den çözülür (`get_block` zaten `page` referansı döndürür), sonra namespace
kontrolü uygulanır. Bu, bu araçlara bir ekstra API round-trip ekler — izolasyon
için kabul edilen maliyet.

### C. Liste/arama (sonuç filtreleme — sessiz)

`list_pages`, `search`, `query`, `find_pages_by_property` ve vektör arama
sonuçları bloklu sayfaları sessizce eler. Mevcut `search` exclude deseni
`_is_page_blocked`'a genişletilir.

## 4. Test planı

- **Unit (saf fonksiyonlar):**
  - `_namespace_matches`: `work`→`work` ✓, `work/x` ✓, `workshop` ✗,
    case-insensitive, trailing slash normalizasyonu.
  - `_is_namespace_blocked`: exclude kazanır, katı allow-list, namespace'siz
    sayfa allow-list altında bloklanır, boş config = bloklanmaz.
  - `_is_page_blocked`: tag VEYA namespace birleşimi.
- **Config:** env > config > boş önceliği; ortak `_load_csv_config` helper'ı;
  `load_exclude_tags` regresyonu (mevcut testler geçer).
- **Tool entegrasyon:**
  - Her A-grubu tool yasak namespace'te Access denied döner.
  - `rename_page` `new_name` kontrolü.
  - B-grubu block→page çözümü ve engelleme.
  - C-grubu sessiz filtreleme (sonuçta bloklu sayfa yok).
- **Geriye dönük uyumluluk:** Hiçbir namespace config'i yokken davranış birebir
  aynı (boş liste = filtre yok).

## Kapsam dışı (YAGNI)

- Tag bazlı include (whitelist) — bu işte gerekmedi.
- Per-tool veya per-agent farklı politikalar — tek global config yeterli.
- Regex/glob namespace desenleri — segment prefix yeterli.
