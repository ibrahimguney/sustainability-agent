import io
import json
import os
import re
import sqlite3
import time
import zipfile
from typing import Dict, List, Optional
import bcrypt

import fitz  # PyMuPDF
import pandas as pd
import requests
import streamlit as st



# =====================================================
# 0. KULLANICI GİRİŞ SİSTEMİ
# =====================================================

def hash_password(password: str) -> str:
    # Şifreyi bcrypt ile hashler.# 
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    # Girilen şifre ile kayıtlı hash'i karşılaştırır.# 
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def init_users_table():
    # PostgreSQL üzerinde kullanıcı tablosunu oluşturur.# 
    database_url = get_secure_database_url()

    if not database_url:
        st.error("DATABASE_URL bulunamadı. Kullanıcı giriş sistemi için PostgreSQL bağlantısı gerekli.")
        st.stop()

    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    cur.close()
    conn.close()


def create_default_admin():
    """
    İlk admin kullanıcısını oluşturur.
    ADMIN_USERNAME ve ADMIN_PASSWORD secrets içinden okunur.
    """
    database_url = get_secure_database_url()

    try:
        admin_username = st.secrets.get("ADMIN_USERNAME", "admin")
        admin_password = st.secrets.get("ADMIN_PASSWORD", "")
    except Exception:
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "")

    if not admin_password:
        return

    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute("SELECT id FROM app_users WHERE username = %s", (admin_username,))
    existing_user = cur.fetchone()

    if existing_user is None:
        password_hash = hash_password(admin_password)

        cur.execute(
            """
            INSERT INTO app_users (username, password_hash, role, is_active)
            VALUES (%s, %s, %s, %s)
            """,
            (admin_username, password_hash, "admin", True),
        )

        conn.commit()

    cur.close()
    conn.close()


def authenticate_user(username: str, password: str):
    # Kullanıcı adı ve şifreyi kontrol eder.# 
    database_url = get_secure_database_url()

    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, username, password_hash, role, is_active
        FROM app_users
        WHERE username = %s
        """,
        (username,),
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    if user is None:
        return None

    user_id, db_username, password_hash, role, is_active = user

    if not is_active:
        return None

    if check_password(password, password_hash):
        return {
            "id": user_id,
            "username": db_username,
            "role": role,
        }

    return None


def login_screen():
    # Kullanıcı giriş ekranı.# 
    st.title("🌱 Sustainability Indicator AI Agent")
    st.subheader("Kullanıcı Girişi")

    username = st.text_input("Kullanıcı adı")
    password = st.text_input("Şifre", type="password")

    if st.button("Giriş yap", type="primary"):
        user = authenticate_user(username, password)

        if user:
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user["id"]
            st.session_state["username"] = user["username"]
            st.session_state["role"] = user["role"]
            st.rerun()
        else:
            st.error("Kullanıcı adı veya şifre hatalı.")


def require_login():
    # Giriş yapılmamışsa uygulamayı durdurur.# 
    init_users_table()
    create_default_admin()

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        login_screen()
        st.stop()

    with st.sidebar:
        st.success("Giriş başarılı")
        st.write(f"Kullanıcı: **{st.session_state.get('username', '')}**")
        st.write(f"Rol: **{st.session_state.get('role', '')}**")

        if st.button("Çıkış yap"):
            st.session_state.clear()
            st.rerun()


def require_admin():
    # Sadece admin rolüne izin verir.# 
    if st.session_state.get("role") != "admin":
        st.warning("Bu bölüme sadece admin kullanıcılar erişebilir.")
        st.stop()

def can_admin() -> bool:
    return st.session_state.get("role") == "admin"


def can_edit() -> bool:
    return st.session_state.get("role") in ["admin", "user"]


def can_view() -> bool:
    return st.session_state.get("role") in ["admin", "user", "viewer"]


def require_edit_permission():
    if not can_edit():
        st.warning("Bu işlem için admin veya user yetkisi gerekir.")
        st.stop()


def require_view_permission():
    if not can_view():
        st.warning("Bu bölümü görüntüleme yetkiniz yok.")
        st.stop()

def admin_user_management():
    # Admin için kullanıcı yönetimi paneli.# 
    require_admin()

    st.subheader("👤 Kullanıcı Yönetimi")

    with st.form("new_user_form"):
        new_username = st.text_input("Yeni kullanıcı adı")
        new_password = st.text_input("Yeni kullanıcı şifresi", type="password")
        new_role = st.selectbox("Rol", ["user", "viewer", "admin"])
        submitted = st.form_submit_button("Kullanıcı ekle")

    if submitted:
        if not new_username or not new_password:
            st.warning("Kullanıcı adı ve şifre boş olamaz.")
        else:
            database_url = get_secure_database_url()
            conn = get_postgres_connection(database_url)
            cur = conn.cursor()

            try:
                password_hash = hash_password(new_password)

                cur.execute(
                    """
                    INSERT INTO app_users (username, password_hash, role, is_active)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (new_username, password_hash, new_role, True),
                )

                conn.commit()
                st.success(f"{new_username} kullanıcısı oluşturuldu.")

            except Exception as exc:
                conn.rollback()
                st.error(f"Kullanıcı oluşturulamadı: {exc}")

            finally:
                cur.close()
                conn.close()

    st.divider()
    st.write("Mevcut kullanıcılar")

    database_url = get_secure_database_url()
    conn = get_postgres_connection(database_url)

    users_df = pd.read_sql_query(
        """
        SELECT id, username, role, is_active, created_at
        FROM app_users
        ORDER BY id
        """,
        conn,
    )

    conn.close()

    st.dataframe(users_df, use_container_width=True)

# =====================================================
# 1. VARSAYILAN GÖSTERGELER
# =====================================================

DEFAULT_INDICATORS: Dict[str, str] = {
    "EN.ATM.CO2E.PC": "CO2_per_capita",
    "NY.GDP.PCAP.PP.KD": "GDP_per_capita_PPP_constant",
    "EG.FEC.RNEW.ZS": "Renewable_energy_consumption_pct",
    "SP.URB.TOTL.IN.ZS": "Urban_population_pct",
    "IT.NET.USER.ZS": "Internet_users_pct",
    "SL.TLF.CACT.FE.ZS": "Female_labor_force_participation_pct",
}

DEFAULT_COUNTRIES = "TUR,DEU,FRA,ITA,ESP,GBR,USA,JPN,KOR"

OECD_SAMPLE_COUNTRIES = (
    "AUS,AUT,BEL,CAN,CHL,COL,CRI,CZE,DNK,EST,FIN,FRA,DEU,GRC,HUN,ISL,IRL,ISR,"
    "ITA,JPN,KOR,LVA,LTU,LUX,MEX,NLD,NZL,NOR,POL,PRT,SVK,SVN,ESP,SWE,CHE,TUR,"
    "GBR,USA"
)

DEFAULT_KEYWORDS = """Kapsam 1
Kapsam 2
Kapsam 3
sera gazı
emisyon
karbon emisyonu
enerji tüketimi
yenilenebilir enerji
su tüketimi
atık
geri dönüştürülen atık
kadın çalışan
iş kazası
iş sağlığı ve güvenliği
sürdürülebilirlik komitesi
net sıfır
ESG"""

# Çok sayıda ülke için World Bank API isteklerini parçalara böler.
WORLD_BANK_COUNTRY_CHUNK_SIZE = 15


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    # Listeyi sabit büyüklükte parçalara böler.# 
    clean_items = [str(x).strip().upper() for x in items if str(x).strip()]
    return [clean_items[i : i + chunk_size] for i in range(0, len(clean_items), chunk_size)]


def parse_country_codes(country_text: str) -> List[str]:
    """
    Ülke kodlarını virgül, noktalı virgül, boşluk veya satır sonuna göre ayırır.
    """
    if not country_text:
        return []

    parts = re.split(r"[,;\s]+", country_text)
    return [p.strip().upper() for p in parts if p.strip()]



# =====================================================
# 2. WORLD BANK VERİ İNDİRME FONKSİYONLARI
# =====================================================

@st.cache_data(show_spinner=False)
def fetch_worldbank_indicator(
    countries: List[str],
    indicator_code: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    # World Bank API üzerinden tek bir göstergeyi indirir.# 

    country_path = ";".join([c.strip().upper() for c in countries if c.strip()])

    url = (
        f"https://api.worldbank.org/v2/country/{country_path}/indicator/{indicator_code}"
        f"?format=json&per_page=20000&date={start_year}:{end_year}"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return pd.DataFrame()

    rows = []

    for item in payload[1]:
        rows.append(
            {
                "country": item.get("country", {}).get("value"),
                "countryiso3code": item.get("countryiso3code"),
                "year": int(item.get("date")),
                "indicator_code": indicator_code,
                "indicator_name": item.get("indicator", {}).get("value"),
                "value": item.get("value"),
            }
        )

    return pd.DataFrame(rows)


def download_worldbank_panel(
    countries: List[str],
    indicators: Dict[str, str],
    start_year: int,
    end_year: int,
    country_chunk_size: int = WORLD_BANK_COUNTRY_CHUNK_SIZE,
) -> pd.DataFrame:
    """
    Birden fazla World Bank göstergesini indirip geniş panel veri formatına dönüştürür.

    Çok sayıda ülke seçildiğinde World Bank API isteği ülke gruplarına bölünür.
    Böylece URL uzunluğu / API isteği sınırı nedeniyle oluşabilecek hatalar azaltılır.
    """

    countries = [c.strip().upper() for c in countries if str(c).strip()]
    country_chunks = chunk_list(countries, country_chunk_size)

    all_frames = []
    progress = st.progress(0)
    status = st.empty()

    total_steps = max(1, len(indicators) * max(1, len(country_chunks)))
    step = 0

    if not country_chunks:
        st.warning("Geçerli ülke kodu bulunamadı.")
        return pd.DataFrame()

    for indicator_code in indicators.keys():
        short_name = indicators[indicator_code]

        for chunk_no, country_chunk in enumerate(country_chunks, start=1):
            step += 1

            status.info(
                f"İndiriliyor: {indicator_code} - {short_name} | "
                f"Ülke grubu {chunk_no}/{len(country_chunks)} "
                f"({len(country_chunk)} ülke)"
            )

            try:
                df = fetch_worldbank_indicator(
                    countries=country_chunk,
                    indicator_code=indicator_code,
                    start_year=start_year,
                    end_year=end_year,
                )

                if not df.empty:
                    all_frames.append(df)

            except Exception as exc:
                st.warning(
                    f"{indicator_code} indirilemedi. "
                    f"Ülke grubu: {', '.join(country_chunk)} | Hata: {exc}"
                )

            progress.progress(min(step / total_steps, 1.0))
            time.sleep(0.1)

    status.empty()

    if not all_frames:
        return pd.DataFrame()

    long_df = pd.concat(all_frames, ignore_index=True)

    long_df = long_df.drop_duplicates(
        subset=["countryiso3code", "year", "indicator_code"],
        keep="first",
    )

    long_df["short_name"] = long_df["indicator_code"].map(indicators)

    wide_df = long_df.pivot_table(
        index=["country", "countryiso3code", "year"],
        columns="short_name",
        values="value",
        aggfunc="first",
    ).reset_index()

    wide_df.columns.name = None
    wide_df = wide_df.sort_values(["countryiso3code", "year"]).reset_index(drop=True)

    return wide_df

def make_worldbank_excel_file(df: pd.DataFrame, metadata: pd.DataFrame) -> bytes:
    # Panel veri, gösterge bilgisi ve eksik veri özetini Excel dosyasına yazar.# 

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="panel_data")
        metadata.to_excel(writer, index=False, sheet_name="indicator_metadata")

        missing = (
            df.isna()
            .sum()
            .reset_index()
            .rename(columns={"index": "variable", 0: "missing_count"})
        )

        missing["missing_pct"] = (missing["missing_count"] / len(df) * 100).round(2)
        missing.to_excel(writer, index=False, sheet_name="missing_summary")

    return output.getvalue()


# =====================================================
# 3. PDF RAPOR OKUMA FONKSİYONLARI
# =====================================================
# PDF okuma ve anahtar kelime tarama mantığı sustainability_pdf.py modülündedir.


# =====================================================
# 4. LLM GÖSTERGE ÇIKARMA FONKSİYONLARI
# =====================================================

def build_llm_prompt(evidence_df: pd.DataFrame, company_name: str, report_year: str) -> str:
    # Kanıt metinlerini LLM'e gönderilecek düzenli metne çevirir.# 

    records = []

    for _, row in evidence_df.iterrows():
        records.append(
            {
                "page": int(row["page"]),
                "keyword": str(row["keyword"]),
                "evidence_text": str(row["evidence_text"]),
            }
        )

    return f"""
Aşağıda bir şirketin faaliyet/sürdürülebilirlik raporundan anahtar kelime taramasıyla çıkarılmış kanıt metinleri var.

Şirket adı: {company_name}
Rapor yılı: {report_year}

Görevin:
Bu metinlerden sürdürülebilirlik/ESG göstergelerini çıkar.
Sadece metinde açıkça bulunan nicel göstergeleri çıkar.
Tahmin yapma.
Değer yoksa kayıt oluşturma.
Birim açık değilse unit alanına null yaz.
Yıl açık değilse report_year değerini kullan.
Her kayıt için kanıt metnini kısa tut.
Cevabı SADECE JSON array olarak ver.

Çıktı şeması:
[
  {{
    "company_name": "string",
    "year": "string veya number",
    "indicator_name": "string",
    "category": "Environmental | Social | Governance | Other",
    "value": "number veya string",
    "unit": "string veya null",
    "page": number,
    "source_keyword": "string",
    "evidence_text": "string",
    "confidence": number,
    "notes": "string veya null"
  }}
]

Özellikle şu göstergeleri ara:
- Kapsam 1 emisyon
- Kapsam 2 emisyon
- Kapsam 3 emisyon
- Toplam sera gazı emisyonu
- Enerji tüketimi
- Yenilenebilir enerji tüketimi
- Su tüketimi
- Atık miktarı
- Geri dönüştürülen atık
- Kadın çalışan sayısı/oranı
- Çalışan sayısı
- İş kazası
- Eğitim saati
- Sürdürülebilirlik komitesi
- Net sıfır hedefi

Kanıt kayıtları:
{json.dumps(records, ensure_ascii=False, indent=2)}
"""


def llm_extract_indicators(
    evidence_df: pd.DataFrame,
    company_name: str,
    report_year: str,
    model_name: str,
    api_key: Optional[str],
) -> pd.DataFrame:
    # OpenAI API ile kanıt metinlerinden ESG göstergeleri çıkarır.# 

    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(
            "openai paketi yüklü değil. PowerShell'de şu komutu çalıştırın: pip install openai"
        ) from exc

    if api_key:
        client = OpenAI(api_key=api_key)
    else:
        client = OpenAI()

    system_prompt = """
Sen akademik sürdürülebilirlik veri çıkarma uzmanısın.
Cevabın sadece istenen yapılandırılmış JSON şemasına uygun olmalı.
Açıkça verilmeyen değerleri üretme.
Türkçe metinlerde sayıları, birimleri ve yıl bilgisini dikkatle ayır.
"""

    user_prompt = build_llm_prompt(
        evidence_df=evidence_df,
        company_name=company_name,
        report_year=report_year,
    )

    response_request = {
        "model": model_name,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        response = client.responses.create(
            **response_request,
            text=get_llm_response_text_format(),
        )
    except Exception:
        response = client.responses.create(**response_request)

    raw_text = getattr(response, "output_text", "")
    extracted = extract_indicator_records_from_response(raw_text)

    df = normalize_extracted_indicator_records(
        extracted,
        default_company_name=company_name,
        default_report_year=report_year,
    )

    df["metric_type"] = df.apply(
        lambda row: classify_metric_type(
            row.get("indicator_name"),
            row.get("unit"),
            row.get("value"),
        ),
        axis=1,
    )

    df = df[
        [
            "company_name",
            "year",
            "indicator_name",
            "category",
            "metric_type",
            "value",
            "numeric_value",
            "unit",
            "page",
            "source_keyword",
            "evidence_text",
            "confidence",
            "notes",
        ]
    ]

    return df


def make_llm_excel_file(
    extracted_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
    keyword_summary_df: pd.DataFrame,
) -> bytes:
    # LLM çıkarımları, kanıtlar ve özetleri Excel'e yazar.# 

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        extracted_df.to_excel(writer, index=False, sheet_name="llm_indicators")
        evidence_df.to_excel(writer, index=False, sheet_name="keyword_evidence")
        keyword_summary_df.to_excel(writer, index=False, sheet_name="keyword_summary")

    return output.getvalue()




# =====================================================
# 5. HESAPLAMA VE PANEL VERİ FONKSİYONLARI
# =====================================================

def find_indicator_value(df: pd.DataFrame, include_terms: List[str], exclude_terms: Optional[List[str]] = None):
    """
    indicator_name içinde geçen kelimelere göre ilk uygun numeric_value değerini bulur.
    Büyük/küçük harf duyarsızdır.
    """
    if df.empty or "indicator_name" not in df.columns or "numeric_value" not in df.columns:
        return None

    exclude_terms = exclude_terms or []

    temp = df.copy()
    temp["indicator_lower"] = temp["indicator_name"].astype(str).str.lower()

    mask = pd.Series(True, index=temp.index)

    for term in include_terms:
        mask = mask & temp["indicator_lower"].str.contains(term.lower(), na=False)

    for term in exclude_terms:
        mask = mask & ~temp["indicator_lower"].str.contains(term.lower(), na=False)

    matched = temp[mask & temp["numeric_value"].notna()]

    if matched.empty:
        return None

    return matched.iloc[0]["numeric_value"]


def build_company_year_panel(extracted_df: pd.DataFrame) -> pd.DataFrame:
    """
    LLM ile çıkarılan uzun form göstergeleri şirket-yıl panel veri formatına dönüştürür.
    Aynı şirket-yıl-gösterge için ilk numeric_value alınır.
    """
    if extracted_df.empty:
        return pd.DataFrame()

    required = {"company_name", "year", "indicator_name", "numeric_value"}
    if not required.issubset(set(extracted_df.columns)):
        return pd.DataFrame()

    temp = extracted_df.copy()
    temp["indicator_slug"] = (
        temp["indicator_name"]
        .astype(str)
        .str.lower()
        .str.replace("ı", "i", regex=False)
        .str.replace("ğ", "g", regex=False)
        .str.replace("ü", "u", regex=False)
        .str.replace("ş", "s", regex=False)
        .str.replace("ö", "o", regex=False)
        .str.replace("ç", "c", regex=False)
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )

    panel = temp.pivot_table(
        index=["company_name", "year"],
        columns="indicator_slug",
        values="numeric_value",
        aggfunc="first",
    ).reset_index()

    panel.columns.name = None
    return panel


def compute_automatic_derived_indicators(extracted_df: pd.DataFrame) -> pd.DataFrame:
    """
    Bilinen örüntüler varsa otomatik türetilmiş göstergeler hesaplar.
    Örnek: Kapsam 1+2+3, kadın çalışan oranı, geri kazanım oranı vb.
    """
    if extracted_df.empty:
        return pd.DataFrame()

    rows = []

    grouped = extracted_df.groupby(["company_name", "year"], dropna=False)

    for (company, year), g in grouped:
        # Kapsam / Scope emisyonları
        scope1 = find_indicator_value(g, ["kapsam", "1"])
        if scope1 is None:
            scope1 = find_indicator_value(g, ["scope", "1"])

        scope2 = find_indicator_value(g, ["kapsam", "2"])
        if scope2 is None:
            scope2 = find_indicator_value(g, ["scope", "2"])

        scope3 = find_indicator_value(g, ["kapsam", "3"])
        if scope3 is None:
            scope3 = find_indicator_value(g, ["scope", "3"])

        if scope1 is not None and scope2 is not None:
            rows.append(
                {
                    "company_name": company,
                    "year": year,
                    "derived_indicator": "Toplam Kapsam 1 + Kapsam 2 emisyon",
                    "value": scope1 + scope2,
                    "unit": "orijinal emisyon birimi",
                    "formula": "Kapsam 1 + Kapsam 2",
                    "notes": "Kapsam 1 ve Kapsam 2 bulunduğu için hesaplandı.",
                }
            )

        if scope1 is not None and scope2 is not None and scope3 is not None:
            rows.append(
                {
                    "company_name": company,
                    "year": year,
                    "derived_indicator": "Toplam Kapsam 1 + Kapsam 2 + Kapsam 3 emisyon",
                    "value": scope1 + scope2 + scope3,
                    "unit": "orijinal emisyon birimi",
                    "formula": "Kapsam 1 + Kapsam 2 + Kapsam 3",
                    "notes": "Kapsam 1, 2 ve 3 bulunduğu için hesaplandı.",
                }
            )

        # Kadın çalışan oranı: kadın çalışan sayısı / toplam çalışan sayısı
        female_count = find_indicator_value(g, ["kadın", "çalışan", "say"])
        total_employee = find_indicator_value(g, ["çalışan", "say"], exclude_terms=["kadın"])

        if female_count is not None and total_employee is not None and total_employee != 0:
            rows.append(
                {
                    "company_name": company,
                    "year": year,
                    "derived_indicator": "Kadın çalışan oranı",
                    "value": female_count / total_employee * 100,
                    "unit": "yüzde",
                    "formula": "Kadın çalışan sayısı / Toplam çalışan sayısı × 100",
                    "notes": "Kadın çalışan sayısı ve toplam çalışan sayısı bulunduğu için hesaplandı.",
                }
            )

        # Yenilenebilir enerji oranı
        renewable_energy = find_indicator_value(g, ["yenilenebilir", "enerji"])
        total_energy = find_indicator_value(g, ["toplam", "enerji"], exclude_terms=["yenilenebilir"])

        if renewable_energy is not None and total_energy is not None and total_energy != 0:
            rows.append(
                {
                    "company_name": company,
                    "year": year,
                    "derived_indicator": "Yenilenebilir enerji oranı",
                    "value": renewable_energy / total_energy * 100,
                    "unit": "yüzde",
                    "formula": "Yenilenebilir enerji / Toplam enerji × 100",
                    "notes": "Yenilenebilir enerji ve toplam enerji bulunduğu için hesaplandı.",
                }
            )

        # Atık geri kazanım oranı
        recovered_waste = find_indicator_value(g, ["geri", "atık"])
        total_waste = find_indicator_value(g, ["toplam", "atık"], exclude_terms=["geri"])

        if recovered_waste is not None and total_waste is not None and total_waste != 0:
            rows.append(
                {
                    "company_name": company,
                    "year": year,
                    "derived_indicator": "Atık geri kazanım oranı",
                    "value": recovered_waste / total_waste * 100,
                    "unit": "yüzde",
                    "formula": "Geri kazanılan atık / Toplam atık × 100",
                    "notes": "Geri kazanılan atık ve toplam atık bulunduğu için hesaplandı.",
                }
            )

    return pd.DataFrame(rows)


def make_panel_excel_file(
    extracted_df: pd.DataFrame,
    derived_df: pd.DataFrame,
    panel_df: pd.DataFrame,
    custom_df: pd.DataFrame,
) -> bytes:
    """
    LLM göstergeleri, türetilmiş göstergeler, panel veri ve özel hesapları Excel'e yazar.
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        extracted_df.to_excel(writer, index=False, sheet_name="llm_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="derived_indicators")
        panel_df.to_excel(writer, index=False, sheet_name="company_year_panel")
        custom_df.to_excel(writer, index=False, sheet_name="custom_calculations")

    return output.getvalue()



def add_to_master_dataset(new_df: pd.DataFrame):
    """
    Yeni LLM çıkarımını oturum içi ana veri setine ekler.
    Aynı şirket-yıl-gösterge-değer-sayfa kayıtları tekrar eklenmez.
    """
    if new_df.empty:
        return

    if "master_indicators_df" not in st.session_state:
        st.session_state["master_indicators_df"] = pd.DataFrame()

    master = st.session_state["master_indicators_df"]

    combined = pd.concat([master, new_df], ignore_index=True)

    dedup_cols = [
        "company_name",
        "year",
        "indicator_name",
        "value",
        "unit",
        "page",
        "evidence_text",
    ]

    existing_cols = [c for c in dedup_cols if c in combined.columns]

    if existing_cols:
        combined = combined.drop_duplicates(subset=existing_cols)

    st.session_state["master_indicators_df"] = combined.reset_index(drop=True)


def make_master_excel_file(master_df: pd.DataFrame) -> bytes:
    """
    Birden çok şirketten gelen ana veri setini Excel'e yazar.
    """
    derived_df = compute_automatic_derived_indicators(master_df)
    panel_df = build_company_year_panel(master_df)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        master_df.to_excel(writer, index=False, sheet_name="all_llm_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="all_derived_indicators")
        panel_df.to_excel(writer, index=False, sheet_name="multi_company_panel")

        if not master_df.empty and "metric_type" in master_df.columns:
            metric_summary = (
                master_df.groupby(["company_name", "year", "metric_type"])
                .size()
                .reset_index(name="count")
            )
            metric_summary.to_excel(writer, index=False, sheet_name="metric_type_summary")

    return output.getvalue()




# =====================================================
# 6. SQLITE VERİ TABANI FONKSİYONLARI
# =====================================================

DB_PATH = "sustainability_esg.db"


def get_db_connection(db_path: str = DB_PATH):
    # SQLite bağlantısı oluşturur.# 
    conn = sqlite3.connect(db_path)
    return conn


def init_database(db_path: str = DB_PATH):
    # Gerekli SQLite tablolarını oluşturur.# 
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS esg_indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            year TEXT,
            indicator_name TEXT,
            category TEXT,
            metric_type TEXT,
            value TEXT,
            numeric_value REAL,
            unit TEXT,
            page INTEGER,
            source_keyword TEXT,
            evidence_text TEXT,
            confidence REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def clear_indicator_data_cache():
    for cached_loader in [load_indicators_from_database, load_indicators_from_postgres]:
        clear_cache = getattr(cached_loader, "clear", None)
        if clear_cache:
            clear_cache()




def save_indicators_to_database(df: pd.DataFrame, db_path: str = DB_PATH) -> int:
    # LLM ile çıkarılan göstergeleri SQLite veri tabanına kaydeder.# 
    if df.empty:
        return 0

    init_database(db_path)
    conn = get_db_connection(db_path)

    save_cols = [
        "company_name",
        "year",
        "indicator_name",
        "category",
        "metric_type",
        "value",
        "numeric_value",
        "unit",
        "page",
        "source_keyword",
        "evidence_text",
        "confidence",
        "notes",
    ]

    temp = df.copy()

    for col in save_cols:
        if col not in temp.columns:
            temp[col] = None

    temp = temp[save_cols]

    before_count = pd.read_sql_query("SELECT COUNT(*) AS n FROM esg_indicators", conn)["n"].iloc[0]

    temp.to_sql("esg_indicators", conn, if_exists="append", index=False)

    # Basit tekrar temizliği: aynı şirket-yıl-gösterge-değer-sayfa-kanıt metni tekrarlarını siler.
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM esg_indicators
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM esg_indicators
            GROUP BY company_name, year, indicator_name, value, unit, page, evidence_text
        )
        """
    )

    conn.commit()

    after_count = pd.read_sql_query("SELECT COUNT(*) AS n FROM esg_indicators", conn)["n"].iloc[0]
    conn.close()

    clear_indicator_data_cache()

    return int(after_count - before_count)


@st.cache_data(show_spinner=False, ttl=60)
def load_indicators_from_database(db_path: str = DB_PATH) -> pd.DataFrame:
    # SQLite veri tabanındaki tüm ESG göstergelerini okur.# 
    init_database(db_path)
    conn = get_db_connection(db_path)

    df = pd.read_sql_query(
        """
        SELECT
            company_name,
            year,
            indicator_name,
            category,
            metric_type,
            value,
            numeric_value,
            unit,
            page,
            source_keyword,
            evidence_text,
            confidence,
            notes,
            created_at
        FROM esg_indicators
        ORDER BY company_name, year, indicator_name, page
        """,
        conn,
    )

    conn.close()
    return df


def delete_database_records(company_name: Optional[str] = None, db_path: str = DB_PATH):
    # Tüm kayıtları veya seçili şirket kayıtlarını siler.# 
    if not can_admin():
        raise PermissionError("SQLite kayıtlarını silmek için admin yetkisi gerekir.")

    init_database(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    if company_name:
        cur.execute("DELETE FROM esg_indicators WHERE company_name = ?", (company_name,))
    else:
        cur.execute("DELETE FROM esg_indicators")

    conn.commit()
    conn.close()
    clear_indicator_data_cache()


def make_database_excel_file(db_df: pd.DataFrame) -> bytes:
    # Veri tabanı kayıtlarını Excel dosyasına yazar.# 
    derived_df = compute_automatic_derived_indicators(db_df)
    panel_df = build_company_year_panel(db_df)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        db_df.to_excel(writer, index=False, sheet_name="database_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="database_derived")
        panel_df.to_excel(writer, index=False, sheet_name="database_panel")

        if not db_df.empty and "metric_type" in db_df.columns:
            metric_summary = (
                db_df.groupby(["company_name", "year", "metric_type"])
                .size()
                .reset_index(name="count")
            )
            metric_summary.to_excel(writer, index=False, sheet_name="metric_type_summary")

    return output.getvalue()




# =====================================================
# 7. TOPLU PDF İŞLEME FONKSİYONLARI
# =====================================================


def bulk_process_single_pdf(
    uploaded_pdf,
    company_name: str,
    report_year: str,
    keywords: List[str],
    context_sentences: int,
    max_evidence_rows_for_llm: int,
    model_name: str,
    api_key: Optional[str],
) -> Dict:
    """
    Tek PDF için:
    1. PDF metin çıkarır
    2. Anahtar kelime tarar
    3. LLM ile gösterge çıkarır
    4. SQLite veri tabanına kaydeder
    """
    pages = extract_pdf_text_by_page(uploaded_pdf)

    evidence_df = search_keywords_in_pdf_pages(
        pages=pages,
        keywords=keywords,
        context_sentences=context_sentences,
    )

    if evidence_df.empty:
        return {
            "company_name": company_name,
            "year": report_year,
            "file_name": uploaded_pdf.name,
            "page_count": len(pages),
            "evidence_count": 0,
            "extracted_count": 0,
            "saved_count": 0,
            "status": "Anahtar kelime eşleşmesi bulunamadı",
            "error": "",
        }

    evidence_df_for_llm = evidence_df.copy()
    evidence_df_for_llm["evidence_length"] = evidence_df_for_llm["evidence_text"].astype(str).str.len()
    evidence_df_for_llm = (
        evidence_df_for_llm.sort_values(["page", "keyword", "evidence_length"])
        .drop_duplicates(subset=["page", "keyword"])
        .head(int(max_evidence_rows_for_llm))
        .reset_index(drop=True)
    )

    extracted_df = llm_extract_indicators(
        evidence_df=evidence_df_for_llm,
        company_name=company_name,
        report_year=report_year,
        model_name=model_name,
        api_key=api_key,
    )

    if extracted_df.empty:
        return {
            "company_name": company_name,
            "year": report_year,
            "file_name": uploaded_pdf.name,
            "page_count": len(pages),
            "evidence_count": len(evidence_df),
            "extracted_count": 0,
            "saved_count": 0,
            "status": "LLM geçerli gösterge çıkaramadı",
            "error": "",
        }

    add_to_master_dataset(extracted_df)
    persistence_result = save_indicators_to_default_stores(extracted_df)

    return {
        "company_name": company_name,
        "year": report_year,
        "file_name": uploaded_pdf.name,
        "page_count": len(pages),
        "evidence_count": len(evidence_df),
        "extracted_count": len(extracted_df),
        "saved_count": persistence_result.get("sqlite_saved_count", 0),
        "postgres_saved_count": persistence_result.get("postgres_saved_count", 0),
        "postgres_error": persistence_result.get("postgres_error", ""),
        "status": "Başarılı",
        "error": "",
    }


def make_bulk_summary_excel_file(summary_df: pd.DataFrame, db_df: pd.DataFrame) -> bytes:
    """
    Toplu işlem özeti ve güncel veri tabanı çıktısını Excel'e yazar.
    """
    derived_df = compute_automatic_derived_indicators(db_df)
    panel_df = build_company_year_panel(db_df)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="bulk_process_summary")
        db_df.to_excel(writer, index=False, sheet_name="database_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="database_derived")
        panel_df.to_excel(writer, index=False, sheet_name="database_panel")

    return output.getvalue()



# =====================================================
# 8. SPSS / STATA / MODELLEME ÇIKTI FONKSİYONLARI
# =====================================================

def standardize_column_name(name: str) -> str:
    """
    SPSS/Stata uyumlu kısa değişken adı üretir.
    """
    text = str(name or "").lower()
    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
    }

    for tr_char, en_char in replacements.items():
        text = text.replace(tr_char, en_char)

    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")

    if not text:
        text = "var"

    if re.match(r"^\d", text):
        text = "v_" + text

    return text[:32]


def build_model_ready_dataset(db_df: pd.DataFrame) -> pd.DataFrame:
    """
    Veri tabanındaki göstergeleri modelleme için geniş form panel veriye çevirir.
    Sadece actual_value ve ratio türündeki numeric_value kayıtlarını kullanır.
    """
    if db_df.empty:
        return pd.DataFrame()

    temp = db_df.copy()

    if "metric_type" in temp.columns:
        temp = temp[temp["metric_type"].isin(["actual_value", "ratio"])].copy()

    temp = temp[temp["numeric_value"].notna()].copy()

    if temp.empty:
        return pd.DataFrame()

    temp["variable_name"] = temp["indicator_name"].apply(standardize_column_name)

    model_df = temp.pivot_table(
        index=["company_name", "year"],
        columns="variable_name",
        values="numeric_value",
        aggfunc="first",
    ).reset_index()

    model_df.columns.name = None
    model_df["year"] = pd.to_numeric(model_df["year"], errors="coerce").astype("Int64")

    return model_df


def build_variable_dictionary(db_df: pd.DataFrame) -> pd.DataFrame:
    """
    Değişken sözlüğü üretir.
    """
    if db_df.empty:
        return pd.DataFrame()

    temp = db_df.copy()
    temp["variable_name"] = temp["indicator_name"].apply(standardize_column_name)

    dict_df = (
        temp[
            [
                "variable_name",
                "indicator_name",
                "category",
                "metric_type",
                "unit",
                "source_keyword",
            ]
        ]
        .drop_duplicates()
        .sort_values(["variable_name", "indicator_name"])
        .reset_index(drop=True)
    )

    return dict_df


def make_modeling_excel_file(db_df: pd.DataFrame) -> bytes:
    """
    Modelleme için Excel çıktısı üretir.
    """
    model_df = build_model_ready_dataset(db_df)
    dictionary_df = build_variable_dictionary(db_df)
    derived_df = compute_automatic_derived_indicators(db_df)
    full_panel_df = build_company_year_panel(db_df)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        model_df.to_excel(writer, index=False, sheet_name="model_ready_panel")
        full_panel_df.to_excel(writer, index=False, sheet_name="full_panel_all_metrics")
        db_df.to_excel(writer, index=False, sheet_name="long_format_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="derived_indicators")
        dictionary_df.to_excel(writer, index=False, sheet_name="variable_dictionary")

    return output.getvalue()


def make_csv_bytes(df: pd.DataFrame) -> bytes:
    """
    UTF-8 BOM ile CSV üretir. Excel, SPSS ve Stata için daha uyumludur.
    """
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def generate_stata_do_file(model_df: pd.DataFrame, dictionary_df: pd.DataFrame) -> str:
    """
    Stata için başlangıç do-file metni üretir.
    """
    numeric_vars = [
        c for c in model_df.columns
        if c not in ["company_name", "year"]
    ]

    label_lines = []

    for _, row in dictionary_df.iterrows():
        var_name = row.get("variable_name")
        label = str(row.get("indicator_name", ""))[:80].replace('"', "'")

        if var_name in numeric_vars:
            label_lines.append(f'label variable {var_name} "{label}"')

    label_text = chr(10).join(label_lines)

    do_text = (
        "* Sustainability ESG model-ready dataset\n"
        "* CSV dosyasını Stata'ya aktarma örneği\n\n"
        "clear all\n"
        "set more off\n\n"
        "* Çalışma dizinini kendi klasörünüze göre düzenleyin\n"
        "* cd \"C:/Users/ibrah/sustainability-agent\"\n\n"
        "import delimited \"model_ready_panel.csv\", clear encoding(UTF-8)\n\n"
        "encode company_name, gen(company_id)\n"
        "xtset company_id year\n\n"
        "* Değişken etiketleri\n"
        f"{label_text}\n\n"
        "* Veri özeti\n"
        "describe\n"
        "summarize\n\n"
        "* Örnek panel regresyon şablonu\n"
        "* Aşağıdaki y ve x değişkenlerini kendi modelinize göre değiştiriniz.\n"
        "* xtreg y x1 x2 x3 i.year, fe vce(cluster company_id)\n"
        "* xtreg y x1 x2 x3 i.year, re vce(cluster company_id)\n"
        "* hausman fe re\n\n"
        "save \"model_ready_panel.dta\", replace\n"
    )

    return do_text


def generate_spss_syntax_file(model_df: pd.DataFrame, dictionary_df: pd.DataFrame) -> str:
    """
    SPSS için başlangıç syntax metni üretir.
    """
    label_lines = []

    for _, row in dictionary_df.iterrows():
        var_name = row.get("variable_name")
        label = str(row.get("indicator_name", ""))[:120].replace('"', "'")

        if var_name in model_df.columns:
            label_lines.append(f'  {var_name} "{label}"')

    if label_lines:
        label_block = "VARIABLE LABELS\n" + "\n".join(label_lines) + "."
    else:
        label_block = "* Değişken etiketi bulunamadı."

    syntax = (
        "* Sustainability ESG model-ready dataset.\n"
        "* CSV dosyasını SPSS'e aktarma örneği.\n"
        "* Dosya yolunu kendi bilgisayarınıza göre düzenleyiniz.\n\n"
        "GET DATA\n"
        "  /TYPE=TXT\n"
        "  /FILE=\"C:\\\\Users\\\\ibrah\\\\sustainability-agent\\\\model_ready_panel.csv\"\n"
        "  /ENCODING='UTF8'\n"
        "  /DELCASE=LINE\n"
        "  /DELIMITERS=\",\"\n"
        "  /ARRANGEMENT=DELIMITED\n"
        "  /FIRSTCASE=2\n"
        "  /IMPORTCASE=ALL\n"
        "  /VARIABLES=\n"
        "    company_name A80\n"
        "    year F8.0\n"
        "    ALL AUTO.\n"
        "CACHE.\n"
        "EXECUTE.\n\n"
        f"{label_block}\n\n"
        "DATASET NAME ESGPanel.\n\n"
        "DESCRIPTIVES VARIABLES=ALL.\n\n"
        "* Örnek regresyon şablonu.\n"
        "* REGRESSION\n"
        "*   /DEPENDENT y\n"
        "*   /METHOD=ENTER x1 x2 x3.\n"
    )

    return syntax



# =====================================================
# 9. POSTGRESQL FONKSİYONLARI
# =====================================================

def get_postgres_connection(database_url: str):
    """
    PostgreSQL bağlantısı oluşturur.
    Gerekli paket: pip install psycopg2-binary
    """
    try:
        import psycopg2
    except Exception as exc:
        raise RuntimeError(
            "psycopg2-binary paketi yüklü değil. PowerShell'de şu komutu çalıştırın: pip install psycopg2-binary"
        ) from exc

    return psycopg2.connect(database_url)


def init_postgres_database(database_url: str):
    """
    PostgreSQL tarafında ESG göstergeleri tablosunu oluşturur.
    """
    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute(
    """
    CREATE TABLE IF NOT EXISTS esg_indicators (
        id SERIAL PRIMARY KEY,
        company_name TEXT,
        year TEXT,
        indicator_name TEXT,
        category TEXT,
        metric_type TEXT,
        value TEXT,
        numeric_value DOUBLE PRECISION,
        unit TEXT,
        page INTEGER,
        source_keyword TEXT,
        evidence_text TEXT,
        confidence DOUBLE PRECISION,
        notes TEXT,
        user_id INTEGER,
        username TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
       )
    """
    )

    cur.execute(
    """
    ALTER TABLE esg_indicators
    ADD COLUMN IF NOT EXISTS user_id INTEGER
    """
    )

    cur.execute(
    """
    ALTER TABLE esg_indicators
    ADD COLUMN IF NOT EXISTS username TEXT
    """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_esg_company_year
        ON esg_indicators (company_name, year)
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_esg_indicator
        ON esg_indicators (indicator_name)
        """
    )

    conn.commit()
    cur.close()
    conn.close()


def save_indicators_to_postgres(df: pd.DataFrame, database_url: str) -> int:
    """
    LLM ile çıkarılan göstergeleri PostgreSQL veri tabanına kaydeder.
    Tekrar kayıtları basit benzersizlik mantığıyla temizler.
    """
    if df.empty:
        return 0

    try:
        from psycopg2.extras import execute_values
    except Exception as exc:
        raise RuntimeError(
            "psycopg2-binary paketi yüklü değil. PowerShell'de şu komutu çalıştırın: pip install psycopg2-binary"
        ) from exc

    init_postgres_database(database_url)
    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    save_cols = [
        "company_name",
        "year",
        "indicator_name",
        "category",
        "metric_type",
        "value",
        "numeric_value",
        "unit",
        "page",
        "source_keyword",
        "evidence_text",
        "confidence",
        "notes",
        "user_id",
        "username",
    ]

    temp = df.copy()

    temp["user_id"] = st.session_state.get("user_id")
    temp["username"] = st.session_state.get("username")

    for col in save_cols:
        if col not in temp.columns:
            temp[col] = None    
    
    temp = temp[save_cols]

    rows = []
    for _, row in temp.iterrows():
        rows.append(
            tuple(None if pd.isna(row[col]) else row[col] for col in save_cols)
        )

    cur.execute("SELECT COUNT(*) FROM esg_indicators")
    before_count = cur.fetchone()[0]

    insert_sql = """
        INSERT INTO esg_indicators (
            company_name, year, indicator_name, category, metric_type,
            value, numeric_value, unit, page, source_keyword,
            evidence_text, confidence, notes, user_id, username
        )
        VALUES %s
    """

    execute_values(cur, insert_sql, rows)

    cur.execute(
        """
        DELETE FROM esg_indicators a
        USING esg_indicators b
        WHERE a.id > b.id
          AND COALESCE(a.company_name, '') = COALESCE(b.company_name, '')
          AND COALESCE(a.year, '') = COALESCE(b.year, '')
          AND COALESCE(a.indicator_name, '') = COALESCE(b.indicator_name, '')
          AND COALESCE(a.value, '') = COALESCE(b.value, '')
          AND COALESCE(a.unit, '') = COALESCE(b.unit, '')
          AND COALESCE(a.page, -1) = COALESCE(b.page, -1)
          AND COALESCE(a.evidence_text, '') = COALESCE(b.evidence_text, '')
          AND COALESCE(a.user_id, -1) = COALESCE(b.user_id, -1)
    """
    )

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM esg_indicators")
    after_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    clear_indicator_data_cache()

    return int(after_count - before_count)


@st.cache_data(show_spinner=False, ttl=60)
def load_indicators_from_postgres(database_url: str) -> pd.DataFrame:
    """
    PostgreSQL veri tabanındaki tüm ESG göstergelerini okur.
    """
    init_postgres_database(database_url)
    conn = get_postgres_connection(database_url)

    df = pd.read_sql_query(
        """
        SELECT
            company_name,
            year,
            indicator_name,
            category,
            metric_type,
            value,
            numeric_value,
            unit,
            page,
            source_keyword,
            evidence_text,
            confidence,
            notes,
            user_id,
            username,
            created_at
        FROM esg_indicators
        ORDER BY company_name, year, indicator_name, page
        """,
        conn,
    )

    conn.close()
    return df


def delete_postgres_records(database_url: str, company_name: Optional[str] = None):
    # PostgreSQL'de tüm kayıtları veya seçili şirket kayıtlarını siler.
    # Sadece admin kullanıcı silebilir.

    if not can_admin():
        st.warning("Kayıt silme yetkisi sadece admin kullanıcılara aittir.")
        return

    init_postgres_database(database_url)
    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    if company_name:
        cur.execute("DELETE FROM esg_indicators WHERE company_name = %s", (company_name,))
    else:
        cur.execute("DELETE FROM esg_indicators")

    conn.commit()
    cur.close()
    conn.close()
    clear_indicator_data_cache()

def migrate_sqlite_to_postgres(database_url: str) -> int:
    # Mevcut SQLite kayıtlarını PostgreSQL'e taşır.

    if not can_admin():
        st.warning("SQLite kayıtlarını PostgreSQL'e taşıma yetkisi sadece admin kullanıcılara aittir.")
        return 0

    sqlite_df = load_indicators_from_database()

    if sqlite_df.empty:
        return 0

    return save_indicators_to_postgres(sqlite_df, database_url)


def make_postgres_excel_file(pg_df: pd.DataFrame) -> bytes:
    # PostgreSQL kayıtlarını Excel dosyasına yazar.

    derived_df = compute_automatic_derived_indicators(pg_df)
    panel_df = build_company_year_panel(pg_df)
    model_df = build_model_ready_dataset(pg_df)
    dictionary_df = build_variable_dictionary(pg_df)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pg_df.to_excel(writer, index=False, sheet_name="postgres_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="postgres_derived")
        panel_df.to_excel(writer, index=False, sheet_name="postgres_full_panel")
        model_df.to_excel(writer, index=False, sheet_name="model_ready_panel")
        dictionary_df.to_excel(writer, index=False, sheet_name="variable_dictionary")

    return output.getvalue()



# =====================================================
# 10. URL'DEN PDF İNDİRME VE İŞLEME FONKSİYONLARI
# =====================================================

def parse_report_links_table(text: str) -> pd.DataFrame:
    # Şirket,Yıl,URL satırlarını DataFrame'e çevirir.
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().replace(" ", "") in ["şirket,yıl,url", "sirket,yil,url", "company,year,url"]:
            continue

        if "," in line:
            parts = [p.strip() for p in line.split(",", maxsplit=2)]
            if len(parts) == 3:
                company, year, url = parts
            elif len(parts) == 2:
                company, url = parts
                year = ""
            else:
                company, year, url = "", "", line
        else:
            company, year, url = "", "", line

        if not url.lower().startswith(("http://", "https://")):
            continue

        if not company:
            company, guessed_year = parse_company_year_from_filename(url.split("/")[-1])
            year = year or guessed_year

        if not year:
            m = re.search(r"(20\d{2})", url)
            year = m.group(1) if m else "2024"

        rows.append({"company_name": company, "year": year, "url": url})
    return pd.DataFrame(rows)


def download_pdf_from_url(url: str, timeout: int = 60) -> bytes:
    # URL'den PDF indirir.
    headers = {"User-Agent": "Mozilla/5.0 Sustainability ESG Research Bot"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        if not response.content.startswith(b"%PDF"):
            raise ValueError(f"İndirilen içerik PDF gibi görünmüyor. Content-Type: {content_type}")
    return response.content


class DownloadedPDF:
    # Streamlit uploaded_file benzeri PDF nesnesi.# 
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def read(self):
        return self._content


def safe_filename_from_url(url: str, company_name: str, year: str) -> str:
    # Güvenli PDF dosya adı üretir.# 
    last_part = url.split("/")[-1].split("?")[0]
    if last_part.lower().endswith(".pdf") and len(last_part) > 4:
        return last_part
    safe_company = standardize_column_name(company_name)[:40]
    return f"{safe_company}_{year}.pdf"


def process_pdf_url_record(
    company_name: str,
    report_year: str,
    url: str,
    keywords: List[str],
    context_sentences: int,
    max_evidence_rows_for_llm: int,
    model_name: str,
    api_key: Optional[str],
    save_to_postgres: bool,
    postgres_url: Optional[str],
) -> Dict:
    #  Tek PDF URL'sini indirir, işler, SQLite'a ve istenirse PostgreSQL'e kaydeder.
    pdf_bytes = download_pdf_from_url(url)
    pdf_obj = DownloadedPDF(safe_filename_from_url(url, company_name, report_year), pdf_bytes)

    result = bulk_process_single_pdf(
        uploaded_pdf=pdf_obj,
        company_name=company_name,
        report_year=report_year,
        keywords=keywords,
        context_sentences=context_sentences,
        max_evidence_rows_for_llm=max_evidence_rows_for_llm,
        model_name=model_name,
        api_key=api_key,
    )
    result["url"] = url
    result["downloaded_bytes"] = len(pdf_bytes)

    if save_to_postgres and postgres_url:
        sqlite_df = load_indicators_from_database()
        subset = sqlite_df[
            (sqlite_df["company_name"].astype(str) == str(company_name))
            & (sqlite_df["year"].astype(str) == str(report_year))
        ].copy()
        result["postgres_saved_count"] = save_indicators_to_postgres(subset, postgres_url) if not subset.empty else 0
        result["postgres_error"] = ""
    else:
        result["postgres_saved_count"] = 0
        result["postgres_error"] = ""

    return result


def make_url_processing_excel_file(summary_df: pd.DataFrame, db_df: pd.DataFrame) -> bytes:
    # URL işleme özeti ve güncel veri tabanını Excel'e yazar.
    derived_df = compute_automatic_derived_indicators(db_df)
    panel_df = build_company_year_panel(db_df)
    model_df = build_model_ready_dataset(db_df)
    dictionary_df = build_variable_dictionary(db_df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="url_process_summary")
        db_df.to_excel(writer, index=False, sheet_name="sqlite_indicators")
        derived_df.to_excel(writer, index=False, sheet_name="derived_indicators")
        panel_df.to_excel(writer, index=False, sheet_name="full_panel")
        model_df.to_excel(writer, index=False, sheet_name="model_ready_panel")
        dictionary_df.to_excel(writer, index=False, sheet_name="variable_dictionary")
    return output.getvalue()



# =====================================================
# 11. BIST HAZIR RAPOR LİNKLERİ FONKSİYONLARI
# =====================================================

BIST_SAMPLE_REPORT_LINKS = [
    {
        "company_name": "Akbank",
        "ticker": "AKBNK",
        "year": "2024",
        "report_type": "Entegre Faaliyet Raporu",
        "url": "https://www.akbankinvestorrelations.com/tr/images/pdf/akbank-2024-entegre-faaliyet-raporu.pdf",
        "note": "Link zamanla değişebilir; çalışmazsa şirket yatırımcı ilişkileri sayfasından güncellenmelidir.",
    },
    {
        "company_name": "Türk Hava Yolları",
        "ticker": "THYAO",
        "year": "2024",
        "report_type": "Faaliyet Raporu",
        "url": "https://investor.turkishairlines.com/documents/yillik-raporlar/2024-faaliyet-raporu.pdf",
        "note": "Link zamanla değişebilir; çalışmazsa yatırımcı ilişkileri sayfasından güncellenmelidir.",
    },
    {
        "company_name": "Arçelik",
        "ticker": "ARCLK",
        "year": "2024",
        "report_type": "Sürdürülebilirlik / Entegre Rapor",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri veya sürdürülebilirlik raporları sayfasından ekleyiniz.",
    },
    {
        "company_name": "Garanti BBVA",
        "ticker": "GARAN",
        "year": "2024",
        "report_type": "Entegre Faaliyet Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Koç Holding",
        "ticker": "KCHOL",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Sabancı Holding",
        "ticker": "SAHOL",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Tüpraş",
        "ticker": "TUPRS",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Ford Otosan",
        "ticker": "FROTO",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Migros",
        "ticker": "MGROS",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
    {
        "company_name": "Şişecam",
        "ticker": "SISE",
        "year": "2024",
        "report_type": "Faaliyet / Sürdürülebilirlik Raporu",
        "url": "",
        "note": "URL'yi şirketin yatırımcı ilişkileri sayfasından ekleyiniz.",
    },
]


def get_bist_report_links_df() -> pd.DataFrame:
    # Hazır BIST rapor linkleri tablosunu döndürür.
    return pd.DataFrame(BIST_SAMPLE_REPORT_LINKS)


def make_url_text_from_bist_df(df: pd.DataFrame) -> str:
    
    # BIST rapor linkleri tablosundan URL işleme sekmesine yapıştırılacak metin üretir.
    # Sadece URL alanı dolu satırları alır.
    
    lines = []

    if df.empty:
        return ""

    for _, row in df.iterrows():
        company = str(row.get("company_name", "")).strip()
        year = str(row.get("year", "")).strip()
        url = str(row.get("url", "")).strip()

        if company and year and url and url.lower().startswith(("http://", "https://")):
            lines.append(f"{company},{year},{url}")

    return "\n".join(lines)


def make_bist_links_excel_file(df: pd.DataFrame) -> bytes:
    # BIST rapor linkleri tablosunu Excel'e yazar.
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="bist_report_links")

    return output.getvalue()



# =====================================================
# 12. ESG SÖZLÜK + KALİTE KONTROL + GÜVENLİ DB FONKSİYONLARI
# =====================================================

def make_quality_control_excel_file(source_df: pd.DataFrame, standardized_df: pd.DataFrame, issues_df: pd.DataFrame, standardized_model_df: pd.DataFrame, dictionary_df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        source_df.to_excel(writer, index=False, sheet_name="source_data")
        standardized_df.to_excel(writer, index=False, sheet_name="standardized_data")
        issues_df.to_excel(writer, index=False, sheet_name="quality_issues")

        if not issues_df.empty:
            issue_summary = issues_df.groupby(["severity", "issue_type"]).size().reset_index(name="count")
            issue_summary.to_excel(writer, index=False, sheet_name="issue_summary")
            issues_df[issues_df["issue_type"] == "low_confidence"].to_excel(writer, index=False, sheet_name="low_confidence")
            issues_df[issues_df["issue_type"] == "unit_conversion_applied"].to_excel(writer, index=False, sheet_name="unit_conversions")
            issues_df[issues_df["issue_type"] == "conflicting_standard_value"].to_excel(writer, index=False, sheet_name="value_conflicts")

        standardized_model_df.to_excel(writer, index=False, sheet_name="standard_model_panel")
        dictionary_df.to_excel(writer, index=False, sheet_name="esg_dictionary")
    return output.getvalue()

def get_secure_database_url() -> str:
    try:
        secret_url = st.secrets.get("DATABASE_URL", "")
        if secret_url:
            return secret_url
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "")

def mask_database_url(database_url: str) -> str:
    if not database_url:
        return ""
    return re.sub(r":([^:@/]+)@", ":****@", database_url)



from sustainability_pdf import (
    clear_pdf_text_cache,
    extract_pdf_text_by_page,
    make_pdf_scan_excel_file,
    search_keywords_in_pdf_pages,
)
from sustainability_utils import (
    add_standardized_columns,
    build_standardized_model_ready_dataset,
    classify_metric_type,
    extract_indicator_records_from_response,
    extract_json_from_response,
    filter_tabs_for_focus,
    get_esg_dictionary_df,
    get_llm_response_text_format,
    get_visible_tabs_for_role,
    map_indicator_to_standard,
    normalize_extracted_indicator_records,
    normalize_for_matching,
    normalize_number,
    normalize_unit_value,
    parse_company_year_from_filename,
    run_data_quality_checks,
)

# =====================================================
# 13. OTOMATİK POSTGRESQL KAYIT FONKSİYONLARI
# =====================================================

def save_indicators_to_default_stores(df: pd.DataFrame) -> Dict:
   
    # ESG göstergelerini varsayılan kalıcı kayıt akışına yazar.

    # Akış:
    # 1. SQLite'a kaydet.
    # 2. DATABASE_URL varsa PostgreSQL'e de kaydet.
    # 3. PostgreSQL hatası uygulamayı durdurmaz; sonuç sözlüğünde raporlanır.
   
    result = {
        "sqlite_saved_count": 0,
        "postgres_saved_count": 0,
        "postgres_enabled": False,
        "postgres_error": "",
    }

    if df.empty:
        return result

    # 1. SQLite her zaman yerel/varsayılan kayıt alanı
    try:
        result["sqlite_saved_count"] = save_indicators_to_database(df)
    except Exception as exc:
        result["sqlite_error"] = str(exc)

    # 2. PostgreSQL: secrets veya ortam değişkeni varsa otomatik
    pg_url = get_secure_database_url()

    if pg_url:
        result["postgres_enabled"] = True
        try:
            result["postgres_saved_count"] = save_indicators_to_postgres(df, pg_url)
        except Exception as exc:
            result["postgres_error"] = str(exc)
    else:
        result["postgres_enabled"] = False
        result["postgres_error"] = "DATABASE_URL bulunamadı; PostgreSQL kaydı atlandı."

    return result


def show_persistence_result(result: Dict):
    
    # Kayıt sonucunu Streamlit arayüzünde anlaşılır şekilde gösterir.
    
    sqlite_count = result.get("sqlite_saved_count", 0)
    postgres_count = result.get("postgres_saved_count", 0)
    postgres_enabled = result.get("postgres_enabled", False)
    postgres_error = result.get("postgres_error", "")

    st.info(f"SQLite kayıt sonucu: yeni kayıt sayısı = {sqlite_count}")

    if postgres_enabled and not postgres_error:
        st.success(f"PostgreSQL otomatik kayıt başarılı. Yeni kayıt sayısı = {postgres_count}")
    elif postgres_enabled and postgres_error:
        st.warning(f"PostgreSQL otomatik kayıt denenmiş ancak hata oluştu: {postgres_error}")
    else:
        st.warning("DATABASE_URL bulunamadığı için PostgreSQL otomatik kayıt yapılmadı.")


def load_default_database_status() -> Dict:
   
    # Varsayılan veri kayıt durumu hakkında kısa bilgi üretir.
    
    pg_url = get_secure_database_url()

    status = {
        "sqlite_available": True,
        "sqlite_path": DB_PATH,
        "postgres_available": bool(pg_url),
        "postgres_url_masked": mask_database_url(pg_url) if pg_url else "",
    }

    return status


def render_sidebar_status_panel(role: str):
    with st.sidebar.expander("Durum paneli", expanded=True):
        st.write(f"Rol: **{role}**")

        try:
            sqlite_df = load_indicators_from_database()
            st.write(f"SQLite kayıt: **{len(sqlite_df)}**")
        except Exception as exc:
            st.warning(f"SQLite durumu okunamadı: {exc}")

        db_status = load_default_database_status()
        if db_status["postgres_available"]:
            st.write("PostgreSQL: **aktif**")
            st.caption(db_status["postgres_url_masked"])
        else:
            st.write("PostgreSQL: **pasif**")

        master_df = st.session_state.get("master_indicators_df", pd.DataFrame())
        st.write(f"Oturum veri seti: **{len(master_df)}**")

        if st.button("Veri cache'ini yenile"):
            clear_indicator_data_cache()
            clear_pdf_text_cache()
            st.rerun()



# =====================================================
# 14. BIST RAPOR LİNKİ ARAMA / DOĞRULAMA FONKSİYONLARI
# =====================================================

def validate_report_url(url: str, expected_year: str = "", timeout: int = 20) -> Dict:
    # Bir rapor URL'sini doğrular.
    # Kontroller:
    # - URL erişilebilir mi?
    # - HTTP durum kodu nedir?
    # - Content-Type PDF mi?
    # - İçerik PDF başlığıyla mı başlıyor?
    # - Dosya boyutu nedir?
    # - URL içinde beklenen yıl geçiyor mu?
    # - Basit doğrulama skoru
    
    result = {
        "url": url,
        "status_code": None,
        "is_accessible": False,
        "content_type": None,
        "is_pdf_content_type": False,
        "starts_with_pdf_header": False,
        "content_length_bytes": None,
        "content_length_mb": None,
        "year_in_url": False,
        "validation_score": 0,
        "validation_status": "invalid",
        "error": "",
    }

    if not url or not str(url).lower().startswith(("http://", "https://")):
        result["error"] = "Geçerli http/https URL değil."
        return result

    headers = {
        "User-Agent": "Mozilla/5.0 Sustainability ESG Research Bot"
    }

    try:
        # Önce HEAD dene
        try:
            head_response = requests.head(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            response_for_meta = head_response
        except Exception:
            response_for_meta = None

        # Bazı sunucular HEAD'i engeller. Küçük GET ile kontrol edelim.
        get_response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )

        result["status_code"] = get_response.status_code
        result["is_accessible"] = 200 <= get_response.status_code < 400

        content_type = get_response.headers.get("Content-Type", "")
        if not content_type and response_for_meta is not None:
            content_type = response_for_meta.headers.get("Content-Type", "")

        result["content_type"] = content_type
        result["is_pdf_content_type"] = "pdf" in str(content_type).lower()

        content_length = get_response.headers.get("Content-Length")
        if not content_length and response_for_meta is not None:
            content_length = response_for_meta.headers.get("Content-Length")

        if content_length:
            try:
                result["content_length_bytes"] = int(content_length)
                result["content_length_mb"] = round(int(content_length) / (1024 * 1024), 2)
            except Exception:
                pass

        first_chunk = b""
        try:
            first_chunk = next(get_response.iter_content(chunk_size=5))
        except Exception:
            first_chunk = b""

        result["starts_with_pdf_header"] = first_chunk.startswith(b"%PDF")
        result["year_in_url"] = bool(expected_year and str(expected_year) in url)

        score = 0

        if result["is_accessible"]:
            score += 30

        if result["is_pdf_content_type"]:
            score += 25

        if result["starts_with_pdf_header"]:
            score += 25

        if result["year_in_url"]:
            score += 10

        if result["content_length_bytes"] and result["content_length_bytes"] > 100_000:
            score += 10

        result["validation_score"] = score

        if score >= 70:
            result["validation_status"] = "strong"
        elif score >= 40:
            result["validation_status"] = "possible"
        else:
            result["validation_status"] = "weak"

    except Exception as exc:
        result["error"] = str(exc)

    return result


def parse_candidate_report_links(text: str) -> pd.DataFrame:
    # Aday BIST rapor linklerini tabloya dönüştürür.
    # Kabul edilen format:
    # Şirket,Yıl,URL
    # veya sadece URL
    # 
    return parse_report_links_table(text)


def validate_candidate_links_df(df: pd.DataFrame) -> pd.DataFrame:
    # Aday link tablosundaki tüm URL'leri doğrular.
    
    if df.empty:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        company = str(row.get("company_name", "")).strip()
        year = str(row.get("year", "")).strip()
        url = str(row.get("url", "")).strip()

        validation = validate_report_url(url, expected_year=year)
        validation["company_name"] = company
        validation["year"] = year

        rows.append(validation)

    result_df = pd.DataFrame(rows)

    preferred_cols = [
        "company_name",
        "year",
        "url",
        "validation_status",
        "validation_score",
        "status_code",
        "is_accessible",
        "is_pdf_content_type",
        "starts_with_pdf_header",
        "content_length_mb",
        "year_in_url",
        "content_type",
        "error",
    ]

    existing = [c for c in preferred_cols if c in result_df.columns]
    other = [c for c in result_df.columns if c not in existing]

    return result_df[existing + other]


def make_validated_links_url_text(validated_df: pd.DataFrame, minimum_score: int = 40) -> str:
    # Doğrulanmış linklerden URL işleme modülüne uygun metin üretir.
    

    if validated_df.empty:
        return ""

    temp = validated_df.copy()
    temp = temp[temp["validation_score"] >= minimum_score]

    lines = []

    for _, row in temp.iterrows():
        company = str(row.get("company_name", "")).strip()
        year = str(row.get("year", "")).strip()
        url = str(row.get("url", "")).strip()

        if company and year and url:
            lines.append(f"{company},{year},{url}")

    return "\n".join(lines)


def generate_search_queries_for_company(company_name: str, ticker: str, year: str) -> List[str]:
    
    # Web'de elle arama yapmak için hazır sorgu önerileri üretir.
    # Uygulama içinde arama motoru çağrısı yapmaz; kullanıcıya kopyalanabilir sorgu verir.
   
    pieces = []

    company = company_name.strip()
    ticker = ticker.strip()
    year = str(year).strip()

    if company:
        pieces.append(f'{company} {year} faaliyet raporu pdf')
        pieces.append(f'{company} {year} sürdürülebilirlik raporu pdf')
        pieces.append(f'{company} {year} entegre faaliyet raporu pdf')
        pieces.append(f'site:{company.lower().replace(" ", "")}.com {year} pdf sürdürülebilirlik raporu')

    if ticker:
        pieces.append(f'{ticker} {year} faaliyet raporu pdf')
        pieces.append(f'{ticker} {year} sustainability report pdf')

    return pieces


def make_link_validation_excel_file(candidate_df: pd.DataFrame, validated_df: pd.DataFrame, url_text: str) -> bytes:
    #  Link doğrulama sonuçlarını Excel dosyasına yazar.
     
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        candidate_df.to_excel(writer, index=False, sheet_name="candidate_links")
        validated_df.to_excel(writer, index=False, sheet_name="validated_links")

        url_text_df = pd.DataFrame(
            [{"url_processing_text": line} for line in url_text.splitlines() if line.strip()]
        )
        url_text_df.to_excel(writer, index=False, sheet_name="url_processing_text")

    return output.getvalue()



# =====================================================
# 15. n8n TAKİP EDİLEN RAPORLAR FONKSİYONLARI
# =====================================================

def init_report_tracking_tables(database_url: str):
    # n8n rapor takip tablolarını oluşturur.
    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS report_sources (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            ticker TEXT,
            report_year TEXT NOT NULL DEFAULT '2024',
            source_url TEXT NOT NULL,
            source_type TEXT DEFAULT 'investor_relations_page',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS report_link_checks (
            id SERIAL PRIMARY KEY,
            company_name TEXT,
            ticker TEXT,
            report_year TEXT,
            source_url TEXT,
            candidate_url TEXT,
            status_code INTEGER,
            content_type TEXT,
            is_pdf BOOLEAN,
            year_in_url BOOLEAN,
            validation_score INTEGER,
            validation_status TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_report_candidate
        ON report_link_checks (company_name, report_year, candidate_url)
        """
    )

    conn.commit()
    cur.close()
    conn.close()


def load_report_link_checks_from_postgres(database_url: str) -> pd.DataFrame:
    """
    n8n'in yazdığı report_link_checks tablosunu okur.
    """
    init_report_tracking_tables(database_url)
    conn = get_postgres_connection(database_url)

    df = pd.read_sql_query(
        """
        SELECT
            company_name,
            ticker,
            report_year,
            source_url,
            candidate_url,
            status_code,
            content_type,
            is_pdf,
            year_in_url,
            validation_score,
            validation_status,
            checked_at,
            error_message
        FROM report_link_checks
        ORDER BY checked_at DESC, validation_score DESC NULLS LAST
        """,
        conn,
    )

    conn.close()
    return df


def load_report_sources_from_postgres(database_url: str) -> pd.DataFrame:
    # n8n'in takip edeceği report_sources tablosunu okur.
    init_report_tracking_tables(database_url)
    conn = get_postgres_connection(database_url)

    df = pd.read_sql_query(
        """
        SELECT
            company_name,
            ticker,
            report_year,
            source_url,
            source_type,
            is_active,
            created_at
        FROM report_sources
        ORDER BY company_name, report_year
        """,
        conn,
    )

    conn.close()
    return df


def add_report_source_to_postgres(
    database_url: str,
    company_name: str,
    ticker: str,
    report_year: str,
    source_url: str,
    source_type: str = "reports_page",
):
    #report_sources tablosuna yeni takip kaynağı ekler.
    
    init_report_tracking_tables(database_url)
    conn = get_postgres_connection(database_url)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO report_sources (
            company_name, ticker, report_year, source_url, source_type, is_active
        )
        VALUES (%s, %s, %s, %s, %s, TRUE)
        """,
        (company_name, ticker, report_year, source_url, source_type),
    )

    conn.commit()
    cur.close()
    conn.close()


def make_n8n_validated_url_text(
    checks_df: pd.DataFrame,
    minimum_score: int = 40,
    statuses: Optional[List[str]] = None,
) -> str:
    """
    n8n link kontrol sonuçlarından URL işleme modülüne uygun metin üretir.
    """
    if checks_df.empty:
        return ""

    statuses = statuses or ["strong", "possible"]

    temp = checks_df.copy()

    if "validation_score" in temp.columns:
        temp["validation_score"] = pd.to_numeric(temp["validation_score"], errors="coerce").fillna(0)
        temp = temp[temp["validation_score"] >= minimum_score]

    if "validation_status" in temp.columns:
        temp = temp[temp["validation_status"].isin(statuses)]

    if "candidate_url" not in temp.columns:
        return ""

    temp = temp.drop_duplicates(subset=["company_name", "report_year", "candidate_url"])

    lines = []

    for _, row in temp.iterrows():
        company = str(row.get("company_name", "") or "").strip()
        year = str(row.get("report_year", "") or "").strip()
        url = str(row.get("candidate_url", "") or "").strip()

        if company and year and url:
            lines.append(f"{company},{year},{url}")

    return "\n".join(lines)


def make_n8n_report_links_excel_file(
    sources_df: pd.DataFrame,
    checks_df: pd.DataFrame,
    url_text: str,
) -> bytes:
    # n8n rapor takip sonuçlarını Excel dosyasına yazar.
    # 
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sources_df.to_excel(writer, index=False, sheet_name="report_sources")
        checks_df.to_excel(writer, index=False, sheet_name="report_link_checks")

        url_text_df = pd.DataFrame(
            [{"url_processing_text": line} for line in url_text.splitlines() if line.strip()]
        )
        url_text_df.to_excel(writer, index=False, sheet_name="url_processing_text")

        if not checks_df.empty:
            summary = (
                checks_df.groupby(["company_name", "report_year", "validation_status"])
                .size()
                .reset_index(name="count")
                .sort_values(["company_name", "report_year", "validation_status"])
            )
            summary.to_excel(writer, index=False, sheet_name="status_summary")

    return output.getvalue()



# =====================================================
# 16. AKADEMİK PANEL VERİ ANALİZİ FONKSİYONLARI
# =====================================================

def numeric_panel_columns(df: pd.DataFrame) -> List[str]:
    #  Panel veri setindeki sayısal analiz değişkenlerini döndürür.
    # company_name ve year haric tutulur.
    # 
    if df.empty:
        return []

    temp = df.copy()

    for col in temp.columns:
        if col not in ["company_name", "year"]:
            temp[col] = pd.to_numeric(temp[col], errors="coerce")

    numeric_cols = [
        c for c in temp.columns
        if c not in ["company_name", "year"] and pd.api.types.is_numeric_dtype(temp[c])
    ]

    return numeric_cols


def make_panel_descriptive_statistics(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    Akademik panel veri için tanımlayıcı istatistik tablosu üretir.
    """
    if panel_df.empty:
        return pd.DataFrame()

    temp = panel_df.copy()
    numeric_cols = [c for c in temp.columns if c not in ["company_name", "year"]]

    for col in numeric_cols:
        temp[col] = pd.to_numeric(temp[col], errors="coerce")

    rows = []

    for col in numeric_cols:
        series = temp[col].dropna()

        if series.empty:
            rows.append(
                {
                    "variable": col,
                    "n": 0,
                    "mean": None,
                    "std": None,
                    "min": None,
                    "p25": None,
                    "median": None,
                    "p75": None,
                    "max": None,
                    "missing": temp[col].isna().sum(),
                    "missing_pct": round(temp[col].isna().mean() * 100, 2),
                }
            )
        else:
            rows.append(
                {
                    "variable": col,
                    "n": int(series.count()),
                    "mean": round(float(series.mean()), 4),
                    "std": round(float(series.std()), 4) if series.count() > 1 else None,
                    "min": round(float(series.min()), 4),
                    "p25": round(float(series.quantile(0.25)), 4),
                    "median": round(float(series.median()), 4),
                    "p75": round(float(series.quantile(0.75)), 4),
                    "max": round(float(series.max()), 4),
                    "missing": int(temp[col].isna().sum()),
                    "missing_pct": round(float(temp[col].isna().mean() * 100), 2),
                }
            )

    return pd.DataFrame(rows)


def make_panel_missing_summary(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    Şirket-yıl paneli için eksik veri özet tablosu.
    """
    if panel_df.empty:
        return pd.DataFrame()

    rows = []

    for col in panel_df.columns:
        rows.append(
            {
                "variable": col,
                "non_missing": int(panel_df[col].notna().sum()),
                "missing": int(panel_df[col].isna().sum()),
                "missing_pct": round(float(panel_df[col].isna().mean() * 100), 2),
            }
        )

    return pd.DataFrame(rows).sort_values("missing_pct", ascending=False)


def make_panel_company_coverage(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    Her şirket için yıl kapsamı ve gözlem sayısını verir.
    """
    if panel_df.empty or "company_name" not in panel_df.columns:
        return pd.DataFrame()

    temp = panel_df.copy()

    if "year" in temp.columns:
        temp["year_num"] = pd.to_numeric(temp["year"], errors="coerce")
    else:
        temp["year_num"] = None

    rows = []

    for company, g in temp.groupby("company_name", dropna=False):
        numeric_years = g["year_num"].dropna()

        rows.append(
            {
                "company_name": company,
                "observation_count": len(g),
                "first_year": int(numeric_years.min()) if not numeric_years.empty else None,
                "last_year": int(numeric_years.max()) if not numeric_years.empty else None,
                "year_count": int(numeric_years.nunique()) if not numeric_years.empty else 0,
            }
        )

    return pd.DataFrame(rows).sort_values(["company_name"])


def make_panel_correlation_matrix(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    Sayısal değişkenler için korelasyon matrisi üretir.
    """
    if panel_df.empty:
        return pd.DataFrame()

    temp = panel_df.copy()
    numeric_cols = [c for c in temp.columns if c not in ["company_name", "year"]]

    for col in numeric_cols:
        temp[col] = pd.to_numeric(temp[col], errors="coerce")

    numeric_cols = [
        c for c in numeric_cols if temp[c].notna().sum() >= 2
    ]

    if len(numeric_cols) < 2:
        return pd.DataFrame()

    corr_df = temp[numeric_cols].corr().round(4)

    return corr_df.reset_index().rename(columns={"index": "variable"})


def suggest_panel_models(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    Veri yapısına göre önerilen panel analiz modellerini listeler.
    """
    if panel_df.empty:
        return pd.DataFrame()

    n_companies = panel_df["company_name"].nunique() if "company_name" in panel_df.columns else 0
    n_years = panel_df["year"].nunique() if "year" in panel_df.columns else 0
    n_obs = len(panel_df)

    suggestions = []

    suggestions.append(
        {
            "model_type": "Pooled OLS",
            "use_case": "Başlangıç modeli / referans model",
            "condition": "Panel yapı zayıf veya gözlem sayısı sınırlıysa kullanılabilir.",
            "recommended": True,
        }
    )

    suggestions.append(
        {
            "model_type": "Fixed Effects",
            "use_case": "Şirkete özgü sabit ve gözlenemeyen etkileri kontrol eder.",
            "condition": "Aynı şirket için birden fazla yıl gözlemi varsa uygundur.",
            "recommended": bool(n_companies >= 2 and n_years >= 2),
        }
    )

    suggestions.append(
        {
            "model_type": "Random Effects",
            "use_case": "Şirket etkilerinin rassal olduğu varsayımı altında kullanılır.",
            "condition": "Hausman testi ile Fixed Effects'e karşı değerlendirilebilir.",
            "recommended": bool(n_companies >= 2 and n_years >= 2),
        }
    )

    suggestions.append(
        {
            "model_type": "Two-way Fixed Effects",
            "use_case": "Hem şirket hem yıl etkilerini kontrol eder.",
            "condition": "Yeterli şirket ve yıl çeşitliliği varsa uygundur.",
            "recommended": bool(n_companies >= 5 and n_years >= 3),
        }
    )

    suggestions.append(
        {
            "model_type": "Dynamic Panel",
            "use_case": "Bağımlı değişkenin gecikmeli değerini modele dahil eder.",
            "condition": "Daha uzun yıl boyutu gerekir; kısa panelde dikkatli kullanılmalıdır.",
            "recommended": bool(n_companies >= 10 and n_years >= 5),
        }
    )

    return pd.DataFrame(suggestions)


def build_stata_panel_do_file(
    panel_df: pd.DataFrame,
    dependent_var: str,
    independent_vars: List[str],
) -> str:
    """
    Stata için akademik panel veri analiz do-file üretir.
    """
    indep = " ".join(independent_vars)

    lines = [
        "* ESG Academic Panel Data Analysis",
        "* Generated by Sustainability Indicator AI Agent",
        "",
        "clear all",
        "set more off",
        "",
        "* 1. Import data",
        'import delimited "standard_esg_panel.csv", clear encoding(UTF-8)',
        "",
        "* 2. Encode company identifier",
        "encode company_name, gen(company_id)",
        "destring year, replace force",
        "",
        "* 3. Declare panel structure",
        "xtset company_id year",
        "",
        "* 4. Descriptive statistics",
        f"summarize {dependent_var} {indep}",
        "",
        "* 5. Correlation matrix",
        f"pwcorr {dependent_var} {indep}, sig star(0.05)",
        "",
        "* 6. Pooled OLS",
        f"reg {dependent_var} {indep}, robust",
        "",
        "* 7. Fixed effects",
        f"xtreg {dependent_var} {indep}, fe robust",
        "estimates store FE",
        "",
        "* 8. Random effects",
        f"xtreg {dependent_var} {indep}, re",
        "estimates store RE",
        "",
        "* 9. Hausman test",
        "hausman FE RE, sigmamore",
        "",
        "* 10. Two-way fixed effects",
        f"xtreg {dependent_var} {indep} i.year, fe robust",
        "",
        "* 11. Cluster-robust standard errors",
        f"xtreg {dependent_var} {indep} i.year, fe vce(cluster company_id)",
        "",
        "* 12. Export note",
        "* You may use esttab/outreg2/asdoc if installed.",
    ]

    return "\n".join(lines)


def build_spss_panel_syntax(
    panel_df: pd.DataFrame,
    dependent_var: str,
    independent_vars: List[str],
) -> str:
    """
    SPSS için temel analiz syntax üretir.
    """
    vars_text = " ".join([dependent_var] + independent_vars)
    indep_text = " ".join(independent_vars)

    syntax = f"""
* ESG Academic Panel Data Analysis.
* Generated by Sustainability Indicator AI Agent.

GET DATA
  /TYPE=XLSX
  /FILE='standard_esg_panel.xlsx'
  /SHEET=name 'standard_model_panel'
  /READNAMES=ON.

EXECUTE.

* Descriptive statistics.
DESCRIPTIVES VARIABLES={vars_text}
  /STATISTICS=MEAN STDDEV MIN MAX.

* Correlation matrix.
CORRELATIONS
  /VARIABLES={vars_text}
  /PRINT=TWOTAIL NOSIG
  /MISSING=PAIRWISE.

* Linear regression reference model.
REGRESSION
  /DEPENDENT {dependent_var}
  /METHOD=ENTER {indep_text}.

* Note:
* For fixed effects in SPSS, add company and year dummy variables
* or use GENLINMIXED / MIXED depending on your license and design.
"""
    return syntax.strip()


def make_academic_panel_excel_file(
    panel_df: pd.DataFrame,
    desc_df: pd.DataFrame,
    missing_df: pd.DataFrame,
    corr_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    model_suggestions_df: pd.DataFrame,
) -> bytes:
    """
    Akademik panel veri analiz paketini Excel'e yazar.
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        panel_df.to_excel(writer, index=False, sheet_name="standard_model_panel")
        desc_df.to_excel(writer, index=False, sheet_name="descriptive_stats")
        missing_df.to_excel(writer, index=False, sheet_name="missing_summary")
        corr_df.to_excel(writer, index=False, sheet_name="correlation_matrix")
        coverage_df.to_excel(writer, index=False, sheet_name="company_coverage")
        model_suggestions_df.to_excel(writer, index=False, sheet_name="model_suggestions")

    return output.getvalue()


def make_academic_panel_zip_file(
    panel_df: pd.DataFrame,
    excel_bytes: bytes,
    stata_code: str,
    spss_code: str,
) -> bytes:
    """
    Akademik panel veri analiz dosyalarını zip olarak üretir.
    """
    output = io.BytesIO()

    csv_buffer = io.StringIO()
    panel_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("standard_esg_panel.csv", csv_buffer.getvalue())
        z.writestr("academic_panel_analysis.xlsx", excel_bytes)
        z.writestr("stata_panel_analysis.do", stata_code)
        z.writestr("spss_panel_analysis.sps", spss_code)

    return output.getvalue()


# =====================================================
# 17. STREAMLIT ARAYÜZ
# =====================================================

st.set_page_config(
    page_title="Sustainability Indicator AI Agent",
    page_icon="🌱",
    layout="wide",
)

require_login()

st.title("🌱 Sustainability Indicator AI Agent")
st.caption("MVP-18: Çok ülkeli World Bank indirme + akademik panel veri analizi + n8n entegrasyonu")

role = st.session_state.get("role", "viewer")

all_tabs = [
    "1. Ülke Göstergeleri",
    "2. PDF Rapor Tarama",
    "3. LLM Gösterge Çıkarma",
    "4. Hesaplama ve Panel Veri",
    "5. Çoklu Şirket Veri Seti",
    "6. Veri Tabanı",
    "7. Toplu PDF İşleme",
    "8. SPSS/Stata Çıktı",
    "9. PostgreSQL",
    "10. URL'den Rapor İşleme",
    "11. BIST Rapor Linkleri",
    "12. ESG Sözlük & Kalite",
    "13. BIST Link Doğrulama",
    "14. n8n Takip Edilen Raporlar",
    "15. Akademik Panel Analizi",
]

# Viewer için sadece görüntüleme sekmeleri
viewer_tabs = [
    "1. Ülke Göstergeleri",
    "5. Çoklu Şirket Veri Seti",
    "6. Veri Tabanı",
    "8. SPSS/Stata Çıktı",
    "11. BIST Rapor Linkleri",
    "12. ESG Sözlük & Kalite",
    "15. Akademik Panel Analizi",
]

# User için admin dışındaki tüm analiz sekmeleri
user_tabs = [
    "1. Ülke Göstergeleri",
    "2. PDF Rapor Tarama",
    "3. LLM Gösterge Çıkarma",
    "4. Hesaplama ve Panel Veri",
    "5. Çoklu Şirket Veri Seti",
    "6. Veri Tabanı",
    "7. Toplu PDF İşleme",
    "8. SPSS/Stata Çıktı",
    "10. URL'den Rapor İşleme",
    "11. BIST Rapor Linkleri",
    "12. ESG Sözlük & Kalite",
    "13. BIST Link Doğrulama",
    "14. n8n Takip Edilen Raporlar",
    "15. Akademik Panel Analizi",
]

# Admin tüm sekmeleri görür; user ve viewer rolleri sınırlı sekme setleriyle çalışır.
visible_tabs = get_visible_tabs_for_role(role, all_tabs, user_tabs, viewer_tabs)

workflow_tab_groups = {
    "Tüm sekmeler": all_tabs,
    "Veri toplama": [all_tabs[0], all_tabs[10], all_tabs[12], all_tabs[13]],
    "PDF / URL işleme": [all_tabs[1], all_tabs[6], all_tabs[9]],
    "ESG çıkarım": [all_tabs[2], all_tabs[3], all_tabs[4]],
    "Kalite kontrol": [all_tabs[11]],
    "Panel veri & analiz": [all_tabs[7], all_tabs[14]],
    "Yönetim": [all_tabs[5], all_tabs[8]],
}

available_focus_options = [
    name for name, tabs in workflow_tab_groups.items()
    if filter_tabs_for_focus(visible_tabs, tabs)
]

with st.sidebar:
    selected_workflow_focus = st.selectbox(
        "Odak görünümü",
        options=available_focus_options,
        index=0,
        help="Sekmeleri seçilen iş akışına göre daraltır.",
    )

focused_tabs = filter_tabs_for_focus(visible_tabs, workflow_tab_groups[selected_workflow_focus])
visible_tabs = focused_tabs if focused_tabs else visible_tabs

render_sidebar_status_panel(role)

main_tabs = st.tabs(visible_tabs)

tab_map = dict(zip(visible_tabs, main_tabs))

main_tab_1 = tab_map.get(all_tabs[0])
main_tab_2 = tab_map.get(all_tabs[1])
main_tab_3 = tab_map.get(all_tabs[2])
main_tab_4 = tab_map.get(all_tabs[3])
main_tab_5 = tab_map.get(all_tabs[4])
main_tab_6 = tab_map.get(all_tabs[5])
main_tab_7 = tab_map.get(all_tabs[6])
main_tab_8 = tab_map.get(all_tabs[7])
main_tab_9 = tab_map.get(all_tabs[8])
main_tab_10 = tab_map.get(all_tabs[9])
main_tab_11 = tab_map.get(all_tabs[10])
main_tab_12 = tab_map.get(all_tabs[11])
main_tab_13 = tab_map.get(all_tabs[12])
main_tab_14 = tab_map.get(all_tabs[13])
main_tab_15 = tab_map.get(all_tabs[14])




# =====================================================
# TAB 1: WORLD BANK VERİ İNDİRME
# =====================================================

if main_tab_1 is not None:
    with main_tab_1:
        st.subheader("World Bank sürdürülebilirlik göstergeleri")

        with st.sidebar:
            st.header("World Bank Ayarları")

            countries_text = st.text_area(
                "Ülke ISO3 kodları",
                value=st.session_state.get("countries_text_override", DEFAULT_COUNTRIES),
                height=120,
                help="Virgül, boşluk veya satır sonu ile ayırabilirsiniz. Örnek: TUR,DEU,FRA veya her satıra bir ülke.",
            )

            col_country_1, col_country_2 = st.columns([1, 1])

            with col_country_1:
                country_chunk_size = st.slider(
                    "Ülke grup büyüklüğü",
                    min_value=5,
                    max_value=30,
                    value=WORLD_BANK_COUNTRY_CHUNK_SIZE,
                    step=5,
                    help="Çok ülke girildiğinde World Bank istekleri bu büyüklükte gruplara bölünür.",
                )

            with col_country_2:
                if st.button("OECD ülke listesini kullan"):
                    st.session_state["countries_text_override"] = OECD_SAMPLE_COUNTRIES
                    st.rerun()

            col1, col2 = st.columns(2)

            with col1:
                start_year = st.number_input(
                    "Başlangıç yılı",
                    min_value=1960,
                    max_value=2030,
                    value=2000,
                    key="wb_start_year",
                )

            with col2:
                end_year = st.number_input(
                    "Bitiş yılı",
                    min_value=1960,
                    max_value=2030,
                    value=2024,
                    key="wb_end_year",
                )

            st.subheader("Göstergeler")

            selected_codes = []

            for code, label in DEFAULT_INDICATORS.items():
                checked = st.checkbox(
                    f"{label} ({code})",
                    value=True,
                    key=f"indicator_{code}",
                )

                if checked:
                    selected_codes.append(code)

            run_button = st.button("Verileri indir", type="primary")

        countries = parse_country_codes(countries_text)
        selected_indicators = {code: DEFAULT_INDICATORS[code] for code in selected_codes}

        st.markdown("### Seçilen kapsam")

        col_a, col_b, col_c = st.columns(3)

        col_a.metric("Ülke sayısı", len(countries))
        col_b.metric("Gösterge sayısı", len(selected_indicators))
        col_c.metric("Yıl aralığı", f"{start_year}-{end_year}")

        if run_button:
            if not countries:
                st.error("En az bir ülke kodu giriniz.")

            elif not selected_indicators:
                st.error("En az bir gösterge seçiniz.")

            elif start_year > end_year:
                st.error("Başlangıç yılı bitiş yılından büyük olamaz.")

            else:
                with st.spinner("World Bank API verileri indiriliyor..."):
                    st.info(
                        f"{len(countries)} ülke kodu algılandı. "
                        f"İndirme {country_chunk_size}'li ülke gruplarıyla yapılacak."
                    )

                    panel_df = download_worldbank_panel(
                        countries=countries,
                        indicators=selected_indicators,
                        start_year=int(start_year),
                        end_year=int(end_year),
                        country_chunk_size=country_chunk_size,
                    )

                if panel_df.empty:
                    st.error(
                        "Veri indirilemedi. Ülke kodlarını, yıl aralığını veya gösterge kodlarını kontrol ediniz."
                    )

                else:
                    st.session_state["worldbank_panel_df"] = panel_df
                    st.success("Veriler başarıyla indirildi.")

                    metadata_df = pd.DataFrame(
                        [
                            {"indicator_code": code, "short_name": name}
                            for code, name in selected_indicators.items()
                        ]
                    )

                    st.markdown("### Panel veri önizleme")
                    st.dataframe(panel_df, use_container_width=True)

                    st.markdown("### Eksik veri özeti")

                    missing_df = (
                        panel_df.isna()
                        .sum()
                        .reset_index()
                        .rename(columns={"index": "variable", 0: "missing_count"})
                    )

                    missing_df["missing_pct"] = (
                        missing_df["missing_count"] / len(panel_df) * 100
                    ).round(2)

                    st.dataframe(missing_df, use_container_width=True)

                    excel_bytes = make_worldbank_excel_file(panel_df, metadata_df)

                    st.download_button(
                        label="Excel dosyasını indir",
                        data=excel_bytes,
                        file_name="sustainability_panel_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

        else:
            st.info("Sol menüden kapsamı seçip 'Verileri indir' düğmesine basınız.")

if st.session_state.get("role") == "admin":
    with st.expander("👤 Kullanıcı Yönetimi"):
        admin_user_management()

# =====================================================
# TAB 2: PDF RAPOR TARAMA
# =====================================================

if main_tab_2 is not None:
    with main_tab_2:
        st.subheader("PDF faaliyet / sürdürülebilirlik raporu tarama")

        st.markdown(
            """
Bu bölüm PDF rapor içinden sürdürülebilirlik anahtar kelimelerini tarar.  
Bu aşama LLM kullanmaz; sayfa ve kanıt metni çıkarır.
        """
    )

    uploaded_pdf = st.file_uploader(
        "PDF faaliyet veya sürdürülebilirlik raporu yükleyiniz",
        type=["pdf"],
        key="pdf_upload",
    )

    col_left, col_right = st.columns([2, 1])

    with col_left:
        keywords_text = st.text_area(
            "Aranacak anahtar kelimeler",
            value=DEFAULT_KEYWORDS,
            height=260,
            help="Her satıra bir anahtar kelime yazınız.",
        )

    with col_right:
        st.markdown("#### Tarama ayarları")
        context_sentences = st.slider(
            "Kanıt metninde kaç komşu cümle gösterilsin?",
            min_value=0,
            max_value=3,
            value=1,
        )

        max_preview_rows = st.number_input(
            "Önizleme satır sayısı",
            min_value=5,
            max_value=500,
            value=80,
        )

    scan_button = st.button("PDF raporu tara", type="primary")

    if scan_button:
        if uploaded_pdf is None:
            st.error("Lütfen önce bir PDF dosyası yükleyiniz.")

        else:
            keywords = [k.strip() for k in keywords_text.splitlines() if k.strip()]

            if not keywords:
                st.error("En az bir anahtar kelime giriniz.")

            else:
                with st.spinner("PDF sayfa sayfa okunuyor ve anahtar kelimeler aranıyor..."):
                    pages = extract_pdf_text_by_page(uploaded_pdf)
                    result_df = search_keywords_in_pdf_pages(
                        pages=pages,
                        keywords=keywords,
                        context_sentences=context_sentences,
                    )

                st.session_state["pdf_pages"] = pages
                st.session_state["pdf_result_df"] = result_df

                st.success(f"PDF okundu. Toplam sayfa sayısı: {len(pages)}")

                if result_df.empty:
                    st.warning("Belirlenen anahtar kelimelerle eşleşme bulunamadı.")

                else:
                    summary_df = (
                        result_df.groupby("keyword")
                        .agg(
                            match_count=("keyword", "size"),
                            first_page=("page", "min"),
                            last_page=("page", "max"),
                        )
                        .reset_index()
                        .sort_values(["match_count", "keyword"], ascending=[False, True])
                    )

                    st.session_state["keyword_summary_df"] = summary_df

                    st.markdown("### Bulunan sürdürülebilirlik kanıtları")
                    st.dataframe(
                        result_df.head(int(max_preview_rows)),
                        use_container_width=True,
                    )

                    st.markdown("### Anahtar kelime özeti")
                    st.dataframe(summary_df, use_container_width=True)

                    excel_bytes = make_pdf_scan_excel_file(result_df, summary_df)

                    st.download_button(
                        label="PDF tarama sonuçlarını Excel indir",
                        data=excel_bytes,
                        file_name="pdf_sustainability_keyword_scan.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

    elif "pdf_result_df" in st.session_state and not st.session_state["pdf_result_df"].empty:
        st.info("Önceki PDF tarama sonucu aşağıda gösteriliyor.")
        st.dataframe(st.session_state["pdf_result_df"].head(80), use_container_width=True)
    else:
        st.info("PDF yükleyip 'PDF raporu tara' düğmesine basınız.")


# =====================================================
# TAB 3: LLM GÖSTERGE ÇIKARMA
# =====================================================

if main_tab_3 is not None:
    with main_tab_3:
        st.subheader("LLM ile sürdürülebilirlik göstergesi çıkarma")

        st.markdown(
            """
Bu bölüm, 2. sekmede bulunan kanıt metinlerini OpenAI API'ye gönderir ve
sayısal sürdürülebilirlik göstergelerini tabloya dönüştürür.
        """
    )

    if "pdf_result_df" not in st.session_state or st.session_state["pdf_result_df"].empty:
        st.warning("Önce 2. sekmede PDF raporu tarayınız.")
    else:
        evidence_df_all = st.session_state["pdf_result_df"].copy()
        keyword_summary_df = st.session_state.get("keyword_summary_df", pd.DataFrame())

        col_info_1, col_info_2, col_info_3 = st.columns(3)
        col_info_1.metric("Kanıt satırı", len(evidence_df_all))
        col_info_2.metric("Sayfa sayısı", evidence_df_all["page"].nunique())
        col_info_3.metric("Anahtar kelime", evidence_df_all["keyword"].nunique())

        st.markdown("### LLM ayarları")

        col1, col2 = st.columns(2)

        with col1:
            company_name = st.text_input("Şirket adı", value="Firma adı")
            report_year = st.text_input("Rapor yılı", value="2024")

        with col2:
            model_name = st.text_input("Model adı", value="gpt-4.1-mini")
            max_evidence_rows_for_llm = st.number_input(
                "LLM'e gönderilecek en fazla kanıt satırı",
                min_value=5,
                max_value=300,
                value=60,
            )

        api_key_from_input = st.text_input(
            "OpenAI API Key (isteğe bağlı)",
            value="",
            type="password",
            help="Boş bırakırsanız OPENAI_API_KEY ortam değişkeni kullanılır.",
        )

        st.markdown("### LLM'e gönderilecek seçilmiş metin")

        # En kısa/tekrarsız örneklerden seçelim; çok uzun raporda maliyeti sınırlar.
        evidence_df_for_llm = evidence_df_all.copy()
        evidence_df_for_llm["evidence_length"] = evidence_df_for_llm["evidence_text"].astype(str).str.len()
        evidence_df_for_llm = (
            evidence_df_for_llm.sort_values(["page", "keyword", "evidence_length"])
            .drop_duplicates(subset=["page", "keyword"])
            .head(int(max_evidence_rows_for_llm))
            .reset_index(drop=True)
        )

        st.dataframe(
            evidence_df_for_llm[["page", "keyword", "evidence_text"]].head(30),
            use_container_width=True,
        )

        run_llm_button = st.button("LLM ile göstergeleri çıkar", type="primary")

        if run_llm_button:
            if not api_key_from_input and not os.getenv("OPENAI_API_KEY"):
                st.error(
                    "OpenAI API anahtarı bulunamadı. Ya kutuya API key girin ya da OPENAI_API_KEY ortam değişkenini tanımlayın."
                )
            else:
                with st.spinner("LLM göstergeleri çıkarıyor..."):
                    try:
                        extracted_df = llm_extract_indicators(
                            evidence_df=evidence_df_for_llm,
                            company_name=company_name,
                            report_year=report_year,
                            model_name=model_name,
                            api_key=api_key_from_input if api_key_from_input else None,
                        )
                    except Exception as exc:
                        st.error(f"LLM çıkarımı sırasında hata oluştu: {exc}")
                        extracted_df = pd.DataFrame()

                if extracted_df.empty:
                    st.warning("LLM geçerli sayısal gösterge çıkaramadı.")
                else:
                    st.session_state["llm_extracted_df"] = extracted_df
                    add_to_master_dataset(extracted_df)

                    persistence_result = save_indicators_to_default_stores(extracted_df)

                    st.success(
                        f"{len(extracted_df)} gösterge çıkarıldı ve çoklu şirket veri setine eklendi."
                    )
                    show_persistence_result(persistence_result)

                    st.markdown("### Çıkarılan göstergeler")
                    st.dataframe(extracted_df, use_container_width=True)

                    excel_bytes = make_llm_excel_file(
                        extracted_df=extracted_df,
                        evidence_df=evidence_df_all,
                        keyword_summary_df=keyword_summary_df,
                    )

                    st.download_button(
                        label="LLM gösterge sonuçlarını Excel indir",
                        data=excel_bytes,
                        file_name="llm_sustainability_indicators.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

        elif "llm_extracted_df" in st.session_state and not st.session_state["llm_extracted_df"].empty:
            st.info("Önceki LLM çıkarım sonucu aşağıda gösteriliyor.")
            st.dataframe(st.session_state["llm_extracted_df"], use_container_width=True)



# =====================================================
# TAB 4: HESAPLAMA VE PANEL VERİ
# =====================================================

if main_tab_4 is not None:
    with main_tab_4:
        st.subheader("Hesaplama ve şirket-yıl panel veri")

        st.markdown(
            """
Bu bölüm LLM ile çıkarılan göstergelerden modellemeye hazır şirket-yıl veri seti üretir.
Ayrıca oran, toplam ve yoğunluk göstergeleri hesaplamak için esnek bir hesaplama alanı sağlar.
        """
    )

    if "llm_extracted_df" not in st.session_state or st.session_state["llm_extracted_df"].empty:
        st.warning("Önce 3. sekmede LLM ile gösterge çıkarımı yapınız.")
    else:
        extracted_df = st.session_state["llm_extracted_df"].copy()

        st.markdown("### 1. LLM göstergeleri")
        st.dataframe(extracted_df, use_container_width=True)

        derived_df = compute_automatic_derived_indicators(extracted_df)
        panel_df = build_company_year_panel(extracted_df)

        st.markdown("### 2. Otomatik türetilmiş göstergeler")

        if derived_df.empty:
            st.info(
                "Otomatik hesaplanabilecek standart gösterge bulunamadı. "
                "Bu normaldir; örneğin Kapsam 1-2-3 veya toplam enerji gibi bilgiler raporda açıkça yakalanmamış olabilir."
            )
        else:
            st.dataframe(derived_df, use_container_width=True)

        st.markdown("### 3. Şirket-yıl panel veri")

        if panel_df.empty:
            st.warning("Panel veri oluşturulamadı.")
        else:
            st.dataframe(panel_df, use_container_width=True)

        st.markdown("### 4. Özel oran / yoğunluk hesabı")

        numeric_rows = extracted_df[extracted_df["numeric_value"].notna()].copy()

        if numeric_rows.empty:
            st.warning("Sayısal değer bulunamadığı için özel hesap yapılamıyor.")
        else:
            numeric_rows["label"] = (
                numeric_rows["indicator_name"].astype(str)
                + " | "
                + numeric_rows["value"].astype(str)
                + " "
                + numeric_rows["unit"].astype(str)
                + " | sayfa "
                + numeric_rows["page"].astype(str)
            )

            labels = numeric_rows["label"].tolist()

            col_calc_1, col_calc_2 = st.columns(2)

            with col_calc_1:
                numerator_label = st.selectbox("Pay / numerator", labels, key="custom_num")
                denominator_label = st.selectbox("Payda / denominator", labels, key="custom_den")

            with col_calc_2:
                custom_name = st.text_input(
                    "Yeni gösterge adı",
                    value="Özel oran göstergesi",
                )
                multiplier = st.number_input(
                    "Çarpan",
                    value=100.0,
                    help="Oran için 100, yoğunluk için 1 kullanılabilir.",
                )
                custom_unit = st.text_input("Yeni birim", value="yüzde")

            if "custom_calculations_df" not in st.session_state:
                st.session_state["custom_calculations_df"] = pd.DataFrame(
                    columns=[
                        "company_name",
                        "year",
                        "custom_indicator",
                        "value",
                        "unit",
                        "formula",
                        "numerator",
                        "denominator",
                    ]
                )

            if st.button("Özel göstergeyi hesapla", type="primary"):
                num_row = numeric_rows[numeric_rows["label"] == numerator_label].iloc[0]
                den_row = numeric_rows[numeric_rows["label"] == denominator_label].iloc[0]

                numerator_value = float(num_row["numeric_value"])
                denominator_value = float(den_row["numeric_value"])

                if denominator_value == 0:
                    st.error("Payda sıfır olduğu için hesaplama yapılamaz.")
                else:
                    calculated_value = numerator_value / denominator_value * float(multiplier)

                    new_row = pd.DataFrame(
                        [
                            {
                                "company_name": num_row["company_name"],
                                "year": num_row["year"],
                                "custom_indicator": custom_name,
                                "value": calculated_value,
                                "unit": custom_unit,
                                "formula": f"({num_row['indicator_name']}) / ({den_row['indicator_name']}) × {multiplier}",
                                "numerator": numerator_value,
                                "denominator": denominator_value,
                            }
                        ]
                    )

                    st.session_state["custom_calculations_df"] = pd.concat(
                        [st.session_state["custom_calculations_df"], new_row],
                        ignore_index=True,
                    )

                    st.success(f"{custom_name} hesaplandı: {calculated_value:.4f} {custom_unit}")

            custom_df = st.session_state.get("custom_calculations_df", pd.DataFrame())

            if not custom_df.empty:
                st.markdown("### 5. Özel hesaplanan göstergeler")
                st.dataframe(custom_df, use_container_width=True)

        st.markdown("### Excel çıktı")

        custom_df = st.session_state.get("custom_calculations_df", pd.DataFrame())

        excel_bytes = make_panel_excel_file(
            extracted_df=extracted_df,
            derived_df=derived_df,
            panel_df=panel_df,
            custom_df=custom_df,
        )

        st.download_button(
            label="Hesaplama ve panel veri Excel indir",
            data=excel_bytes,
            file_name="sustainability_model_ready_panel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )



# =====================================================
# TAB 5: ÇOKLU ŞİRKET VERİ SETİ
# =====================================================

if main_tab_5 is not None:
    with main_tab_5:
        st.subheader("Çoklu şirket ESG veri seti")

        st.markdown(
            """
Bu bölüm, farklı şirket raporlarından çıkarılan göstergeleri tek ana veri setinde birleştirir.
Her şirket için 2. ve 3. sekmeleri çalıştırdıktan sonra sonuçlar burada birikir.
        """
    )

    if "master_indicators_df" not in st.session_state or st.session_state["master_indicators_df"].empty:
        st.warning(
            "Henüz ana veri setinde kayıt yok. Önce 3. sekmede en az bir şirket için LLM gösterge çıkarımı yapınız."
        )
    else:
        master_df = st.session_state["master_indicators_df"].copy()

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Toplam kayıt", len(master_df))
        col_m2.metric("Şirket sayısı", master_df["company_name"].nunique())
        col_m3.metric("Yıl sayısı", master_df["year"].nunique())
        col_m4.metric("Gösterge sayısı", master_df["indicator_name"].nunique())

        st.markdown("### 1. Ana ESG gösterge veri seti")
        st.dataframe(master_df, use_container_width=True)

        st.markdown("### 2. Gösterge türü özeti")

        if "metric_type" in master_df.columns:
            metric_summary = (
                master_df.groupby(["company_name", "year", "metric_type"])
                .size()
                .reset_index(name="count")
                .sort_values(["company_name", "year", "metric_type"])
            )
            st.dataframe(metric_summary, use_container_width=True)
        else:
            st.info("metric_type alanı bulunamadı.")

        st.markdown("### 3. Çoklu şirket panel veri")

        multi_panel_df = build_company_year_panel(master_df)

        if multi_panel_df.empty:
            st.warning("Panel veri üretilemedi.")
        else:
            st.dataframe(multi_panel_df, use_container_width=True)

        st.markdown("### 4. Çoklu şirket türetilmiş göstergeler")

        multi_derived_df = compute_automatic_derived_indicators(master_df)

        if multi_derived_df.empty:
            st.info("Otomatik türetilmiş gösterge bulunamadı.")
        else:
            st.dataframe(multi_derived_df, use_container_width=True)

        st.markdown("### 5. Veri seti yönetimi")

        col_download, col_clear = st.columns([2, 1])

        with col_download:
            excel_bytes = make_master_excel_file(master_df)

            st.download_button(
                label="Çoklu şirket ESG veri setini Excel indir",
                data=excel_bytes,
                file_name="multi_company_esg_dataset.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col_clear:
            if can_edit():
                if st.button("Ana veri setini temizle"):
                    st.session_state["master_indicators_df"] = pd.DataFrame()
                    st.success("Ana veri seti temizlendi. Sayfayı yenileyebilirsiniz.")
            else:
                st.info("Viewer rolü veri setini temizleyemez.")




# =====================================================
# TAB 6: VERİ TABANI
# =====================================================

if main_tab_6 is not None:
    with main_tab_6:
        st.subheader("SQLite kalıcı veri tabanı")

        st.markdown(
            f""" 
Bu bölüm çıkarılan göstergeleri kalıcı olarak saklar.  
Veri tabanı dosyası proje klasörünüzde şu adla oluşur:

`{DB_PATH}`
"""
    )

    init_database()

    db_df = load_indicators_from_database()

    col_db1, col_db2, col_db3, col_db4 = st.columns(4)

    if db_df.empty:
        col_db1.metric("Toplam kayıt", 0)
        col_db2.metric("Şirket sayısı", 0)
        col_db3.metric("Yıl sayısı", 0)
        col_db4.metric("Gösterge sayısı", 0)
        st.warning("Veri tabanında henüz kayıt yok.")
    else:
        col_db1.metric("Toplam kayıt", len(db_df))
        col_db2.metric("Şirket sayısı", db_df["company_name"].nunique())
        col_db3.metric("Yıl sayısı", db_df["year"].nunique())
        col_db4.metric("Gösterge sayısı", db_df["indicator_name"].nunique())

        st.markdown("### 1. Veri tabanı kayıtları")
        st.dataframe(db_df, use_container_width=True)

        st.markdown("### 2. Veri tabanı panel veri")

        db_panel_df = build_company_year_panel(db_df)

        if db_panel_df.empty:
            st.info("Panel veri üretilemedi.")
        else:
            st.dataframe(db_panel_df, use_container_width=True)

        st.markdown("### 3. Veri tabanı türetilmiş göstergeler")

        db_derived_df = compute_automatic_derived_indicators(db_df)

        if db_derived_df.empty:
            st.info("Türetilmiş gösterge bulunamadı.")
        else:
            st.dataframe(db_derived_df, use_container_width=True)

        st.markdown("### 4. Veri tabanı Excel çıktısı")

        db_excel_bytes = make_database_excel_file(db_df)

        st.download_button(
            label="SQLite veri tabanı Excel indir",
            data=db_excel_bytes,
            file_name="sqlite_esg_database_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.markdown("### 5. Veri tabanı yönetimi")

        if can_admin():
            company_options = sorted(db_df["company_name"].dropna().unique().tolist())

            col_del1, col_del2 = st.columns(2)

            with col_del1:
                selected_company_to_delete = st.selectbox(
                    "Silinecek şirket",
                    company_options,
                    key="delete_company_select",
                )

                if st.button("Seçili şirket kayıtlarını sil"):
                    delete_database_records(company_name=selected_company_to_delete)
                    st.success(f"{selected_company_to_delete} kayıtları silindi. Sayfayı yenileyiniz.")

            with col_del2:
                st.warning("Dikkat: Aşağıdaki işlem tüm veri tabanını temizler.")

                confirm_delete_all = st.checkbox("Tüm kayıtları silmeyi onaylıyorum")

                if st.button("Tüm veri tabanını temizle"):
                    if confirm_delete_all:
                        delete_database_records(company_name=None)
                        st.success("Tüm veri tabanı kayıtları silindi. Sayfayı yenileyiniz.")
                    else:
                        st.error("Lütfen önce onay kutusunu işaretleyiniz.")
        else:
            st.info("Veri tabanı silme işlemleri yalnızca admin rolüne açıktır.")




# =====================================================
# TAB 7: TOPLU PDF İŞLEME
# =====================================================

if main_tab_7 is not None:
    with main_tab_7:
        st.subheader("Toplu PDF işleme")

        st.markdown(
            """
Bu bölüm birden fazla faaliyet/sürdürülebilirlik raporunu sırayla işler.

İş akışı:

1. Birden fazla PDF yüklenir.  
2. Dosya adından şirket adı ve yıl tahmin edilir.  
3. PDF anahtar kelimelerle taranır.  
4. Kanıt metinleri LLM'e gönderilir.  
5. Çıkarılan göstergeler SQLite veri tabanına kaydedilir.  
        """
    )

    bulk_files = st.file_uploader(
        "Birden fazla PDF raporu yükleyiniz",
        type=["pdf"],
        accept_multiple_files=True,
        key="bulk_pdf_upload",
    )

    col_bulk_left, col_bulk_right = st.columns([2, 1])

    with col_bulk_left:
        bulk_keywords_text = st.text_area(
            "Toplu işlem anahtar kelimeleri",
            value=DEFAULT_KEYWORDS,
            height=260,
            key="bulk_keywords_text",
        )

    with col_bulk_right:
        st.markdown("#### Toplu işlem ayarları")

        bulk_context_sentences = st.slider(
            "Kanıt metninde komşu cümle sayısı",
            min_value=0,
            max_value=3,
            value=1,
            key="bulk_context_sentences",
        )

        bulk_max_evidence_rows = st.number_input(
            "Her PDF için LLM'e gönderilecek en fazla kanıt satırı",
            min_value=5,
            max_value=200,
            value=50,
            key="bulk_max_evidence_rows",
        )

        bulk_model_name = st.text_input(
            "Model adı",
            value="gpt-4.1-mini",
            key="bulk_model_name",
        )

        bulk_api_key = st.text_input(
            "OpenAI API Key",
            value="",
            type="password",
            key="bulk_api_key",
            help="Boş bırakırsanız OPENAI_API_KEY ortam değişkeni kullanılır.",
        )

    if bulk_files:
        st.markdown("### Dosya adı tahminleri")

        file_meta_rows = []

        for f in bulk_files:
            guessed_company, guessed_year = parse_company_year_from_filename(f.name)

            file_meta_rows.append(
                {
                    "file_name": f.name,
                    "guessed_company": guessed_company,
                    "guessed_year": guessed_year,
                }
            )

        file_meta_df = pd.DataFrame(file_meta_rows)
        st.dataframe(file_meta_df, use_container_width=True)

        st.info(
            "Dosya adı tahmini doğru değilse dosyaları şu formatta adlandırmanız işinizi kolaylaştırır: "
            "Akbank_2024.pdf, THY_2024.pdf, Arcelik_2024.pdf"
        )

    run_bulk_button = st.button("Toplu PDF işlemeyi başlat", type="primary")

    if run_bulk_button:
        if not bulk_files:
            st.error("Lütfen en az bir PDF dosyası yükleyiniz.")
        elif not bulk_api_key and not os.getenv("OPENAI_API_KEY"):
            st.error(
                "OpenAI API anahtarı bulunamadı. Ya kutuya API key girin ya da OPENAI_API_KEY ortam değişkenini tanımlayın."
            )
        else:
            bulk_keywords = [k.strip() for k in bulk_keywords_text.splitlines() if k.strip()]

            if not bulk_keywords:
                st.error("En az bir anahtar kelime giriniz.")
            else:
                summary_rows = []

                progress = st.progress(0)
                status_box = st.empty()

                for i, uploaded_pdf in enumerate(bulk_files, start=1):
                    guessed_company, guessed_year = parse_company_year_from_filename(uploaded_pdf.name)

                    if not guessed_year:
                        guessed_year = "2024"

                    status_box.info(
                        f"İşleniyor ({i}/{len(bulk_files)}): {uploaded_pdf.name} "
                        f"→ {guessed_company}, {guessed_year}"
                    )

                    try:
                        result = bulk_process_single_pdf(
                            uploaded_pdf=uploaded_pdf,
                            company_name=guessed_company,
                            report_year=guessed_year,
                            keywords=bulk_keywords,
                            context_sentences=int(bulk_context_sentences),
                            max_evidence_rows_for_llm=int(bulk_max_evidence_rows),
                            model_name=bulk_model_name,
                            api_key=bulk_api_key if bulk_api_key else None,
                        )
                    except Exception as exc:
                        result = {
                            "company_name": guessed_company,
                            "year": guessed_year,
                            "file_name": uploaded_pdf.name,
                            "page_count": None,
                            "evidence_count": 0,
                            "extracted_count": 0,
                            "saved_count": 0,
                            "status": "Hata",
                            "error": str(exc),
                        }

                    summary_rows.append(result)
                    progress.progress(i / len(bulk_files))

                status_box.success("Toplu PDF işleme tamamlandı.")

                summary_df = pd.DataFrame(summary_rows)
                st.session_state["bulk_summary_df"] = summary_df

                st.markdown("### Toplu işlem özeti")
                st.dataframe(summary_df, use_container_width=True)

                db_df = load_indicators_from_database()

                st.markdown("### Güncel veri tabanı özeti")

                if db_df.empty:
                    st.warning("Veri tabanında kayıt yok.")
                else:
                    col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                    col_b1.metric("Toplam kayıt", len(db_df))
                    col_b2.metric("Şirket sayısı", db_df["company_name"].nunique())
                    col_b3.metric("Yıl sayısı", db_df["year"].nunique())
                    col_b4.metric("Gösterge sayısı", db_df["indicator_name"].nunique())

                    excel_bytes = make_bulk_summary_excel_file(summary_df, db_df)

                    st.download_button(
                        label="Toplu işlem + veri tabanı Excel indir",
                        data=excel_bytes,
                        file_name="bulk_esg_processing_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

    elif "bulk_summary_df" in st.session_state:
        st.markdown("### Önceki toplu işlem özeti")
        st.dataframe(st.session_state["bulk_summary_df"], use_container_width=True)




# =====================================================
# TAB 8: SPSS / STATA ÇIKTI
# =====================================================

if main_tab_8 is not None:
    with main_tab_8:
        st.subheader("SPSS / Stata modelleme çıktıları")

        st.markdown(
            """
Bu bölüm SQLite veri tabanındaki göstergelerden modellemeye hazır panel veri üretir.

Üretilen ana dosyalar:

- `model_ready_panel.csv`
- `model_ready_esg_dataset.xlsx`
- `stata_esg_analysis.do`
- `spss_esg_import.sps`
        """
    )

    db_df = load_indicators_from_database()

    if db_df.empty:
        st.warning("Veri tabanında kayıt yok. Önce 3. veya 7. sekmede gösterge çıkarımı yapınız.")
    else:
        model_df = build_model_ready_dataset(db_df)
        dictionary_df = build_variable_dictionary(db_df)

        col_e1, col_e2, col_e3, col_e4 = st.columns(4)

        col_e1.metric("Uzun form kayıt", len(db_df))
        col_e2.metric("Model satırı", len(model_df))
        col_e3.metric("Model değişkeni", max(len(model_df.columns) - 2, 0) if not model_df.empty else 0)
        col_e4.metric("Şirket sayısı", db_df["company_name"].nunique())

        st.markdown("### 1. Modellemeye hazır panel veri")

        if model_df.empty:
            st.warning(
                "Modellemeye hazır veri üretilemedi. actual_value veya ratio türünde numeric_value bulunmamış olabilir."
            )
        else:
            st.dataframe(model_df, use_container_width=True)

        st.markdown("### 2. Değişken sözlüğü")

        if dictionary_df.empty:
            st.info("Değişken sözlüğü üretilemedi.")
        else:
            st.dataframe(dictionary_df, use_container_width=True)

        st.markdown("### 3. İndirilebilir dosyalar")

        if not model_df.empty:
            excel_bytes = make_modeling_excel_file(db_df)
            csv_bytes = make_csv_bytes(model_df)
            dict_csv_bytes = make_csv_bytes(dictionary_df)
            stata_do = generate_stata_do_file(model_df, dictionary_df)
            spss_sps = generate_spss_syntax_file(model_df, dictionary_df)

            col_d1, col_d2 = st.columns(2)

            with col_d1:
                st.download_button(
                    label="Excel modelleme dosyası indir",
                    data=excel_bytes,
                    file_name="model_ready_esg_dataset.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                st.download_button(
                    label="CSV panel veri indir",
                    data=csv_bytes,
                    file_name="model_ready_panel.csv",
                    mime="text/csv",
                )

                st.download_button(
                    label="Değişken sözlüğü CSV indir",
                    data=dict_csv_bytes,
                    file_name="variable_dictionary.csv",
                    mime="text/csv",
                )

            with col_d2:
                st.download_button(
                    label="Stata do-file indir",
                    data=stata_do.encode("utf-8-sig"),
                    file_name="stata_esg_analysis.do",
                    mime="text/plain",
                )

                st.download_button(
                    label="SPSS syntax indir",
                    data=spss_sps.encode("utf-8-sig"),
                    file_name="spss_esg_import.sps",
                    mime="text/plain",
                )

        st.markdown("### 4. Stata başlangıç kodu")

        if not model_df.empty:
            st.code(generate_stata_do_file(model_df, dictionary_df), language="stata")

        st.markdown("### 5. SPSS başlangıç syntax")

        if not model_df.empty:
            st.code(generate_spss_syntax_file(model_df, dictionary_df), language="spss")




# =====================================================
# TAB 9: POSTGRESQL
# =====================================================

if main_tab_9 is not None:
    with main_tab_9:
        st.subheader("PostgreSQL veri tabanı")

        db_status = load_default_database_status()
        if db_status["postgres_available"]:
            st.success(f"Otomatik PostgreSQL kayıt aktif: {db_status['postgres_url_masked']}")
        else:
            st.warning("Otomatik PostgreSQL kayıt pasif: DATABASE_URL bulunamadı.")

        st.markdown(
            """
Bu bölüm PostgreSQL bağlantısı ve veri yönetimi içindir.

Yeni varsayılan akışta LLM gösterge çıkarımı başarılı olduğunda:
SQLite'a kayıt yapılır; DATABASE_URL varsa PostgreSQL'e de otomatik kayıt yapılır.

İki kullanım biçimi vardır:

1. **Lokal PostgreSQL**: Kendi bilgisayarınızda çalışan PostgreSQL.
2. **Bulut PostgreSQL**: Supabase, Neon, Railway, Render, Google Cloud SQL vb.

Bağlantı adresi örneği:

`postgresql://postgres:PAROLA@localhost:5432/sustainability_esg`
        """
    )

    default_pg_url = get_secure_database_url()

    use_manual_database_url = st.checkbox(
        "DATABASE_URL değerini elle girmek istiyorum",
        value=False,
        help="Yayın ortamında kapalı bırakmak daha güvenlidir. Secrets veya ortam değişkeni kullanılır.",
    )

    if use_manual_database_url:
        database_url = st.text_input(
            "PostgreSQL DATABASE_URL",
            value="",
            type="password",
            help="Elle girmek yerine Streamlit Secrets kullanmanız önerilir.",
        )
        effective_pg_url = database_url if database_url else default_pg_url
    else:
        effective_pg_url = default_pg_url
        masked_url = mask_database_url(effective_pg_url)
        if masked_url:
            st.success(f"DATABASE_URL secrets/ortam değişkeninden okundu: {masked_url}")
        else:
            st.warning("DATABASE_URL bulunamadı. Streamlit Secrets veya ortam değişkeni tanımlayınız.")

    st.markdown("### 1. PostgreSQL bağlantı ve tablo oluşturma")

    col_pg_a, col_pg_b, col_pg_c = st.columns(3)

    with col_pg_a:
        test_pg = st.button("Bağlantıyı test et / tablo oluştur")

    with col_pg_b:
        migrate_pg = st.button("SQLite → PostgreSQL taşı")

    with col_pg_c:
        refresh_pg = st.button("PostgreSQL kayıtlarını yenile")

    if test_pg:
        if not effective_pg_url:
            st.error("PostgreSQL bağlantı adresi giriniz veya DATABASE_URL ortam değişkenini tanımlayınız.")
        else:
            try:
                init_postgres_database(effective_pg_url)
                st.success("PostgreSQL bağlantısı başarılı. Tablo hazır.")
            except Exception as exc:
                st.error(f"PostgreSQL bağlantı hatası: {exc}")

    if migrate_pg:
        if not effective_pg_url:
            st.error("PostgreSQL bağlantı adresi giriniz veya DATABASE_URL ortam değişkenini tanımlayınız.")
        else:
            try:
                moved_count = migrate_sqlite_to_postgres(effective_pg_url)
                st.success(f"SQLite kayıtları PostgreSQL'e taşındı. Yeni kayıt sayısı: {moved_count}")
            except Exception as exc:
                st.error(f"Taşıma sırasında hata oluştu: {exc}")

    if refresh_pg:
        st.session_state.pop("postgres_df", None)

    st.markdown("### 2. PostgreSQL kayıtları")

    if effective_pg_url:
        try:
            pg_df = load_indicators_from_postgres(effective_pg_url)
            st.session_state["postgres_df"] = pg_df
        except Exception as exc:
            st.error(f"PostgreSQL kayıtları okunamadı: {exc}")
            pg_df = pd.DataFrame()
    else:
        pg_df = pd.DataFrame()
        st.info("PostgreSQL bağlantı adresi girildiğinde kayıtlar burada gösterilir.")

    if not pg_df.empty:
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        col_p1.metric("Toplam kayıt", len(pg_df))
        col_p2.metric("Şirket sayısı", pg_df["company_name"].nunique())
        col_p3.metric("Yıl sayısı", pg_df["year"].nunique())
        col_p4.metric("Gösterge sayısı", pg_df["indicator_name"].nunique())

        st.dataframe(pg_df, use_container_width=True)

        st.markdown("### 3. PostgreSQL panel veri")

        pg_model_df = build_model_ready_dataset(pg_df)

        if pg_model_df.empty:
            st.info("Modellemeye hazır PostgreSQL panel veri üretilemedi.")
        else:
            st.dataframe(pg_model_df, use_container_width=True)

        st.markdown("### 4. PostgreSQL Excel çıktı")

        pg_excel_bytes = make_postgres_excel_file(pg_df)

        st.download_button(
            label="PostgreSQL ESG veri setini Excel indir",
            data=pg_excel_bytes,
            file_name="postgres_esg_dataset_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.markdown("### 5. PostgreSQL veri yönetimi")

        pg_company_options = sorted(pg_df["company_name"].dropna().unique().tolist())

        col_pg_del_1, col_pg_del_2 = st.columns(2)

        with col_pg_del_1:
            selected_pg_company = st.selectbox(
                "PostgreSQL'den silinecek şirket",
                pg_company_options,
                key="pg_delete_company_select",
            )

            if st.button("PostgreSQL seçili şirket kayıtlarını sil"):
                try:
                    delete_postgres_records(effective_pg_url, company_name=selected_pg_company)
                    st.success(f"{selected_pg_company} PostgreSQL kayıtları silindi. Yenileyiniz.")
                except Exception as exc:
                    st.error(f"Silme hatası: {exc}")

        with col_pg_del_2:
            st.warning("Dikkat: Aşağıdaki işlem PostgreSQL'deki tüm ESG kayıtlarını siler.")
            confirm_pg_delete_all = st.checkbox("PostgreSQL tüm kayıtları silmeyi onaylıyorum")

            if st.button("PostgreSQL tüm kayıtları temizle"):
                if confirm_pg_delete_all:
                    try:
                        delete_postgres_records(effective_pg_url, company_name=None)
                        st.success("PostgreSQL tüm kayıtları silindi. Yenileyiniz.")
                    except Exception as exc:
                        st.error(f"Silme hatası: {exc}")
                else:
                    st.error("Lütfen önce onay kutusunu işaretleyiniz.")

    st.markdown("### 6. Lokal PostgreSQL hızlı kurulum komutları")

    st.code(
        """
# Paket
pip install psycopg2-binary

# PostgreSQL'de örnek veritabanı oluşturma
# psql içinde:
CREATE DATABASE sustainability_esg;

# PowerShell ortam değişkeni olarak tanımlama:
$env:DATABASE_URL="postgresql://postgres:PAROLA@localhost:5432/sustainability_esg"

# Uygulamayı çalıştırma:
streamlit run streamlit_app.py
        """,
        language="powershell",
    )




# =====================================================
# TAB 10: URL'DEN RAPOR İŞLEME
# =====================================================

if main_tab_10 is not None:
    with main_tab_10:
        st.subheader("URL'den faaliyet / sürdürülebilirlik raporu işleme")

        st.markdown(
            """
Bu bölüm PDF raporların web adreslerini alır, PDF'leri indirir, anahtar kelime taraması yapar,
LLM ile ESG göstergelerini çıkarır ve SQLite veri tabanına kaydeder. İstenirse PostgreSQL'e de aktarır.
        """
    )

    example_links = """Akbank,2024,https://www.example.com/akbank_2024.pdf
THY,2024,https://www.example.com/thy_2024.pdf"""

    report_links_text = st.text_area(
        "Rapor linkleri",
        value=example_links,
        height=180,
        help="Her satır: Şirket,Yıl,PDF_URL formatında olmalı. Sadece URL de yazabilirsiniz.",
    )

    parsed_links_df = parse_report_links_table(report_links_text)

    st.markdown("### 1. Okunan link tablosu")
    if parsed_links_df.empty:
        st.warning("Geçerli rapor linki bulunamadı.")
    else:
        st.dataframe(parsed_links_df, use_container_width=True)

    col_url_left, col_url_right = st.columns([2, 1])

    with col_url_left:
        url_keywords_text = st.text_area(
            "URL işleme anahtar kelimeleri",
            value=DEFAULT_KEYWORDS,
            height=260,
            key="url_keywords_text",
        )

    with col_url_right:
        st.markdown("#### URL işleme ayarları")
        url_context_sentences = st.slider("Kanıt metninde komşu cümle sayısı", 0, 3, 1, key="url_context_sentences")
        url_max_evidence_rows = st.number_input("Her rapor için LLM'e gönderilecek en fazla kanıt satırı", 5, 200, 50, key="url_max_evidence_rows")
        url_model_name = st.text_input("Model adı", value="gpt-4.1-mini", key="url_model_name")
        url_api_key = st.text_input("OpenAI API Key", value="", type="password", key="url_api_key")
        save_url_to_postgres = st.checkbox("Sonuçları PostgreSQL'e de kaydet", value=False, key="save_url_to_postgres")
        url_postgres_url = st.text_input("PostgreSQL DATABASE_URL", value=os.getenv("DATABASE_URL", ""), type="password", key="url_postgres_url")

    run_url_button = st.button("URL raporlarını indir ve işle", type="primary")

    if run_url_button:
        if parsed_links_df.empty:
            st.error("İşlenecek geçerli rapor linki yok.")
        elif not url_api_key and not os.getenv("OPENAI_API_KEY"):
            st.error("OpenAI API anahtarı bulunamadı. Ya kutuya API key girin ya da OPENAI_API_KEY ortam değişkenini tanımlayın.")
        elif save_url_to_postgres and not url_postgres_url:
            st.error("PostgreSQL'e kaydetmek için DATABASE_URL giriniz.")
        else:
            url_keywords = [k.strip() for k in url_keywords_text.splitlines() if k.strip()]
            if not url_keywords:
                st.error("En az bir anahtar kelime giriniz.")
            else:
                summary_rows = []
                progress = st.progress(0)
                status_box = st.empty()

                for i, row in parsed_links_df.iterrows():
                    company_name = str(row["company_name"]).strip()
                    report_year = str(row["year"]).strip()
                    report_url = str(row["url"]).strip()

                    status_box.info(f"İşleniyor ({i + 1}/{len(parsed_links_df)}): {company_name} {report_year}")

                    try:
                        result = process_pdf_url_record(
                            company_name=company_name,
                            report_year=report_year,
                            url=report_url,
                            keywords=url_keywords,
                            context_sentences=int(url_context_sentences),
                            max_evidence_rows_for_llm=int(url_max_evidence_rows),
                            model_name=url_model_name,
                            api_key=url_api_key if url_api_key else None,
                            save_to_postgres=save_url_to_postgres,
                            postgres_url=url_postgres_url if url_postgres_url else None,
                        )
                    except Exception as exc:
                        result = {
                            "company_name": company_name,
                            "year": report_year,
                            "file_name": "",
                            "url": report_url,
                            "page_count": None,
                            "evidence_count": 0,
                            "extracted_count": 0,
                            "saved_count": 0,
                            "postgres_saved_count": 0,
                            "status": "Hata",
                            "error": str(exc),
                        }

                    summary_rows.append(result)
                    progress.progress((i + 1) / len(parsed_links_df))

                status_box.success("URL rapor işleme tamamlandı.")
                url_summary_df = pd.DataFrame(summary_rows)
                st.session_state["url_summary_df"] = url_summary_df

                st.markdown("### 2. URL işleme özeti")
                st.dataframe(url_summary_df, use_container_width=True)

                db_df = load_indicators_from_database()
                if not db_df.empty:
                    st.markdown("### 3. Güncel SQLite veri tabanı özeti")
                    col_u1, col_u2, col_u3, col_u4 = st.columns(4)
                    col_u1.metric("Toplam kayıt", len(db_df))
                    col_u2.metric("Şirket sayısı", db_df["company_name"].nunique())
                    col_u3.metric("Yıl sayısı", db_df["year"].nunique())
                    col_u4.metric("Gösterge sayısı", db_df["indicator_name"].nunique())
                    excel_bytes = make_url_processing_excel_file(url_summary_df, db_df)
                    st.download_button(
                        label="URL işleme + veri tabanı Excel indir",
                        data=excel_bytes,
                        file_name="url_esg_processing_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                else:
                    st.warning("SQLite veri tabanında kayıt bulunamadı.")

    elif "url_summary_df" in st.session_state:
        st.markdown("### Önceki URL işleme özeti")
        st.dataframe(st.session_state["url_summary_df"], use_container_width=True)

    st.markdown("### 4. Link formatı örnekleri")
    st.code(
        """Akbank,2024,https://www.akbankinvestorrelations.com/tr/images/pdf/akbank-2024-entegre-faaliyet-raporu.pdf
THY,2024,https://investor.turkishairlines.com/documents/yillik-raporlar/2024-faaliyet-raporu.pdf
Arcelik,2024,https://www.arcelikglobal.com/media/xxxx/arcelik-2024-surdurulebilirlik-raporu.pdf""",
        language="text",
    )




# =====================================================
# TAB 11: BIST RAPOR LİNKLERİ
# =====================================================

if main_tab_11 is not None:
    with main_tab_11:
        st.subheader("BIST şirketleri için rapor linkleri")

        st.markdown(
            """
Bu bölüm, BIST şirketleri için faaliyet/sürdürülebilirlik raporu linklerini düzenlemek ve
10. sekmedeki URL işleme modülüne uygun formata dönüştürmek için eklendi.

Not: Şirket rapor linkleri her yıl değişebildiği için tabloyu gerektiğinde elle güncellemek gerekir.
        """
    )

    bist_df = get_bist_report_links_df()

    st.markdown("### 1. Hazır BIST rapor linkleri tablosu")
    edited_bist_df = st.data_editor(
        bist_df,
        use_container_width=True,
        num_rows="dynamic",
        key="bist_links_editor",
    )

    st.markdown("### 2. URL işleme formatı")

    url_text = make_url_text_from_bist_df(edited_bist_df)

    if url_text:
        st.text_area(
            "10. sekmeye yapıştırılacak metin",
            value=url_text,
            height=180,
            key="bist_url_text_output",
        )
    else:
        st.warning("URL alanı dolu olan satır yok. İşlenecek rapor linki üretilemedi.")

    col_bist_1, col_bist_2 = st.columns(2)

    with col_bist_1:
        excel_bytes = make_bist_links_excel_file(edited_bist_df)
        st.download_button(
            label="BIST rapor linkleri Excel indir",
            data=excel_bytes,
            file_name="bist_report_links.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_bist_2:
        st.download_button(
            label="URL işleme metnini TXT indir",
            data=url_text.encode("utf-8-sig"),
            file_name="bist_report_urls_for_processing.txt",
            mime="text/plain",
            disabled=not bool(url_text),
        )

    st.markdown("### 3. Kullanım")

    st.info(
        "Yukarıdaki metni kopyalayıp 10. sekmedeki 'Rapor linkleri' alanına yapıştırın. "
        "Sonra URL raporlarını indir ve işle düğmesine basın."
    )

    st.markdown("### 4. Eksik URL ekleme önerisi")

    st.code(
        """
Şirket,Yıl,PDF_URL
Akbank,2024,https://...
Türk Hava Yolları,2024,https://...
Arçelik,2024,https://...
Garanti BBVA,2024,https://...
Koç Holding,2024,https://...
        """,
        language="text",
    )




# =====================================================
# TAB 12: ESG SÖZLÜK VE VERİ KALİTE KONTROL
# =====================================================

if main_tab_12 is not None:
    with main_tab_12:
        st.subheader("ESG gösterge sözlüğü ve veri kalite kontrol")

        st.markdown(
            """
Bu bölüm LLM ile çıkarılan göstergeleri standart ESG gösterge sözlüğüyle eşleştirir
ve akademik modelleme öncesi veri kalite kontrollerini yapar.
        """
    )

    dictionary_df = get_esg_dictionary_df()

    st.markdown("### 1. ESG gösterge sözlüğü")
    edited_dictionary_df = st.data_editor(
        dictionary_df,
        use_container_width=True,
        num_rows="dynamic",
        key="esg_dictionary_editor",
    )

    st.download_button(
        label="ESG gösterge sözlüğünü Excel indir",
        data=make_bist_links_excel_file(edited_dictionary_df),
        file_name="esg_indicator_dictionary.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### 2. Kalite kontrol veri kaynağı")

    source_option = st.radio(
        "Kalite kontrol hangi veri üzerinden yapılsın?",
        ["SQLite veri tabanı", "PostgreSQL veri tabanı", "Oturumdaki çoklu şirket veri seti"],
        horizontal=True,
    )

    qc_source_df = pd.DataFrame()

    if source_option == "SQLite veri tabanı":
        qc_source_df = load_indicators_from_database()
    elif source_option == "PostgreSQL veri tabanı":
        secure_url = get_secure_database_url()
        if secure_url:
            try:
                qc_source_df = load_indicators_from_postgres(secure_url)
            except Exception as exc:
                st.error(f"PostgreSQL verisi okunamadı: {exc}")
        else:
            st.warning("DATABASE_URL bulunamadı. Secrets veya ortam değişkenini kontrol ediniz.")
    else:
        qc_source_df = st.session_state.get("master_indicators_df", pd.DataFrame())

    if qc_source_df.empty:
        st.warning("Seçilen kaynakta kalite kontrol yapılacak veri bulunamadı.")
    else:
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        col_q1.metric("Kayıt sayısı", len(qc_source_df))
        col_q2.metric("Şirket sayısı", qc_source_df["company_name"].nunique() if "company_name" in qc_source_df.columns else 0)
        col_q3.metric("Yıl sayısı", qc_source_df["year"].nunique() if "year" in qc_source_df.columns else 0)
        col_q4.metric("Gösterge sayısı", qc_source_df["indicator_name"].nunique() if "indicator_name" in qc_source_df.columns else 0)

        st.markdown("### 3. Standartlaştırılmış veri")
        standardized_df = add_standardized_columns(qc_source_df)
        st.dataframe(standardized_df, use_container_width=True)

        st.markdown("### 4. Veri kalite sorunları")
        issues_df = run_data_quality_checks(qc_source_df)
        if issues_df.empty:
            st.success("Belirlenen kurallara göre veri kalite sorunu bulunmadı.")
        else:
            issue_summary = issues_df.groupby(["severity", "issue_type"]).size().reset_index(name="count")
            st.markdown("#### Sorun özeti")
            st.dataframe(issue_summary, use_container_width=True)
            st.markdown("#### Sorun detayları")
            st.dataframe(issues_df, use_container_width=True)

            priority_issue_types = [
                "conflicting_standard_value",
                "low_confidence",
                "unit_conversion_applied",
            ]
            priority_issues_df = issues_df[issues_df["issue_type"].isin(priority_issue_types)]
            if not priority_issues_df.empty:
                st.markdown("#### Öncelikli inceleme listesi")
                st.dataframe(priority_issues_df, use_container_width=True)

        st.markdown("### 5. Standart ESG model paneli")
        standardized_model_df = build_standardized_model_ready_dataset(qc_source_df)
        if standardized_model_df.empty:
            st.warning("Standart ESG sözlüğüne göre model paneli üretilemedi.")
        else:
            st.dataframe(standardized_model_df, use_container_width=True)

        st.markdown("### 6. Kalite kontrol Excel çıktısı")
        qc_excel_bytes = make_quality_control_excel_file(
            source_df=qc_source_df,
            standardized_df=standardized_df,
            issues_df=issues_df,
            standardized_model_df=standardized_model_df,
            dictionary_df=edited_dictionary_df,
        )
        st.download_button(
            label="ESG kalite kontrol raporunu Excel indir",
            data=qc_excel_bytes,
            file_name="esg_quality_control_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("### 7. Güvenli DATABASE_URL durumu")
    secure_database_url = get_secure_database_url()
    if secure_database_url:
        st.success(f"DATABASE_URL güvenli kaynaktan okunuyor: {mask_database_url(secure_database_url)}")
    else:
        st.warning("DATABASE_URL bulunamadı. Streamlit Secrets veya ortam değişkeni tanımlayınız.")

    st.info("Yayın ortamında PostgreSQL bağlantı adresini ekranda elle yazmak yerine Streamlit Secrets içindeki DATABASE_URL değerini kullanmanız önerilir.")




# =====================================================
# TAB 13: BIST RAPOR LİNKİ ARAMA / DOĞRULAMA
# =====================================================

if main_tab_13 is not None:
    with main_tab_13:
        st.subheader("BIST rapor linki arama ve doğrulama")

        st.markdown(
            """
Bu bölüm BIST şirketleri için aday faaliyet/sürdürülebilirlik raporu linklerini doğrular.

Kontroller:

- URL erişilebilir mi?
- HTTP durum kodu nedir?
- Content-Type PDF mi?
- Dosya gerçekten `%PDF` başlığıyla mı başlıyor?
- Dosya boyutu nedir?
- URL içinde beklenen yıl geçiyor mu?
- Genel doğrulama skoru nedir?
        """
    )

    st.markdown("### 1. Arama sorgusu üretici")

    col_search_1, col_search_2, col_search_3 = st.columns(3)

    with col_search_1:
        search_company = st.text_input("Şirket adı", value="Akbank", key="search_company")

    with col_search_2:
        search_ticker = st.text_input("BIST kodu", value="AKBNK", key="search_ticker")

    with col_search_3:
        search_year = st.text_input("Rapor yılı", value="2024", key="search_year")

    search_queries = generate_search_queries_for_company(search_company, search_ticker, search_year)

    st.markdown("#### Kopyalanabilir arama sorguları")
    st.code("\n".join(search_queries), language="text")

    st.info(
        "Bu sorguları Google/Bing'de arayıp bulduğunuz PDF linklerini aşağıdaki aday linkler alanına ekleyebilirsiniz."
    )

    st.markdown("### 2. Aday rapor linkleri")

    default_candidate_links = """Akbank,2024,https://www.akbankinvestorrelations.com/tr/images/pdf/akbank-2024-entegre-faaliyet-raporu.pdf
Türk Hava Yolları,2024,https://investor.turkishairlines.com/documents/yillik-raporlar/2024-faaliyet-raporu.pdf"""

    candidate_links_text = st.text_area(
        "Aday linkler",
        value=default_candidate_links,
        height=180,
        help="Her satır: Şirket,Yıl,PDF_URL formatında olmalı.",
        key="candidate_links_text",
    )

    candidate_df = parse_candidate_report_links(candidate_links_text)

    if candidate_df.empty:
        st.warning("Geçerli aday link bulunamadı.")
    else:
        st.markdown("#### Okunan aday linkler")
        st.dataframe(candidate_df, use_container_width=True)

    col_validate_1, col_validate_2 = st.columns([1, 2])

    with col_validate_1:
        minimum_score = st.slider(
            "URL işleme metnine alınacak minimum skor",
            min_value=0,
            max_value=100,
            value=40,
            step=10,
        )

    validate_button = st.button("Aday linkleri doğrula", type="primary")

    if validate_button:
        if candidate_df.empty:
            st.error("Doğrulanacak aday link yok.")
        else:
            rows = []
            progress = st.progress(0)
            status_box = st.empty()

            for i, row in candidate_df.iterrows():
                company = str(row.get("company_name", "")).strip()
                year = str(row.get("year", "")).strip()
                url = str(row.get("url", "")).strip()

                status_box.info(f"Doğrulanıyor ({i + 1}/{len(candidate_df)}): {company} {year}")

                validation = validate_report_url(url, expected_year=year)
                validation["company_name"] = company
                validation["year"] = year
                rows.append(validation)

                progress.progress((i + 1) / len(candidate_df))

            status_box.success("Link doğrulama tamamlandı.")

            validated_df = pd.DataFrame(rows)

            preferred_cols = [
                "company_name",
                "year",
                "url",
                "validation_status",
                "validation_score",
                "status_code",
                "is_accessible",
                "is_pdf_content_type",
                "starts_with_pdf_header",
                "content_length_mb",
                "year_in_url",
                "content_type",
                "error",
            ]

            existing_cols = [c for c in preferred_cols if c in validated_df.columns]
            validated_df = validated_df[existing_cols + [c for c in validated_df.columns if c not in existing_cols]]

            st.session_state["validated_links_df"] = validated_df

            st.markdown("### 3. Doğrulama sonuçları")
            st.dataframe(validated_df, use_container_width=True)

            url_text = make_validated_links_url_text(validated_df, minimum_score=minimum_score)

            st.markdown("### 4. URL işleme modülüne uygun doğrulanmış metin")

            if url_text:
                st.text_area(
                    "10. sekmeye yapıştırılacak doğrulanmış URL metni",
                    value=url_text,
                    height=160,
                    key="validated_url_text",
                )

                excel_bytes = make_link_validation_excel_file(candidate_df, validated_df, url_text)

                st.download_button(
                    label="Link doğrulama sonuçlarını Excel indir",
                    data=excel_bytes,
                    file_name="bist_report_link_validation.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                st.download_button(
                    label="Doğrulanmış URL metnini TXT indir",
                    data=url_text.encode("utf-8-sig"),
                    file_name="validated_report_urls_for_processing.txt",
                    mime="text/plain",
                )
            else:
                st.warning("Minimum skoru geçen link bulunamadı.")

    elif "validated_links_df" in st.session_state:
        validated_df = st.session_state["validated_links_df"]
        st.markdown("### Önceki doğrulama sonuçları")
        st.dataframe(validated_df, use_container_width=True)

        url_text = make_validated_links_url_text(validated_df, minimum_score=minimum_score)

        if url_text:
            st.text_area(
                "10. sekmeye yapıştırılacak doğrulanmış URL metni",
                value=url_text,
                height=160,
                key="previous_validated_url_text",
            )

    st.markdown("### 5. Skor yorumu")

    st.markdown(
        """
| Skor | Yorum |
|---:|---|
| 70–100 | Güçlü aday: erişilebilir, PDF olma ihtimali yüksek |
| 40–69 | Olası aday: kontrol edilmeli |
| 0–39 | Zayıf aday: link bozuk veya PDF olmayabilir |
        """
    )




# =====================================================
# TAB 14: n8n TAKİP EDİLEN RAPORLAR
# =====================================================

if main_tab_14 is not None:
    with main_tab_14:
        st.subheader("n8n takip edilen raporlar")

        st.markdown(
            """
Bu bölüm n8n workflow'unun PostgreSQL'e yazdığı rapor linki takip sonuçlarını okur.

n8n şu tabloya yazar:

`report_link_checks`

Streamlit bu tablodan güçlü/olası aday linkleri alır ve 10. sekmedeki URL işleme modülüne uygun metne dönüştürür.
        """
    )

    secure_url = get_secure_database_url()

    if not secure_url:
        st.warning("DATABASE_URL bulunamadı. Streamlit Secrets veya ortam değişkenini kontrol ediniz.")
    else:
        st.success(f"PostgreSQL bağlantısı bulundu: {mask_database_url(secure_url)}")

        col_n8n_init, col_n8n_refresh = st.columns(2)

        with col_n8n_init:
            if st.button("n8n takip tablolarını oluştur / kontrol et"):
                try:
                    init_report_tracking_tables(secure_url)
                    st.success("report_sources ve report_link_checks tabloları hazır.")
                except Exception as exc:
                    st.error(f"Tablo oluşturma/kontrol hatası: {exc}")

        with col_n8n_refresh:
            refresh_n8n = st.button("n8n rapor linklerini yenile")

        try:
            sources_df = load_report_sources_from_postgres(secure_url)
        except Exception as exc:
            sources_df = pd.DataFrame()
            st.error(f"report_sources okunamadı: {exc}")

        try:
            checks_df = load_report_link_checks_from_postgres(secure_url)
        except Exception as exc:
            checks_df = pd.DataFrame()
            st.error(f"report_link_checks okunamadı: {exc}")

        st.markdown("### 1. n8n takip kaynakları")

        if sources_df.empty:
            st.warning("report_sources tablosunda takip kaynağı bulunamadı.")
        else:
            st.dataframe(sources_df, use_container_width=True)

        with st.expander("Yeni takip kaynağı ekle"):
            col_src1, col_src2, col_src3 = st.columns(3)

            with col_src1:
                new_company = st.text_input("Şirket adı", value="Arçelik", key="n8n_new_company")
                new_ticker = st.text_input("BIST kodu", value="ARCLK", key="n8n_new_ticker")

            with col_src2:
                new_year = st.text_input("Rapor yılı", value="2024", key="n8n_new_year")
                new_source_type = st.text_input("Kaynak türü", value="reports_page", key="n8n_new_source_type")

            with col_src3:
                new_source_url = st.text_area(
                    "Kaynak sayfa URL",
                    value="",
                    height=100,
                    key="n8n_new_source_url",
                )

            if st.button("Takip kaynağını PostgreSQL'e ekle"):
                if not new_company or not new_year or not new_source_url:
                    st.error("Şirket adı, yıl ve kaynak URL zorunludur.")
                else:
                    try:
                        add_report_source_to_postgres(
                            database_url=secure_url,
                            company_name=new_company,
                            ticker=new_ticker,
                            report_year=new_year,
                            source_url=new_source_url,
                            source_type=new_source_type,
                        )
                        st.success("Yeni takip kaynağı eklendi. n8n bir sonraki çalışmada bu sayfayı tarayacak.")
                    except Exception as exc:
                        st.error(f"Kaynak ekleme hatası: {exc}")

        st.markdown("### 2. n8n link kontrol sonuçları")

        if checks_df.empty:
            st.info("Henüz n8n tarafından yazılmış link kontrol sonucu yok.")
        else:
            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            col_c1.metric("Toplam link", len(checks_df))
            col_c2.metric("Şirket sayısı", checks_df["company_name"].nunique())
            col_c3.metric("Güçlü aday", int((checks_df["validation_status"] == "strong").sum()))
            col_c4.metric("Olası aday", int((checks_df["validation_status"] == "possible").sum()))

            st.dataframe(checks_df, use_container_width=True)

            st.markdown("### 3. Filtrelenmiş güçlü/olası aday linkler")

            min_n8n_score = st.slider(
                "URL işleme metnine alınacak minimum n8n skoru",
                min_value=0,
                max_value=100,
                value=40,
                step=10,
                key="n8n_min_score",
            )

            status_options = st.multiselect(
                "Dahil edilecek durumlar",
                ["strong", "possible", "weak", "invalid"],
                default=["strong", "possible"],
                key="n8n_status_options",
            )

            filtered_df = checks_df.copy()

            if "validation_score" in filtered_df.columns:
                filtered_df["validation_score"] = pd.to_numeric(
                    filtered_df["validation_score"],
                    errors="coerce",
                ).fillna(0)
                filtered_df = filtered_df[filtered_df["validation_score"] >= min_n8n_score]

            if status_options and "validation_status" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["validation_status"].isin(status_options)]

            st.dataframe(filtered_df, use_container_width=True)

            st.markdown("### 4. 10. sekmeye aktarılacak URL işleme metni")

            url_text = make_n8n_validated_url_text(
                checks_df=checks_df,
                minimum_score=min_n8n_score,
                statuses=status_options,
            )

            if url_text:
                st.text_area(
                    "10. URL'den Rapor İşleme sekmesine yapıştırılacak metin",
                    value=url_text,
                    height=180,
                    key="n8n_url_processing_text",
                )

                st.download_button(
                    label="n8n doğrulanmış URL metnini TXT indir",
                    data=url_text.encode("utf-8-sig"),
                    file_name="n8n_validated_report_urls.txt",
                    mime="text/plain",
                )

                excel_bytes = make_n8n_report_links_excel_file(
                    sources_df=sources_df,
                    checks_df=checks_df,
                    url_text=url_text,
                )

                st.download_button(
                    label="n8n rapor takip Excel çıktısı indir",
                    data=excel_bytes,
                    file_name="n8n_report_tracking_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.warning("Seçilen kriterlere göre URL işleme metni üretilemedi.")

        st.markdown("### 5. n8n entegrasyon notu")

        st.info(
            "Bu sekme n8n workflow'unun ürettiği linkleri okur. "
            "n8n bağımsız çalışır; Streamlit yalnızca PostgreSQL'deki sonuçları gösterir."
        )




# =====================================================
# TAB 15: AKADEMİK PANEL VERİ ANALİZİ
# =====================================================

if main_tab_15 is not None:
    with main_tab_15:
        st.subheader("Akademik panel veri analizi")

        st.markdown(
            """
Bu bölüm ESG göstergelerinden akademik çalışmaya uygun şirket-yıl panel veri seti üretir.

Üretilen çıktılar:

- Standart ESG panel veri
- Tanımlayıcı istatistikler
- Eksik veri özeti
- Korelasyon matrisi
- Şirket-yıl kapsam tablosu
- Model önerileri
- Stata `.do` dosyası
- SPSS `.sps` dosyası
- Excel ve ZIP analiz paketi
        """
    )

    st.markdown("### 1. Veri kaynağı")

    panel_source_option = st.radio(
        "Panel analiz veri kaynağı",
        [
            "PostgreSQL veri tabanı",
            "SQLite veri tabanı",
            "Oturumdaki çoklu şirket veri seti",
        ],
        horizontal=True,
        key="academic_panel_source",
    )

    source_df = pd.DataFrame()

    if panel_source_option == "PostgreSQL veri tabanı":
        secure_url = get_secure_database_url()
        if secure_url:
            try:
                source_df = load_indicators_from_postgres(secure_url)
            except Exception as exc:
                st.error(f"PostgreSQL verisi okunamadı: {exc}")
        else:
            st.warning("DATABASE_URL bulunamadı.")

    elif panel_source_option == "SQLite veri tabanı":
        source_df = load_indicators_from_database()

    else:
        source_df = st.session_state.get("master_indicators_df", pd.DataFrame())

    if source_df.empty:
        st.warning("Seçilen kaynakta analiz yapılacak ESG gösterge verisi bulunamadı.")
    else:
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        col_a1.metric("Kayıt sayısı", len(source_df))
        col_a2.metric("Şirket sayısı", source_df["company_name"].nunique() if "company_name" in source_df.columns else 0)
        col_a3.metric("Yıl sayısı", source_df["year"].nunique() if "year" in source_df.columns else 0)
        col_a4.metric("Gösterge sayısı", source_df["indicator_name"].nunique() if "indicator_name" in source_df.columns else 0)

        st.markdown("### 2. Standart ESG panel veri")

        standard_panel_df = build_standardized_model_ready_dataset(source_df)

        if standard_panel_df.empty:
            st.warning(
                "Standart ESG sözlüğüne göre model paneli üretilemedi. "
                "Önce 12. sekmede göstergelerin sözlükle eşleştiğini kontrol ediniz."
            )
        else:
            st.dataframe(standard_panel_df, use_container_width=True)

            numeric_cols = numeric_panel_columns(standard_panel_df)

            st.markdown("### 3. Değişken seçimi")

            if len(numeric_cols) == 0:
                st.warning("Sayısal analiz değişkeni bulunamadı.")
            else:
                default_dep = numeric_cols[0]

                dependent_var = st.selectbox(
                    "Bağımlı değişken",
                    options=numeric_cols,
                    index=0,
                    key="academic_dependent_var",
                )

                default_indep = [c for c in numeric_cols if c != dependent_var][:5]

                independent_vars = st.multiselect(
                    "Bağımsız değişkenler",
                    options=[c for c in numeric_cols if c != dependent_var],
                    default=default_indep,
                    key="academic_independent_vars",
                )

                st.markdown("### 4. Tanımlayıcı analizler")

                desc_df = make_panel_descriptive_statistics(standard_panel_df)
                missing_df = make_panel_missing_summary(standard_panel_df)
                coverage_df = make_panel_company_coverage(standard_panel_df)
                corr_df = make_panel_correlation_matrix(standard_panel_df)
                model_suggestions_df = suggest_panel_models(standard_panel_df)

                sub_tab_desc, sub_tab_missing, sub_tab_corr, sub_tab_coverage, sub_tab_models = st.tabs(
                    [
                        "Tanımlayıcı İstatistikler",
                        "Eksik Veri",
                        "Korelasyon",
                        "Şirket-Yıl Kapsamı",
                        "Model Önerileri",
                    ]
                )

                with sub_tab_desc:
                    st.dataframe(desc_df, use_container_width=True)

                with sub_tab_missing:
                    st.dataframe(missing_df, use_container_width=True)

                with sub_tab_corr:
                    if corr_df.empty:
                        st.info("Korelasyon matrisi için yeterli sayısal değişken yok.")
                    else:
                        st.dataframe(corr_df, use_container_width=True)

                with sub_tab_coverage:
                    st.dataframe(coverage_df, use_container_width=True)

                with sub_tab_models:
                    st.dataframe(model_suggestions_df, use_container_width=True)

                st.markdown("### 5. Stata ve SPSS analiz kodları")

                if dependent_var and independent_vars:
                    stata_code = build_stata_panel_do_file(
                        panel_df=standard_panel_df,
                        dependent_var=dependent_var,
                        independent_vars=independent_vars,
                    )

                    spss_code = build_spss_panel_syntax(
                        panel_df=standard_panel_df,
                        dependent_var=dependent_var,
                        independent_vars=independent_vars,
                    )

                    code_tab_stata, code_tab_spss = st.tabs(["Stata do-file", "SPSS syntax"])

                    with code_tab_stata:
                        st.code(stata_code, language="stata")

                    with code_tab_spss:
                        st.code(spss_code, language="spss")

                    st.markdown("### 6. Akademik analiz çıktıları")

                    excel_bytes = make_academic_panel_excel_file(
                        panel_df=standard_panel_df,
                        desc_df=desc_df,
                        missing_df=missing_df,
                        corr_df=corr_df,
                        coverage_df=coverage_df,
                        model_suggestions_df=model_suggestions_df,
                    )

                    zip_bytes = make_academic_panel_zip_file(
                        panel_df=standard_panel_df,
                        excel_bytes=excel_bytes,
                        stata_code=stata_code,
                        spss_code=spss_code,
                    )

                    col_down1, col_down2, col_down3 = st.columns(3)

                    with col_down1:
                        st.download_button(
                            label="Akademik panel Excel indir",
                            data=excel_bytes,
                            file_name="academic_panel_analysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

                    with col_down2:
                        csv_buffer = io.StringIO()
                        standard_panel_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
                        st.download_button(
                            label="Standart panel CSV indir",
                            data=csv_buffer.getvalue().encode("utf-8-sig"),
                            file_name="standard_esg_panel.csv",
                            mime="text/csv",
                        )

                    with col_down3:
                        st.download_button(
                            label="ZIP analiz paketi indir",
                            data=zip_bytes,
                            file_name="academic_panel_analysis_pack.zip",
                            mime="application/zip",
                        )

                    st.download_button(
                        label="Stata do-file indir",
                        data=stata_code.encode("utf-8-sig"),
                        file_name="stata_panel_analysis.do",
                        mime="text/plain",
                    )

                    st.download_button(
                        label="SPSS syntax indir",
                        data=spss_code.encode("utf-8-sig"),
                        file_name="spss_panel_analysis.sps",
                        mime="text/plain",
                    )

                else:
                    st.info("Stata/SPSS kodu üretmek için bağımlı ve en az bir bağımsız değişken seçiniz.")

        st.markdown("### 7. Akademik not")

        st.info(
            "Bu modül analiz dosyalarını hazırlar. Nihai makale/bildiri için model seçimi, "
            "değişken dönüşümleri, uç değer kontrolü, durağanlık ve sağlamlık analizleri ayrıca değerlendirilmelidir."
        )



st.divider()

st.markdown(
    """
### Sonraki aşama

Bu sürümde çok sayıda ülke için World Bank API indirme akışı güçlendirildi.

Bir sonraki sürümde şunları ekleyebiliriz:

- PostgreSQL kayıtlarını sürümleme ve denetim izi
- n8n sonuçlarından tek tıkla URL işleme
- BIST şirket raporları için geniş otomatik takip listesi
- Rol bazlı kullanıcı yönetimi
- Makale tablo ve yöntem metni otomatik üretimi
    """
)
