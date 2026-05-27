import io
import re
from typing import Dict, List

import fitz
import pandas as pd
import streamlit as st


def clean_text(text: str) -> str:
    text = str(text or "").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_into_sentences(text: str) -> List[str]:
    text = clean_text(text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) > 20]


@st.cache_data(show_spinner=False, ttl=3600)
def extract_pdf_text_by_page_from_bytes(pdf_bytes: bytes) -> List[Dict]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text("text")
        pages.append(
            {
                "page": page_index + 1,
                "text": text,
                "clean_text": clean_text(text),
            }
        )

    doc.close()
    return pages


def extract_pdf_text_by_page(uploaded_file) -> List[Dict]:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    pdf_bytes = uploaded_file.read()
    return extract_pdf_text_by_page_from_bytes(pdf_bytes)


def clear_pdf_text_cache():
    clear_cache = getattr(extract_pdf_text_by_page_from_bytes, "clear", None)
    if clear_cache:
        clear_cache()


def search_keywords_in_pdf_pages(
    pages: List[Dict],
    keywords: List[str],
    context_sentences: int = 1,
) -> pd.DataFrame:
    rows = []

    for page_item in pages:
        page_no = page_item["page"]
        page_text = page_item["clean_text"]
        sentences = split_into_sentences(page_text)

        for keyword in keywords:
            keyword_clean = keyword.strip()
            if not keyword_clean:
                continue

            pattern = re.compile(re.escape(keyword_clean), re.IGNORECASE)
            if not pattern.search(page_text):
                continue

            matched_sentences = []
            for idx, sentence in enumerate(sentences):
                if pattern.search(sentence):
                    start_idx = max(0, idx - context_sentences)
                    end_idx = min(len(sentences), idx + context_sentences + 1)
                    matched_sentences.append(" ".join(sentences[start_idx:end_idx]))

            if not matched_sentences:
                matched_sentences = [page_text[:1000]]

            for evidence in matched_sentences:
                rows.append(
                    {
                        "page": page_no,
                        "keyword": keyword_clean,
                        "evidence_text": evidence[:2000],
                        "evidence_length": len(evidence),
                    }
                )

    result_df = pd.DataFrame(rows)
    if result_df.empty:
        return result_df

    result_df = result_df.drop_duplicates(
        subset=["page", "keyword", "evidence_text"]
    ).sort_values(["page", "keyword"])
    return result_df.reset_index(drop=True)


def make_pdf_scan_excel_file(result_df: pd.DataFrame, summary_df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        result_df.to_excel(writer, index=False, sheet_name="keyword_evidence")
        summary_df.to_excel(writer, index=False, sheet_name="keyword_summary")
    return output.getvalue()