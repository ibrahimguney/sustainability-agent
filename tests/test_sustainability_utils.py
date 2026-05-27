import unittest

from sustainability_utils import (
    add_standardized_columns,
    build_standardized_model_ready_dataset,
    classify_metric_type,
    extract_indicator_records_from_response,
    extract_json_from_response,
    filter_tabs_for_focus,
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


class SustainabilityUtilsTest(unittest.TestCase):
    def test_normalize_number_handles_turkish_decimal_format(self):
        self.assertEqual(normalize_number("1.234,56"), 1234.56)
        self.assertEqual(normalize_number("45,7%"), 45.7)
        self.assertIsNone(normalize_number("yok"))

    def test_extract_json_from_response_accepts_code_fences_and_objects(self):
        self.assertEqual(extract_json_from_response('```json\n[{"a": 1}]\n```'), [{"a": 1}])
        self.assertEqual(extract_json_from_response('prefix {"a": 1} suffix'), [{"a": 1}])
        self.assertEqual(extract_json_from_response("not json"), [])

    def test_parse_company_year_from_filename(self):
        self.assertEqual(parse_company_year_from_filename("THY-2024-surdurulebilirlik.pdf"), ("THY", "2024"))
        self.assertEqual(parse_company_year_from_filename("Akbank_2023_annual_report.pdf"), ("Akbank", "2023"))

    def test_dictionary_matching_normalizes_turkish_characters(self):
        self.assertEqual(normalize_for_matching("Sürdürülebilirlik Komitesi"), "surdurulebilirlik komitesi")
        match = map_indicator_to_standard("Yenilenebilir enerji oranı", "", "")
        self.assertEqual(match["standard_name"], "renewable_energy_ratio")
        self.assertGreater(match["dictionary_match_score"], 0)

    def test_get_visible_tabs_for_role_limits_non_admin_roles(self):
        all_tabs = ["all", "edit", "admin"]
        user_tabs = ["all", "edit"]
        viewer_tabs = ["all"]

        self.assertEqual(get_visible_tabs_for_role("admin", all_tabs, user_tabs, viewer_tabs), all_tabs)
        self.assertEqual(get_visible_tabs_for_role("user", all_tabs, user_tabs, viewer_tabs), user_tabs)
        self.assertEqual(get_visible_tabs_for_role("viewer", all_tabs, user_tabs, viewer_tabs), viewer_tabs)
        self.assertEqual(get_visible_tabs_for_role("unknown", all_tabs, user_tabs, viewer_tabs), viewer_tabs)
    def test_normalize_extracted_indicator_records_fills_defaults_and_coerces_values(self):
        records = [
            {
                "indicator_name": "Scope 1",
                "value": "1.234,5 ton",
                "page": "7",
                "confidence": "85",
            }
        ]

        df = normalize_extracted_indicator_records(records, "ACME", "2024")

        self.assertEqual(df.loc[0, "company_name"], "ACME")
        self.assertEqual(df.loc[0, "year"], "2024")
        self.assertEqual(df.loc[0, "numeric_value"], 1234.5)
        self.assertEqual(df.loc[0, "page"], 7)
        self.assertEqual(df.loc[0, "confidence"], 0.85)
        self.assertIn("notes", df.columns)

    def test_normalize_extracted_indicator_records_prefers_numeric_value_when_present(self):
        records = [{"value": "not numeric", "numeric_value": "42", "confidence": "1.2"}]
        df = normalize_extracted_indicator_records(records)

        self.assertEqual(df.loc[0, "numeric_value"], 42.0)
        self.assertEqual(df.loc[0, "confidence"], 1.0)
    def test_normalize_unit_value_converts_common_units(self):
        emission = normalize_unit_value("scope1_emissions", "actual_value", "2500", "kg CO2e")
        self.assertEqual(emission["standard_unit"], "ton CO2e")
        self.assertEqual(emission["normalized_numeric_value"], 2.5)
        self.assertEqual(emission["unit_conversion_note"], "kg_to_ton")

        energy = normalize_unit_value("energy_consumption", "actual_value", "1200", "kWh")
        self.assertEqual(energy["standard_unit"], "MWh")
        self.assertEqual(energy["normalized_numeric_value"], 1.2)

    def test_normalize_unit_value_handles_ratio_decimals(self):
        ratio = normalize_unit_value("female_employee_ratio", "ratio", "0.42", "")
        self.assertEqual(ratio["standard_unit"], "%")
        self.assertEqual(ratio["normalized_numeric_value"], 42.0)
        self.assertEqual(ratio["unit_conversion_note"], "decimal_ratio_to_percent")
    def test_filter_tabs_for_focus_preserves_visible_order_from_focus_group(self):
        visible_tabs = ["A", "B", "C"]
        focus_tabs = ["C", "A", "X"]

        self.assertEqual(filter_tabs_for_focus(visible_tabs, focus_tabs), ["C", "A"])
    def test_structured_output_format_uses_json_schema(self):
        text_format = get_llm_response_text_format()
        schema_format = text_format["format"]

        self.assertEqual(schema_format["type"], "json_schema")
        self.assertTrue(schema_format["strict"])
        self.assertIn("indicators", schema_format["schema"]["properties"])

    def test_extract_indicator_records_from_structured_response(self):
        raw = '{"indicators": [{"indicator_name": "Scope 1", "value": "12"}]}'
        records = extract_indicator_records_from_response(raw)

        self.assertEqual(records, [{"indicator_name": "Scope 1", "value": "12"}])
    def test_standardized_columns_and_model_panel_live_in_utils(self):
        import pandas as pd

        source = pd.DataFrame([
            {
                "company_name": "ACME",
                "year": "2024",
                "indicator_name": "Scope 1 emissions",
                "numeric_value": 2500,
                "unit": "kg CO2e",
                "source_keyword": "scope 1",
                "evidence_text": "Scope 1 emissions were 2500 kg CO2e.",
            }
        ])

        standardized = add_standardized_columns(source)
        self.assertEqual(standardized.loc[0, "standard_name"], "scope1_emissions")
        self.assertEqual(standardized.loc[0, "normalized_numeric_value"], 2.5)

        panel = build_standardized_model_ready_dataset(source)
        self.assertEqual(panel.loc[0, "scope1_emissions"], 2.5)

    def test_run_data_quality_checks_flags_missing_numeric_values(self):
        import pandas as pd

        source = pd.DataFrame([{"company_name": "ACME", "year": "2024", "indicator_name": "Unknown metric"}])
        issues = run_data_quality_checks(source)

        self.assertIn("missing_numeric_value", set(issues["issue_type"]))
        self.assertIn("unmapped_indicator", set(issues["issue_type"]))
    def test_classify_metric_type_identifies_common_types(self):
        self.assertEqual(classify_metric_type("Net sıfır hedefi", "yıl", "2050"), "target_year")
        self.assertEqual(classify_metric_type("Kadın çalışan oranı", "%", "42"), "ratio")
        self.assertEqual(classify_metric_type("Sürdürülebilirlik komitesi", "", "var"), "policy_indicator")
        self.assertEqual(classify_metric_type("Enerji tüketimi", "MWh", "120"), "actual_value")
    def test_run_data_quality_checks_flags_low_confidence_conversion_and_conflicts(self):
        import pandas as pd

        source = pd.DataFrame([
            {
                "company_name": "ACME",
                "year": "2024",
                "indicator_name": "Scope 1 emissions",
                "numeric_value": 2500,
                "unit": "kg CO2e",
                "source_keyword": "scope 1",
                "evidence_text": "Scope 1 emissions were 2500 kg CO2e.",
                "confidence": 0.4,
            },
            {
                "company_name": "ACME",
                "year": "2024",
                "indicator_name": "Scope 1 emissions",
                "numeric_value": 3,
                "unit": "ton CO2e",
                "source_keyword": "scope 1",
                "evidence_text": "Scope 1 emissions were 3 ton CO2e.",
                "confidence": 0.9,
            },
        ])

        issues = run_data_quality_checks(source)
        issue_types = set(issues["issue_type"])

        self.assertIn("low_confidence", issue_types)
        self.assertIn("unit_conversion_applied", issue_types)
        self.assertIn("conflicting_standard_value", issue_types)

if __name__ == "__main__":
    unittest.main()