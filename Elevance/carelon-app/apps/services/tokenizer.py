"""Tokenization orchestrator — coordinates the full pipeline."""

import json
import os
import logging
from typing import Dict, Optional
from services.file_parser import FileParser
from services.template_parser import TemplateParser
from services.protegrity_client import ProtegrityClient
from services.volume_service import VolumeService

logger = logging.getLogger(__name__)


class TokenizationOrchestrator:
    """Orchestrates: parse templates → read file → tokenize → write to Volume."""

    def __init__(self):
        self.file_parser = FileParser()
        self.template_parser = TemplateParser()
        self.protegrity_client = ProtegrityClient()
        self.volume_service = VolumeService()

    def process(self, data_file_path: str, processing_template_path: str,
                protegrity_template_path: str, volume_path: str = None,
                user_token: str = '', metadata: Optional[Dict] = None) -> Dict:
        """Execute the full tokenization pipeline for a single file.

        Args:
            data_file_path: Path to the uploaded data file (temp)
            processing_template_path: Path to the processing template JSON
            protegrity_template_path: Path to the Protegrity template JSON
            volume_path: Target Volume path for output
            user_token: User's X-Forwarded-Access-Token for Volume writes
            metadata: Upload form metadata (entity_type, domain, etc.)

        Returns: {output_path, rows_processed, columns_tokenized, metadata_path}
        """
        # Step 1: Parse templates
        proc_template = self.template_parser.parse_processing_template(processing_template_path)
        prot_template = self.template_parser.parse_protegrity_template(protegrity_template_path)

        # Step 2: Cross-validate templates
        errors = self.template_parser.validate_templates(proc_template, prot_template)
        if errors:
            raise ValueError(f"Template validation failed: {'; '.join(errors)}")

        # Step 3: Read data file into DataFrame
        df = self.file_parser.parse(data_file_path, proc_template)

        # Step 4: Validate PII columns exist in the data
        for col in proc_template.pii_columns:
            if col not in df.columns:
                raise ValueError(
                    f"PII column '{col}' not found in data file. "
                    f"Available columns: {list(df.columns)}"
                )

        # Step 5: Tokenize each PII column
        columns_tokenized = []
        for col in proc_template.pii_columns:
            values = df[col].fillna('').astype(str).tolist()
            tokenized = self.protegrity_client.tokenize_batch(prot_template, col, values)
            df[col] = tokenized
            columns_tokenized.append(col)

        # Step 6: Write tokenized file to Volume
        output_path = self.volume_service.write_tokenized_file(
            df=df,
            original_filename=data_file_path.split('/')[-1],
            file_type=proc_template.file_type,
            delimiter=proc_template.delimiter,
            volume_path=volume_path,
            user_token=user_token,
        )

        # Step 7: Write metadata sidecar JSON alongside the tokenized file
        metadata_path = None
        if metadata:
            metadata_path = self._write_metadata(
                output_path=output_path,
                metadata=metadata,
                rows_processed=len(df),
                columns_tokenized=columns_tokenized,
                user_token=user_token,
            )

        logger.info(f"Tokenization complete: {output_path} ({len(df)} rows, "
                    f"{len(columns_tokenized)} columns tokenized)")
        return {
            'output_path': output_path,
            'rows_processed': len(df),
            'columns_tokenized': columns_tokenized,
            'metadata_path': metadata_path,
        }

    def _write_metadata(self, output_path: str, metadata: Dict,
                        rows_processed: int, columns_tokenized: list,
                        user_token: str = '') -> Optional[str]:
        """Write a JSON metadata sidecar file alongside the tokenized output."""
        try:
            import io
            from datetime import datetime

            meta_content = {
                **metadata,
                'output_file': output_path,
                'rows_processed': rows_processed,
                'columns_tokenized': columns_tokenized,
                'processed_at': datetime.now().isoformat(),
            }

            # Derive metadata filename from output path
            meta_path = output_path.rsplit('.', 1)[0] + '_metadata.json'
            meta_bytes = json.dumps(meta_content, indent=2).encode('utf-8')

            import requests as http_req
            if not user_token or not user_token.strip():
                logger.warning("No user token for metadata write — skipping")
                return None
            host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
            if host and not host.startswith('http'):
                host = f'https://{host}'
            api_path = meta_path.lstrip('/')
            url = f"{host}/api/2.0/fs/files/{api_path}"
            resp = http_req.put(
                url,
                headers={'Authorization': f'Bearer {user_token}', 'Content-Type': 'application/octet-stream', 'Overwrite': 'true'},
                data=meta_bytes,
                timeout=30,
            )
            if resp.status_code not in (200, 201, 204):
                raise Exception(f"Metadata upload failed (HTTP {resp.status_code}): {resp.text[:200]}")
            logger.info(f"Metadata written: {meta_path}")
            return meta_path
        except Exception as e:
            logger.warning(f"Failed to write metadata sidecar: {e}")
            return None
