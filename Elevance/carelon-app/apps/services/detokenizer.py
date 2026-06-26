"""Detokenization orchestrator — reverses tokenization, streams output."""

import io
import json
import logging
import pandas as pd
from typing import Tuple
from services.template_parser import TemplateParser
from services.protegrity_client import ProtegrityClient
from services.volume_service import VolumeService

logger = logging.getLogger(__name__)


class DetokenizationOrchestrator:
    """Orchestrates detokenization: read file → reverse tokenize → stream."""

    def __init__(self):
        self.template_parser = TemplateParser()
        self.protegrity_client = ProtegrityClient()
        self.volume_service = VolumeService()

    def detokenize(self, file_path: str, prot_template_file) -> Tuple[io.BytesIO, str]:
        """Detokenize a file and return as stream (never stored).

        Args:
            file_path: Path to the tokenized file in Volume.
            prot_template_file: Uploaded Protegrity template file object.

        Returns: (BytesIO stream, filename)
        """
        import tempfile
        import os

        # Save template to temp file for parsing
        tmp_template = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        prot_template_file.save(tmp_template.name)

        try:
            # Parse Protegrity template
            prot_template = self.template_parser.parse_protegrity_template(tmp_template.name)

            # Download file from Volume
            file_buffer, filename = self.volume_service.download_file(file_path)

            # Detect format and read into DataFrame
            ext = filename.rsplit('.', 1)[-1].lower()
            if ext in ('csv', 'tsv'):
                sep = '\t' if ext == 'tsv' else ','
                df = pd.read_csv(file_buffer, dtype=str, sep=sep)
            elif ext in ('xlsx', 'xls'):
                df = pd.read_excel(file_buffer, dtype=str)
            else:
                raise ValueError(f"Cannot detokenize file type: {ext}")

            # Detokenize each column defined in the template
            for col in prot_template.tokenize_functions:
                if col in df.columns:
                    values = df[col].fillna('').astype(str).tolist()
                    detokenized = self.protegrity_client.detokenize_batch(prot_template, col, values)
                    df[col] = detokenized

            # Convert back to bytes (stream, never stored)
            output_buffer = io.BytesIO()
            if ext in ('csv', 'tsv'):
                sep = '\t' if ext == 'tsv' else ','
                df.to_csv(output_buffer, index=False, sep=sep)
            else:
                df.to_excel(output_buffer, index=False, engine='openpyxl')
            output_buffer.seek(0)

            logger.info(f"Detokenization complete for {filename}")
            return output_buffer, filename

        finally:
            os.unlink(tmp_template.name)
