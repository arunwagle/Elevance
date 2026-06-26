"""Protegrity REST API client — synthetic implementation.

In production, replace _synthetic_tokenize with real HTTP calls to
Protegrity Data Security Gateway.
"""

import hashlib
import logging
from typing import List
from models.protegrity_template import ProtegrityTemplate

logger = logging.getLogger(__name__)


class ProtegrityClient:
    """Tokenize/detokenize values using Protegrity functions (synthetic)."""

    def tokenize_batch(self, template: ProtegrityTemplate,
                       column_name: str, values: List[str]) -> List[str]:
        """Tokenize a batch of values for a column."""
        function_name = template.get_function_for_column(column_name)
        logger.info(f"Tokenizing column '{column_name}' with function '{function_name}' "
                    f"({len(values)} values)")

        return [self._synthetic_tokenize(v, function_name) for v in values]

    def detokenize_batch(self, template: ProtegrityTemplate,
                         column_name: str, values: List[str]) -> List[str]:
        """Detokenize a batch of values (reverse). Some functions are irreversible."""
        function_name = template.get_function_for_column(column_name)
        return [self._synthetic_detokenize(v, function_name) for v in values]

    # --- Synthetic Implementations ---

    def _synthetic_tokenize(self, value: str, function_name: str) -> str:
        """Simulate tokenization with deterministic transformations."""
        if not value or value.strip() == '':
            return value

        if function_name == 'FPE_ASCII':
            return self._fpe_encrypt(value)
        elif function_name == 'HASH_SHA256':
            return hashlib.sha256(value.encode()).hexdigest()[:len(value)]
        elif function_name == 'MASK':
            if len(value) > 2:
                return value[0] + '*' * (len(value) - 2) + value[-1]
            return '**'
        elif function_name == 'TOKENIZE_NUMERIC':
            return ''.join(str((int(c) + 5) % 10) if c.isdigit() else c for c in value)
        else:  # DEFAULT_TOKENIZE
            hash_val = hashlib.md5(f"{value}{function_name}".encode()).hexdigest()
            return f"TOK_{hash_val[:12]}"

    def _synthetic_detokenize(self, value: str, function_name: str) -> str:
        """Reverse synthetic tokenization where possible."""
        if not value or value.strip() == '':
            return value

        if function_name == 'FPE_ASCII':
            return self._fpe_decrypt(value)
        elif function_name == 'TOKENIZE_NUMERIC':
            return ''.join(str((int(c) - 5) % 10) if c.isdigit() else c for c in value)
        elif function_name in ('HASH_SHA256', 'MASK', 'DEFAULT_TOKENIZE'):
            return f"[IRREVERSIBLE:{function_name}]"
        return value

    def _fpe_encrypt(self, value: str) -> str:
        """Format-preserving encryption simulation."""
        result = []
        for i, c in enumerate(value):
            offset = (i + 3) % 10
            if c.isdigit():
                result.append(str((int(c) + offset) % 10))
            elif c.isalpha():
                base = ord('A') if c.isupper() else ord('a')
                result.append(chr(base + (ord(c) - base + offset) % 26))
            else:
                result.append(c)
        return ''.join(result)

    def _fpe_decrypt(self, value: str) -> str:
        """Reverse FPE simulation."""
        result = []
        for i, c in enumerate(value):
            offset = (i + 3) % 10
            if c.isdigit():
                result.append(str((int(c) - offset) % 10))
            elif c.isalpha():
                base = ord('A') if c.isupper() else ord('a')
                result.append(chr(base + (ord(c) - base - offset) % 26))
            else:
                result.append(c)
        return ''.join(result)
