"""ProtegrityTemplate model — defines tokenization functions per column.

Follows the Protegrity REST API fixed-pattern contract format.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


SUPPORTED_FUNCTIONS = {
    'FPE_ASCII',
    'HASH_SHA256',
    'MASK',
    'TOKENIZE_NUMERIC',
    'DEFAULT_TOKENIZE',
}

SUPPORTED_DATA_TYPES = {'STRING', 'NUMERIC', 'DATE'}


@dataclass
class DataElement:
    """A single data element definition in the Protegrity contract."""

    name: str
    data_type: str
    length: int


@dataclass
class ProtegrityTemplate:
    """Protegrity contract template mapping columns to tokenization functions.

    Parsed from the user-uploaded Protegrity template JSON.
    """

    session_id: Optional[str] = None
    data_elements: List[DataElement] = field(default_factory=list)
    tokenize_functions: Dict[str, str] = field(default_factory=dict)

    def get_function_for_column(self, column_name: str) -> str:
        """Get the Protegrity tokenization function for a given column."""
        return self.tokenize_functions.get(column_name, 'DEFAULT_TOKENIZE')

    def validate(self) -> List[str]:
        """Validate template. Returns list of error messages."""
        errors = []

        if not self.data_elements:
            errors.append("dataElements must be a non-empty list")

        if not self.tokenize_functions:
            errors.append("tokenizeFunctions must be a non-empty mapping")

        # Validate data types
        for elem in self.data_elements:
            if elem.data_type not in SUPPORTED_DATA_TYPES:
                errors.append(
                    f"dataElement '{elem.name}' has invalid dataType '{elem.data_type}'. "
                    f"Must be one of {SUPPORTED_DATA_TYPES}"
                )

        # Validate function names
        for col, func in self.tokenize_functions.items():
            if func not in SUPPORTED_FUNCTIONS:
                errors.append(
                    f"Column '{col}' has unsupported function '{func}'. "
                    f"Must be one of {SUPPORTED_FUNCTIONS}"
                )

        # Validate every tokenize column has a data element
        element_names = {e.name for e in self.data_elements}
        for col in self.tokenize_functions:
            if col not in element_names:
                errors.append(
                    f"Column '{col}' in tokenizeFunctions has no matching dataElement"
                )

        return errors
