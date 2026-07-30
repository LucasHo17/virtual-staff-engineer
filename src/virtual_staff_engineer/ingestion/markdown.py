import hashlib
import re


RULE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_-]*-\d+)\b", re.IGNORECASE)


def compute_checksum(file_path):
    """Generate a SHA-256 hash for immutable playbook version identity."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as playbook_file:
        for chunk in iter(lambda: playbook_file.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def derive_rule_key(section):
    """Return an explicit rule identifier or a stable heading slug."""
    rule_match = RULE_KEY_PATTERN.search(section)
    if rule_match:
        return rule_match.group(1).upper()

    normalized_section = re.sub(r"[^A-Z0-9]+", "-", section.upper()).strip("-")
    return normalized_section[:100] or "GENERAL"


def parse_markdown(file_path):
    """Split a Markdown playbook into non-empty H2 sections."""
    chunks = []
    current_section = "General"
    current_content = []

    with open(file_path, "r", encoding="utf-8") as playbook_file:
        for line in playbook_file:
            if line.startswith("## "):
                text_content = "".join(current_content).strip()
                if text_content:
                    chunks.append((current_section, text_content))
                current_content = []
                current_section = line.removeprefix("## ").strip()
            elif not line.startswith("# "):
                current_content.append(line)

    text_content = "".join(current_content).strip()
    if text_content:
        chunks.append((current_section, text_content))

    return chunks
