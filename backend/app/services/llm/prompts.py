"""Shared prompt builder for structured extraction."""


def build_extraction_prompt(text: str, schema_fields: list[dict]) -> str:
    """Build a system+user prompt pair for structured extraction.

    Returns a single formatted prompt string.  The prompt asks the model
    to return both extracted values and per-field confidence scores so
    downstream validation can route low-confidence fields to review.
    """
    field_descriptions = []
    for f in schema_fields:
        req = "required" if f.get("required", True) else "optional"
        field_descriptions.append(
            f'  - "{f["name"]}" ({f.get("field_type", "string")}, {req}): {f.get("description", "")}'
        )
    fields_block = "\n".join(field_descriptions)

    return (
        "You are a document data extraction assistant. "
        "Extract structured data from the document text below.\n\n"
        "RULES:\n"
        "1. Return ONLY valid JSON — no markdown fences, no commentary.\n"
        "2. Use the exact field names specified.\n"
        "3. If a field value is not found in the text, use null.\n"
        "4. For list fields, return a JSON array.\n"
        "5. For number fields, return a numeric value (not a string).\n"
        "6. For date fields, return ISO 8601 format (YYYY-MM-DD).\n"
        '7. Include a "_confidence" object mapping each field name to a '
        "confidence score between 0.0 and 1.0 indicating how certain you "
        "are about the extracted value.\n\n"
        "EXAMPLE OUTPUT FORMAT:\n"
        '{\n  "vendor": "Acme Corp",\n  "total": 1500.00,\n'
        '  "_confidence": {"vendor": 0.95, "total": 0.80}\n}\n\n'
        f"FIELDS TO EXTRACT:\n{fields_block}\n\n"
        f"DOCUMENT TEXT:\n{text}"
    )
