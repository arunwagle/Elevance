"""Template parser service — parses processing and Protegrity template files."""

import json
import logging
from typing import List
from models.file_template import FileProcessingTemplate
from models.protegrity_template import ProtegrityTemplate, DataElement

logger = logging.getLogger(__name__)


class TemplateParser:
    """Parses and validates both template types from JSON files."""

    def parse_processing_template(self, template_path: str) -> FileProcessingTemplate:
        """Parse processing template JSON into FileProcessingTemplate."""
        with open(template_path, 'r') as f:
            config = json.load(f)

        template = FileProcessingTemplate(
            file_type=config.get('file_type', ''),
            is_delimited=config.get('is_delimited', True),
            delimiter=config.get('delimiter', ','),
            has_header=config.get('has_header', True),
            sheet_name=config.get('sheet_name'),
            pii_columns=config.get('pii_columns', []),
        )

        errors = template.validate()
        if errors:
            raise ValueError(f"Invalid processing template: {'; '.join(errors)}")

        logger.info(f"Parsed processing template: type={template.file_type}, pii_cols={template.pii_columns}")
        return template

    def parse_protegrity_template(self, template_path: str) -> ProtegrityTemplate:
        """Parse Protegrity contract template JSON into ProtegrityTemplate."""
        with open(template_path, 'r') as f:
            config = json.load(f)

        data_elements = [
            DataElement(
                name=elem.get('name', ''),
                data_type=elem.get('dataType', 'STRING'),
                length=elem.get('length', 0),
            )
            for elem in config.get('dataElements', [])
        ]

        template = ProtegrityTemplate(
            session_id=config.get('sessionId'),
            data_elements=data_elements,
            tokenize_functions=config.get('tokenizeFunctions', {}),
        )

        errors = template.validate()
        if errors:
            raise ValueError(f"Invalid Protegrity template: {'; '.join(errors)}")

        logger.info(f"Parsed Protegrity template: session={template.session_id}, "
                    f"functions={template.tokenize_functions}")
        return template

    def validate_templates(self, proc: FileProcessingTemplate, prot: ProtegrityTemplate) -> List[str]:
        """Cross-validate both templates. Returns list of errors."""
        errors = []

        # Every PII column must have a tokenize function defined
        for col in proc.pii_columns:
            if col not in prot.tokenize_functions:
                errors.append(
                    f"PII column '{col}' has no matching entry in Protegrity tokenizeFunctions"
                )

        return errors
