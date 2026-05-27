# 🌱 Sustainability Indicator AI Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" />
  <img src="https://img.shields.io/badge/Streamlit-Cloud-red?logo=streamlit" />
  <img src="https://img.shields.io/badge/PostgreSQL-Supabase-336791?logo=postgresql" />
  <img src="https://img.shields.io/badge/OpenAI-LLM-111111?logo=openai" />
  <img src="https://img.shields.io/badge/n8n-Automation-EA4B71?logo=n8n" />
  <img src="https://img.shields.io/badge/Output-SPSS%20%7C%20Stata%20%7C%20Excel-green" />
</p>

<p align="center">
  <b>AI destekli ESG / sürdürülebilirlik gösterge çıkarımı, rapor takibi, veri kalite kontrolü ve akademik panel veri analizi platformu.</b>
</p>

---

## 📌 Proje Özeti

**Sustainability Indicator AI Agent**, şirketlerin faaliyet raporları, entegre raporları ve sürdürülebilirlik raporlarından ESG göstergelerini çıkarmak için geliştirilen akademik odaklı bir Streamlit uygulamasıdır.

Uygulama; PDF raporları okur, anahtar kelime temelli kanıt metinleri çıkarır, OpenAI modelleriyle nicel ESG göstergelerini yapılandırılmış veri setine dönüştürür, sonuçları SQLite ve PostgreSQL/Supabase veritabanına kaydeder ve analiz için Excel, CSV, SPSS ve Stata çıktıları üretir.

Bu proje özellikle şu amaçlar için tasarlanmıştır:

- 📊 ESG / sürdürülebilirlik göstergelerini akademik araştırmaya uygun hale getirmek
- 🏢 BIST şirketleri için faaliyet ve sürdürülebilirlik raporlarından veri toplamak
- 🤖 LLM ile raporlardan nicel gösterge çıkarımı yapmak
- 🧪 Veri kalite kontrolü ve standart gösterge eşleştirmesi yapmak
- 📈 Panel veri analizi için SPSS, Stata ve Excel çıktıları üretmek
- 🔄 n8n ile rapor linklerini otomatik takip etmek

---

## 🧠 Sistem Mimarisi

```mermaid
flowchart TD
    A[Şirket Raporları PDF / URL] --> B[PDF Metin Okuma]
    B --> C[Anahtar Kelime Taraması]
    C --> D[Kanıt Metinleri]
    D --> E[OpenAI LLM ile ESG Gösterge Çıkarma]
    E --> F[SQLite Yerel Kayıt]
    E --> G[Supabase PostgreSQL Kayıt]

    H[World Bank API] --> I[Ülke Düzeyi Sürdürülebilirlik Göstergeleri]
    I --> J[Panel Veri Hazırlama]

    K[n8n Cloud] --> L[Rapor Sayfalarını Otomatik Takip]
    L --> M[PDF Link Adayları]
    M --> G

    G --> N[ESG Sözlük ve Kalite Kontrol]
    N --> O[Akademik Panel Veri]
    O --> P[Excel / CSV / SPSS / Stata]
```

---

## 🧩 Ana Modüller

| No | Modül | Açıklama |
|---:|---|---|
| 1 | **Ülke Göstergeleri** | World Bank API üzerinden CO₂, GDP, yenilenebilir enerji, internet kullanımı gibi göstergeleri indirir. |
| 2 | **PDF Rapor Tarama** | PDF raporlarda ESG anahtar kelimelerini arar ve kanıt metinlerini çıkarır. |
| 3 | **LLM Gösterge Çıkarma** | Kanıt metinlerinden OpenAI modeliyle yapılandırılmış ESG göstergeleri üretir. |
| 4 | **Hesaplama ve Panel Veri** | Türetilmiş göstergeler ve şirket-yıl panel veri çıktıları üretir. |
| 5 | **Çoklu Şirket Veri Seti** | Birden fazla şirketten gelen göstergeleri birleştirir. |
| 6 | **SQLite Veri Tabanı** | Yerel kalıcı ESG gösterge kayıtlarını yönetir. |
| 7 | **Toplu PDF İşleme** | Birden çok PDF raporu aynı anda işler. |
| 8 | **SPSS/Stata Çıktı** | Modellemeye hazır CSV, Excel, Stata `.do` ve SPSS `.sps` dosyaları üretir. |
| 9 | **PostgreSQL / Supabase** | Bulut veritabanı bağlantısı, kayıt aktarımı ve veri yönetimi sağlar. |
| 10 | **URL’den Rapor İşleme** | PDF URL’lerini indirir, işler ve ESG göstergelerini çıkarır. |
| 11 | **BIST Rapor Linkleri** | BIST şirketleri için rapor linkleri tablosu ve URL işleme metni üretir. |
| 12 | **ESG Sözlük & Kalite** | Standart ESG sözlüğüyle eşleştirme, eksik veri, birim ve tekrar kontrolü yapar. |
| 13 | **BIST Link Doğrulama** | PDF linklerinin erişilebilirlik, yıl, içerik tipi ve skor kontrolünü yapar. |
| 14 | **n8n Takip Edilen Raporlar** | n8n’in PostgreSQL’e yazdığı rapor linklerini okur ve işler. |
| 15 | **Akademik Panel Analizi** | Tanımlayıcı istatistik, korelasyon, eksik veri, Stata/SPSS analiz kodu ve ZIP analiz paketi üretir. |

---

## 🏗️ Veri Akışı

```mermaid
sequenceDiagram
    participant User as Kullanıcı
    participant App as Streamlit App
    participant PDF as PDF / URL Rapor
    participant LLM as OpenAI LLM
    participant DB as Supabase PostgreSQL
    participant n8n as n8n Workflow

    User->>App: PDF yükler veya rapor URL girer
    App->>PDF: Rapor metnini okur
    App->>App: ESG anahtar kelime taraması yapar
    App->>LLM: Kanıt metinlerini gönderir
    LLM-->>App: ESG göstergelerini JSON olarak döndürür
    App->>DB: Göstergeleri kaydeder
    n8n->>DB: Yeni rapor linklerini düzenli kaydeder
    App->>DB: Linkleri ve göstergeleri okur
    App-->>User: Excel / SPSS / Stata / Panel veri çıktısı verir
```

---

## 📚 ESG Gösterge Sözlüğü

Uygulama, LLM’den gelen gösterge adlarını standart değişken adlarına eşleştirmek için bir ESG sözlüğü kullanır.

Örnek standart göstergeler:

| Standart Değişken | Açıklama | Tür |
|---|---|---|
| `scope1_emissions` | Kapsam 1 emisyonları | Environmental |
| `scope2_emissions` | Kapsam 2 emisyonları | Environmental |
| `scope3_emissions` | Kapsam 3 emisyonları | Environmental |
| `total_ghg_emissions` | Toplam sera gazı emisyonu | Environmental |
| `energy_consumption` | Toplam enerji tüketimi | Environmental |
| `renewable_energy_ratio` | Yenilenebilir enerji oranı | Environmental |
| `water_consumption` | Su tüketimi | Environmental |
| `total_waste` | Toplam atık | Environmental |
| `female_employee_ratio` | Kadın çalışan oranı | Social |
| `employee_count` | Toplam çalışan sayısı | Social |
| `occupational_accident_count` | İş kazası sayısı | Social |
| `sustainability_committee` | Sürdürülebilirlik komitesi | Governance |
| `net_zero_target_year` | Net sıfır hedef yılı | Environmental |

---

## 🔍 Veri Kalite Kontrolü

Kalite kontrol modülü şu kontrolleri yapar:

- Eksik `numeric_value` kontrolü
- Standart ESG sözlüğüyle eşleşmeyen göstergeler
- Beklenmeyen birim kullanımı
- Oran değişkenleri için 0–100 aralığı kontrolü
- Hedef yılı ile gerçekleşen değer ayrımı
- Olası tekrar kayıtlar
- Zayıf veya kısa kanıt metinleri

Çıktı dosyası:

```text
esg_quality_control_report.xlsx
```

---

## 📈 Akademik Panel Veri Analizi

Akademik panel analiz modülü şu dosyaları üretir:

```text
academic_panel_analysis.xlsx
standard_esg_panel.csv
academic_panel_analysis_pack.zip
stata_panel_analysis.do
spss_panel_analysis.sps
```

Analiz çıktıları:

- Tanımlayıcı istatistikler
- Eksik veri özeti
- Korelasyon matrisi
- Şirket-yıl kapsam tablosu
- Model önerileri
- Pooled OLS, Fixed Effects, Random Effects ve Two-way Fixed Effects için Stata kodu
- SPSS regresyon ve korelasyon syntax çıktısı

---

## 🔄 n8n Entegrasyonu

n8n workflow’u, BIST şirketlerinin rapor sayfalarını otomatik takip etmek için kullanılır.

```mermaid
flowchart LR
    A[Schedule Trigger] --> B[PostgreSQL report_sources Oku]
    B --> C[HTTP Request ile Rapor Sayfasını İndir]
    C --> D[Code Node ile PDF Linklerini Çıkar]
    D --> E[Linkleri Skorla]
    E --> F[report_link_checks Tablosuna Yaz]
    F --> G[Streamlit n8n Takip Sekmesinde Göster]
```

n8n’in yazdığı tablolar:

| Tablo | Görev |
|---|---|
| `report_sources` | Takip edilecek şirket rapor sayfaları |
| `report_link_checks` | Bulunan ve skorlanan aday PDF linkleri |

---

## 🗄️ Veritabanı Yapısı

Ana ESG gösterge tablosu:

```sql
esg_indicators
```

Temel alanlar:

```text
company_name
year
indicator_name
category
metric_type
value
numeric_value
unit
page
source_keyword
evidence_text
confidence
notes
created_at
```

n8n rapor takip tabloları:

```text
report_sources
report_link_checks
```

---

## 🚀 Kurulum

### 1. Depoyu klonlayın

```bash
git clone https://github.com/ibrahimguney/sustainability-agent.git
cd sustainability-agent
```

### 2. Paketleri kurun

```bash
pip install -r requirements.txt
```

### 3. Uygulamayı çalıştırın

```bash
streamlit run streamlit_app.py
```

---

## 🔐 Streamlit Cloud Secrets

Streamlit Cloud üzerinde çalıştırmak için aşağıdaki değerleri **Settings → Secrets** alanına ekleyin.

```toml
APP_PASSWORD = "güçlü-bir-şifre"

OPENAI_API_KEY = "sk-..."

DATABASE_URL = "postgresql://postgres.PROJECT_REF:PAROLA@aws-...pooler.supabase.com:6543/postgres"
```

> ⚠️ Güvenlik notu: `OPENAI_API_KEY`, `DATABASE_URL` ve `APP_PASSWORD` hiçbir zaman GitHub’a commit edilmemelidir.

---

## 🧪 Lokal Ortam Değişkenleri

Windows CMD:

```cmd
set OPENAI_API_KEY=sk-...
set DATABASE_URL=postgresql://postgres:1234@localhost:5432/sustainability_esg
set APP_PASSWORD=1234
```

PowerShell:

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:DATABASE_URL="postgresql://postgres:1234@localhost:5432/sustainability_esg"
$env:APP_PASSWORD="1234"
```

---

## 🧾 Örnek URL İşleme Formatı

```text
Akbank,2024,https://www.example.com/akbank-2024-entegre-faaliyet-raporu.pdf
Türk Hava Yolları,2024,https://www.example.com/thy-2024-faaliyet-raporu.pdf
Arçelik,2024,https://www.example.com/arcelik-2024-surdurulebilirlik-raporu.pdf
```

---

## 📦 Çıktı Dosyaları

| Dosya | Açıklama |
|---|---|
| `model_ready_esg_dataset.xlsx` | Modellemeye hazır ESG veri seti |
| `model_ready_panel.csv` | SPSS/Stata uyumlu panel veri |
| `variable_dictionary.csv` | Değişken sözlüğü |
| `stata_esg_analysis.do` | Stata başlangıç analiz kodu |
| `spss_esg_import.sps` | SPSS veri içe aktarma syntax dosyası |
| `esg_quality_control_report.xlsx` | ESG kalite kontrol raporu |
| `academic_panel_analysis.xlsx` | Akademik panel analiz dosyası |
| `academic_panel_analysis_pack.zip` | CSV + Excel + Stata + SPSS analiz paketi |

---

## 🧑‍🎓 Akademik Kullanım Senaryosu

Bu proje şu tür akademik çalışmalar için kullanılabilir:

- BIST şirketlerinde ESG performans analizi
- Sürdürülebilirlik raporlarında karbon emisyon göstergeleri
- Kadın çalışan oranı ve kurumsal sürdürülebilirlik ilişkisi
- Net sıfır hedefleri ve çevresel performans göstergeleri
- Kurumsal yönetişim ve sürdürülebilirlik komitesi etkisi
- ESG göstergeleriyle panel veri regresyon modelleri

---

## 🛣️ Yol Haritası

- [x] PDF rapor tarama
- [x] LLM ile ESG gösterge çıkarımı
- [x] SQLite kayıt
- [x] PostgreSQL / Supabase entegrasyonu
- [x] URL’den rapor işleme
- [x] BIST link doğrulama
- [x] ESG sözlük ve kalite kontrol
- [x] n8n rapor takip entegrasyonu
- [x] Akademik panel veri analizi
- [x] Tek şifreli giriş koruması
- [ ] Rol bazlı kullanıcı yönetimi
- [ ] PostgreSQL kayıt sürümleme / audit log
- [ ] n8n sonuçlarından tek tıkla URL işleme
- [ ] Otomatik makale tablo ve yöntem metni üretimi

---

## ⚠️ Sınırlılıklar

- LLM çıktıları mutlaka insan denetiminden geçirilmelidir.
- PDF raporlardaki tablo yapıları her zaman düzgün metne dönüşmeyebilir.
- ESG göstergeleri şirketten şirkete farklı adlandırılabilir.
- Panel veri analizi için yeterli şirket-yıl gözlemi gerekir.
- Streamlit Cloud’da lokal Docker PostgreSQL kullanılamaz; Supabase/Neon gibi dış erişilebilir PostgreSQL gereklidir.

---

## 🤝 Katkı

Katkılar, iyileştirme önerileri ve yeni ESG gösterge sözlüğü eklemeleri memnuniyetle karşılanır.

Önerilen katkı alanları:

- Yeni BIST şirket rapor linkleri
- ESG gösterge sözlüğü genişletmeleri
- Yeni kalite kontrol kuralları
- Stata/SPSS/R analiz şablonları
- n8n workflow iyileştirmeleri

---

## 📄 Lisans

Bu proje akademik araştırma ve eğitim amaçlı geliştirilmiştir. Kullanım öncesinde veri kaynaklarının ve şirket raporlarının kullanım koşulları kontrol edilmelidir.

---

<p align="center">
  <b>🌱 Sustainability Indicator AI Agent</b><br>
  ESG verisini raporlardan çıkar, kalite kontrol yap, panel analize hazırla.
</p>

---

## Güncel Geliştirici Notları

### Rol ve erişim modeli

Uygulama PostgreSQL tabanlı kullanıcı girişi kullanır. Roller:

| Rol | Yetki |
|---|---|
| `admin` | Tüm sekmeler, kullanıcı yönetimi, SQLite/PostgreSQL silme ve taşıma işlemleri |
| `user` | Veri toplama, PDF/URL işleme, LLM çıkarımı ve analiz işlemleri |
| `viewer` | Görüntüleme, indirme ve kalite/analiz inceleme sekmeleri |

İlk admin kullanıcısı için secrets veya ortam değişkenleri:

```toml
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "güçlü-bir-şifre"
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE"
OPENAI_API_KEY = "sk-..."
```

`.streamlit/secrets.toml` dosyası yerel kullanım içindir ve Git'e eklenmemelidir.

### Modül yapısı

| Dosya | Görev |
|---|---|
| `streamlit_app.py` | Ana Streamlit arayüzü, sekmeler ve işlem akışları |
| `sustainability_utils.py` | ESG sözlük eşleştirme, kalite kontrolleri, LLM çıktı normalizasyonu, birim dönüşümü ve test edilebilir yardımcılar |
| `sustainability_pdf.py` | PDF metin çıkarma, PDF cache, anahtar kelime tarama ve PDF tarama Excel çıktısı |
| `tests/` | Unit testler |

### LLM structured output

LLM gösterge çıkarımı OpenAI Responses API structured output akışını kullanır. Yanıt şu üst seviye yapıya zorlanır:

```json
{
  "indicators": [
    {
      "company_name": "string",
      "year": "string",
      "indicator_name": "string",
      "category": "Environmental | Social | Governance | Other",
      "value": "string",
      "unit": "string veya null",
      "page": 1,
      "source_keyword": "string",
      "evidence_text": "string",
      "confidence": 0.85,
      "notes": "string veya null"
    }
  ]
}
```

Model veya SDK structured output desteklemezse uygulama eski serbest JSON parse yoluna otomatik düşer.

### Performans ve cache

- SQLite ve PostgreSQL okuma fonksiyonları Streamlit cache ile 60 saniye cache'lenir.
- PDF byte içeriğinden metin çıkarma 1 saat cache'lenir.
- Kayıt ekleme, silme ve PostgreSQL taşıma işlemlerinden sonra ilgili veri cache'leri temizlenir.
- Sidebar'daki **Veri cache'ini yenile** düğmesi hem DB hem PDF cache'ini temizler.

### Veri kalite raporu

Kalite kontrol raporu aşağıdaki ek kontrolleri içerir:

- Düşük LLM güven skoru: `low_confidence`
- Sayısal olmayan güven skoru: `invalid_confidence`
- Uygulanan birim dönüşümleri: `unit_conversion_applied`
- Aynı şirket-yıl-standart gösterge için çelişkili normalize değerler: `conflicting_standard_value`
- Normalize edilmiş değerlerle min/max aralık kontrolü

Excel kalite raporunda ek sayfalar üretilir:

```text
issue_summary
low_confidence
unit_conversions
value_conflicts
```

### Test ve doğrulama

Yerel testleri çalıştırmak için:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m py_compile sustainability_utils.py sustainability_pdf.py streamlit_app.py
```

Sistem Python'u kullanılıyorsa bağımlılıkların kurulu olduğundan emin olun:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
python -m py_compile sustainability_utils.py sustainability_pdf.py streamlit_app.py
```

Mevcut test kapsamı yardımcı fonksiyonlar, PDF tarama, rol tab görünürlüğü, LLM response parse/structured output, birim normalizasyonu ve veri kalite kontrollerini kapsar.