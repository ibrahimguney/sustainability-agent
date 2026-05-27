import json
import os
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd


ESG_INDICATOR_DICTIONARY = [
    {"standard_name": "scope1_emissions", "display_name": "Kapsam 1 Emisyon", "category": "Environmental", "metric_type": "actual_value", "expected_units": "ton CO2e;tCO2e;ton", "keywords": "kapsam 1;scope 1;direkt emisyon;direct emission", "min_value": 0, "max_value": None},
    {"standard_name": "scope2_emissions", "display_name": "Kapsam 2 Emisyon", "category": "Environmental", "metric_type": "actual_value", "expected_units": "ton CO2e;tCO2e;ton", "keywords": "kapsam 2;scope 2;dolayli emisyon;electricity emissions", "min_value": 0, "max_value": None},
    {"standard_name": "scope3_emissions", "display_name": "Kapsam 3 Emisyon", "category": "Environmental", "metric_type": "actual_value", "expected_units": "ton CO2e;tCO2e;ton", "keywords": "kapsam 3;scope 3;diger dolayli emisyon", "min_value": 0, "max_value": None},
    {"standard_name": "total_ghg_emissions", "display_name": "Toplam Sera Gazi Emisyonu", "category": "Environmental", "metric_type": "actual_value", "expected_units": "ton CO2e;tCO2e;ton", "keywords": "toplam sera gazi;toplam emisyon;total ghg;total emissions", "min_value": 0, "max_value": None},
    {"standard_name": "energy_consumption", "display_name": "Toplam Enerji Tuketimi", "category": "Environmental", "metric_type": "actual_value", "expected_units": "MWh;kWh;GJ;TJ", "keywords": "enerji tuketimi;toplam enerji;energy consumption;total energy", "min_value": 0, "max_value": None},
    {"standard_name": "renewable_energy_ratio", "display_name": "Yenilenebilir Enerji Orani", "category": "Environmental", "metric_type": "ratio", "expected_units": "yuzde;percent;%", "keywords": "yenilenebilir enerji oran;yenilenebilir elektrik;renewable energy;renewable electricity", "min_value": 0, "max_value": 100},
    {"standard_name": "water_consumption", "display_name": "Su Tuketimi", "category": "Environmental", "metric_type": "actual_value", "expected_units": "m3;metrekup;ton", "keywords": "su tuketimi;su cekimi;water consumption;water withdrawal", "min_value": 0, "max_value": None},
    {"standard_name": "total_waste", "display_name": "Toplam Atik", "category": "Environmental", "metric_type": "actual_value", "expected_units": "ton;kg", "keywords": "toplam atik;atik miktari;total waste;waste generated", "min_value": 0, "max_value": None},
    {"standard_name": "recycled_waste_ratio", "display_name": "Geri Kazanilan Atik Orani", "category": "Environmental", "metric_type": "ratio", "expected_units": "yuzde;percent;%", "keywords": "geri kazanim orani;geri donusturulen atik;recycled waste;waste recycling", "min_value": 0, "max_value": 100},
    {"standard_name": "female_employee_ratio", "display_name": "Kadin Calisan Orani", "category": "Social", "metric_type": "ratio", "expected_units": "yuzde;percent;%", "keywords": "kadin calisan orani;kadin calisan;female employee;women employee", "min_value": 0, "max_value": 100},
    {"standard_name": "employee_count", "display_name": "Toplam Calisan Sayisi", "category": "Social", "metric_type": "actual_value", "expected_units": "kisi;person;employee", "keywords": "calisan sayisi;toplam calisan;employee count;number of employees", "min_value": 0, "max_value": None},
    {"standard_name": "occupational_accident_count", "display_name": "Is Kazasi Sayisi", "category": "Social", "metric_type": "actual_value", "expected_units": "adet;kisi;case", "keywords": "is kazasi;occupational accident;work accident", "min_value": 0, "max_value": None},
    {"standard_name": "training_hours", "display_name": "Egitim Saati", "category": "Social", "metric_type": "actual_value", "expected_units": "saat;hour", "keywords": "egitim saati;training hours;employee training", "min_value": 0, "max_value": None},
    {"standard_name": "sustainability_committee", "display_name": "Surdurulebilirlik Komitesi", "category": "Governance", "metric_type": "policy_indicator", "expected_units": "adet;var/yok;none", "keywords": "surdurulebilirlik komitesi;sustainability committee;esg committee", "min_value": 0, "max_value": None},
    {"standard_name": "net_zero_target_year", "display_name": "Net Sifir Hedef Yili", "category": "Environmental", "metric_type": "target_year", "expected_units": "yil;year", "keywords": "net sifir;net zero;karbon notr;carbon neutral", "min_value": 2020, "max_value": 2100},
]


def normalize_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text == "" or text.lower() in ["null", "none", "nan", "yok", "-"]:
        return None

    text = text.replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")

    text = re.sub(r"[^0-9\.\-]", "", text)
    try:
        return float(text)
    except Exception:
        return None


def extract_json_from_response(raw_text: str):
    if not raw_text:
        return []

    raw_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    array_match = re.search(r"\[[\s\S]*\]", raw_text)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    object_match = re.search(r"\{[\s\S]*\}", raw_text)
    if object_match:
        try:
            parsed = json.loads(object_match.group(0))
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            pass

    return []


def parse_company_year_from_filename(file_name: str) -> Tuple[str, str]:
    base = os.path.basename(file_name)
    base = re.sub(r"\.pdf$", "", base, flags=re.IGNORECASE)

    year_match = re.search(r"(20\d{2})", base)
    year = year_match.group(1) if year_match else ""
    company = base.replace(year, "") if year else base

    company = re.sub(r"[_\-\.\(\)\[\]]+", " ", company)
    company = re.sub(
        r"\b(faaliyet|raporu|surdurulebilirlik|sürdürülebilirlik|entegre|annual|report|esg|ir)\b",
        " ",
        company,
        flags=re.IGNORECASE,
    )
    company = re.sub(r"\s+", " ", company).strip()

    if not company:
        company = base

    return company, year


def get_esg_dictionary_df() -> pd.DataFrame:
    return pd.DataFrame(ESG_INDICATOR_DICTIONARY)


def normalize_for_matching(text: str) -> str:
    text = str(text or "").lower()
    for old, new in {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def map_indicator_to_standard(indicator_name: str, source_keyword: str = "", evidence_text: str = "") -> Dict:
    dictionary_df = get_esg_dictionary_df()
    source_text = normalize_for_matching(f"{indicator_name} {source_keyword} {str(evidence_text)[:300]}")
    best_score, best_row = 0, None

    for _, row in dictionary_df.iterrows():
        score = 0
        for keyword in str(row.get("keywords", "")).split(";"):
            kw = normalize_for_matching(keyword)
            if kw and kw in source_text:
                score += len(kw.split()) + 1
        if normalize_for_matching(row.get("display_name", "")) in source_text:
            score += 4
        if score > best_score:
            best_score, best_row = score, row

    if best_row is None or best_score == 0:
        return {"standard_name": None, "standard_display_name": None, "standard_category": None, "standard_metric_type": None, "expected_units": None, "dictionary_match_score": 0}

    return {
        "standard_name": best_row.get("standard_name"),
        "standard_display_name": best_row.get("display_name"),
        "standard_category": best_row.get("category"),
        "standard_metric_type": best_row.get("metric_type"),
        "expected_units": best_row.get("expected_units"),
        "dictionary_match_score": best_score,
    }

def get_visible_tabs_for_role(role: str, all_tabs: List[str], user_tabs: List[str], viewer_tabs: List[str]) -> List[str]:
    if role == "admin":
        return all_tabs
    if role == "user":
        return user_tabs
    return viewer_tabs

LLM_INDICATOR_COLUMNS = [
    "company_name",
    "year",
    "indicator_name",
    "category",
    "value",
    "numeric_value",
    "unit",
    "page",
    "source_keyword",
    "evidence_text",
    "confidence",
    "notes",
]


def normalize_confidence(value):
    numeric = normalize_number(value)
    if numeric is None:
        return None
    if numeric > 10 and numeric <= 100:
        numeric = numeric / 100
    return max(0.0, min(1.0, numeric))


def normalize_page(value):
    numeric = normalize_number(value)
    if numeric is None:
        return None
    return int(numeric)


def normalize_extracted_indicator_records(records, default_company_name: str = "", default_report_year: str = "") -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=LLM_INDICATOR_COLUMNS)

    df = pd.DataFrame(records)

    for col in LLM_INDICATOR_COLUMNS:
        if col not in df.columns:
            df[col] = None

    for col in ["company_name", "year", "indicator_name", "category", "value", "unit", "source_keyword", "evidence_text", "notes"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    if default_company_name:
        df.loc[df["company_name"] == "", "company_name"] = str(default_company_name).strip()

    if default_report_year:
        df.loc[df["year"] == "", "year"] = str(default_report_year).strip()

    numeric_source = df["numeric_value"].where(df["numeric_value"].notna(), df["value"])
    df["numeric_value"] = numeric_source.apply(normalize_number)
    df["page"] = df["page"].apply(normalize_page)
    df["confidence"] = df["confidence"].apply(normalize_confidence)

    return df[LLM_INDICATOR_COLUMNS]

STANDARD_UNIT_BY_NAME = {
    "scope1_emissions": "ton CO2e",
    "scope2_emissions": "ton CO2e",
    "scope3_emissions": "ton CO2e",
    "total_ghg_emissions": "ton CO2e",
    "energy_consumption": "MWh",
    "renewable_energy_ratio": "%",
    "water_consumption": "m3",
    "total_waste": "ton",
    "recycled_waste_ratio": "%",
    "female_employee_ratio": "%",
    "employee_count": "person",
    "occupational_accident_count": "case",
    "training_hours": "hour",
    "sustainability_committee": "count",
    "net_zero_target_year": "year",
}


def normalize_unit_value(standard_name: str, metric_type: str, value, unit: str) -> Dict:
    numeric = normalize_number(value)
    standard_unit = STANDARD_UNIT_BY_NAME.get(str(standard_name or ""), "")
    result = {
        "standard_unit": standard_unit,
        "normalized_numeric_value": numeric,
        "unit_conversion_note": "",
    }

    if numeric is None:
        return result

    unit_norm = normalize_for_matching(unit)
    metric = str(metric_type or "")

    if metric == "ratio" or standard_unit == "%":
        result["standard_unit"] = "%"
        if numeric <= 1 and "%" not in str(unit or "") and "percent" not in unit_norm and "yuzde" not in unit_norm:
            result["normalized_numeric_value"] = numeric * 100
            result["unit_conversion_note"] = "decimal_ratio_to_percent"
        return result

    if standard_unit == "ton CO2e":
        if "kg" in unit_norm:
            result["normalized_numeric_value"] = numeric / 1000
            result["unit_conversion_note"] = "kg_to_ton"
        return result

    if standard_unit == "ton":
        if "kg" in unit_norm:
            result["normalized_numeric_value"] = numeric / 1000
            result["unit_conversion_note"] = "kg_to_ton"
        return result

    if standard_unit == "MWh":
        if "kwh" in unit_norm:
            result["normalized_numeric_value"] = numeric / 1000
            result["unit_conversion_note"] = "kwh_to_mwh"
        elif unit_norm == "gj" or " gigajoule" in unit_norm:
            result["normalized_numeric_value"] = numeric * 0.277778
            result["unit_conversion_note"] = "gj_to_mwh"
        elif unit_norm == "tj" or " terajoule" in unit_norm:
            result["normalized_numeric_value"] = numeric * 277.778
            result["unit_conversion_note"] = "tj_to_mwh"
        return result

    return result

def filter_tabs_for_focus(visible_tabs: List[str], focus_tabs: List[str]) -> List[str]:
    return [tab for tab in focus_tabs if tab in visible_tabs]

LLM_STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "company_name": {"type": "string"},
                    "year": {"type": "string"},
                    "indicator_name": {"type": "string"},
                    "category": {"type": "string", "enum": ["Environmental", "Social", "Governance", "Other"]},
                    "value": {"type": "string"},
                    "unit": {"type": ["string", "null"]},
                    "page": {"type": ["integer", "null"]},
                    "source_keyword": {"type": "string"},
                    "evidence_text": {"type": "string"},
                    "confidence": {"type": ["number", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": [
                    "company_name",
                    "year",
                    "indicator_name",
                    "category",
                    "value",
                    "unit",
                    "page",
                    "source_keyword",
                    "evidence_text",
                    "confidence",
                    "notes",
                ],
            },
        }
    },
    "required": ["indicators"],
}


def get_llm_response_text_format() -> Dict:
    return {
        "format": {
            "type": "json_schema",
            "name": "esg_indicator_extraction",
            "description": "Structured ESG indicators extracted from report evidence.",
            "strict": True,
            "schema": LLM_STRUCTURED_OUTPUT_SCHEMA,
        }
    }


def extract_indicator_records_from_response(raw_text: str):
    parsed = extract_json_from_response(raw_text)
    if not parsed:
        return []

    if len(parsed) == 1 and isinstance(parsed[0], dict) and isinstance(parsed[0].get("indicators"), list):
        return parsed[0]["indicators"]

    return parsed

def add_standardized_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    mapped = [
        map_indicator_to_standard(
            row.get("indicator_name", ""),
            row.get("source_keyword", ""),
            row.get("evidence_text", ""),
        )
        for _, row in df.iterrows()
    ]
    standardized = pd.concat([df.reset_index(drop=True), pd.DataFrame(mapped).reset_index(drop=True)], axis=1)
    normalized = [
        normalize_unit_value(
            row.get("standard_name", ""),
            row.get("standard_metric_type", row.get("metric_type", "")),
            row.get("numeric_value", row.get("value")),
            row.get("unit", ""),
        )
        for _, row in standardized.iterrows()
    ]
    return pd.concat([standardized.reset_index(drop=True), pd.DataFrame(normalized).reset_index(drop=True)], axis=1)


def unit_is_expected(unit: str, expected_units: str) -> bool:
    if expected_units is None or str(expected_units).strip() in ["", "None", "none"]:
        return True
    if unit is None or str(unit).strip() in ["", "None", "none"]:
        return False
    unit_norm = normalize_for_matching(unit)
    expected = [normalize_for_matching(x) for x in str(expected_units).split(";") if x.strip()]
    return any(exp in unit_norm or unit_norm in exp for exp in expected)


def run_data_quality_checks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    temp = add_standardized_columns(df)
    issues = []
    duplicate_cols = [
        col for col in ["company_name", "year", "indicator_name", "value", "unit", "page", "evidence_text"]
        if col in temp.columns
    ]
    dup = temp.duplicated(subset=duplicate_cols, keep=False) if duplicate_cols else pd.Series(False, index=temp.index)
    dictionary_df = get_esg_dictionary_df()

    conflict_groups = {}
    conflict_cols = ["company_name", "year", "standard_name"]
    if all(col in temp.columns for col in conflict_cols) and "normalized_numeric_value" in temp.columns:
        comparable = temp[temp["standard_name"].notna() & temp["normalized_numeric_value"].notna()].copy()
        for group_key, group_df in comparable.groupby(conflict_cols, dropna=False):
            unique_values = sorted({round(float(value), 6) for value in group_df["normalized_numeric_value"].dropna()})
            if len(unique_values) > 1:
                conflict_groups[group_key] = unique_values

    for idx, row in temp.iterrows():
        base = {
            "row_index": idx,
            "company_name": row.get("company_name"),
            "year": row.get("year"),
            "indicator_name": row.get("indicator_name"),
            "standard_name": row.get("standard_name"),
        }
        value = row.get("numeric_value")

        if pd.isna(value):
            issues.append({**base, "severity": "warning", "issue_type": "missing_numeric_value", "issue_detail": "numeric_value is empty."})
        if not row.get("standard_name"):
            issues.append({**base, "severity": "warning", "issue_type": "unmapped_indicator", "issue_detail": "Indicator did not match the standard ESG dictionary."})
        if row.get("standard_name") and not unit_is_expected(row.get("unit"), row.get("expected_units")):
            issues.append({**base, "severity": "warning", "issue_type": "unexpected_unit", "issue_detail": f"Unit is not in expected list. unit={row.get('unit')}, expected={row.get('expected_units')}"})

        confidence = row.get("confidence")
        if pd.notna(confidence):
            try:
                confidence_value = float(confidence)
                if confidence_value < 0.6:
                    issues.append({**base, "severity": "warning", "issue_type": "low_confidence", "issue_detail": f"LLM confidence is low: {confidence_value:.2f}"})
            except Exception:
                issues.append({**base, "severity": "warning", "issue_type": "invalid_confidence", "issue_detail": f"Confidence is not numeric: {confidence}"})

        conversion_note = row.get("unit_conversion_note")
        if conversion_note:
            issues.append({
                **base,
                "severity": "info",
                "issue_type": "unit_conversion_applied",
                "issue_detail": (
                    f"Converted {row.get('numeric_value')} {row.get('unit')} to "
                    f"{row.get('normalized_numeric_value')} {row.get('standard_unit')} ({conversion_note})."
                ),
            })

        if row.get("standard_name") and pd.notna(value):
            matched = dictionary_df[dictionary_df["standard_name"] == row.get("standard_name")]
            if not matched.empty:
                min_value = matched.iloc[0].get("min_value")
                max_value = matched.iloc[0].get("max_value")
                try:
                    numeric_value = float(row.get("normalized_numeric_value", value))
                    if min_value is not None and pd.notna(min_value) and numeric_value < float(min_value):
                        issues.append({**base, "severity": "error", "issue_type": "value_below_min", "issue_detail": f"Value below minimum after normalization: {numeric_value} < {min_value}"})
                    if max_value is not None and pd.notna(max_value) and numeric_value > float(max_value):
                        issues.append({**base, "severity": "error", "issue_type": "value_above_max", "issue_detail": f"Value above maximum after normalization: {numeric_value} > {max_value}"})
                except Exception:
                    pass

        conflict_key = (row.get("company_name"), row.get("year"), row.get("standard_name"))
        if conflict_key in conflict_groups:
            issues.append({
                **base,
                "severity": "error",
                "issue_type": "conflicting_standard_value",
                "issue_detail": f"Same company-year-standard indicator has conflicting normalized values: {conflict_groups[conflict_key]}",
            })

        if dup.loc[idx]:
            issues.append({**base, "severity": "info", "issue_type": "possible_duplicate", "issue_detail": "Record may be duplicated."})

    return pd.DataFrame(issues)


def build_standardized_model_ready_dataset(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    temp = add_standardized_columns(df)
    temp = temp[temp["numeric_value"].notna() & temp["standard_name"].notna()]
    if "standard_metric_type" in temp.columns:
        temp = temp[temp["standard_metric_type"].isin(["actual_value", "ratio"])]
    if temp.empty:
        return pd.DataFrame()

    value_column = "normalized_numeric_value" if "normalized_numeric_value" in temp.columns else "numeric_value"
    model_df = temp.pivot_table(
        index=["company_name", "year"],
        columns="standard_name",
        values=value_column,
        aggfunc="first",
    ).reset_index()
    model_df.columns.name = None
    model_df["year"] = pd.to_numeric(model_df["year"], errors="coerce").astype("Int64")
    return model_df

def classify_metric_type(indicator_name: str, unit: str, value) -> str:
    name = str(indicator_name or "").lower()
    unit_text = str(unit or "").lower()

    if "hedef" in name and ("yil" in normalize_for_matching(unit_text) or "year" in unit_text):
        return "target_year"

    if "net sifir" in normalize_for_matching(name) or "net zero" in name:
        return "target_year"

    if "hedef" in name:
        return "target_value"

    if "oran" in name or "yuzde" in normalize_for_matching(unit_text) or "percent" in unit_text or "%" in unit_text:
        return "ratio"

    policy_terms = ["komite", "politika", "kurul", "sertifika", "program", "egitim", "toplanti"]
    normalized_name = normalize_for_matching(name)
    if any(term in normalized_name for term in policy_terms):
        return "policy_indicator"

    return "actual_value"