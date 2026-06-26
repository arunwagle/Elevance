"""FileProcessingTemplate model — defines how to read a data file."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileProcessingTemplate:
    """Configuration for reading a structured data file.

    Parsed from the user-uploaded processing template JSON.
    """

    file_type: str                      # csv, tsv, xlsx, xls
    is_delimited: bool                  # Whether file uses a delimiter
    delimiter: str = ','                # Delimiter character
    has_header: bool = True             # Whether first row is headers
    sheet_name: Optional[str] = None    # For Excel — which sheet
    pii_columns: List[str] = field(default_factory=list)  # Columns to tokenize

    def validate(self) -> List[str]:
        """Validate template configuration. Returns list of error messages."""
        errors = []

        valid_types = {'csv', 'tsv', 'xlsx', 'xls'}
        if self.file_type not in valid_types:
            errors.append(f"file_type must be one of {valid_types}, got '{self.file_type}'")

        if self.is_delimited and not self.delimiter:
            errors.append("delimiter is required when is_delimited is true")

        if not self.pii_columns:
            errors.append("pii_columns must be a non-empty list")

        return errors
