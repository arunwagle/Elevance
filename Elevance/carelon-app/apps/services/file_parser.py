"""File parser service — reads structured data files into DataFrames."""

import logging
import pandas as pd
from models.file_template import FileProcessingTemplate

logger = logging.getLogger(__name__)


class FileParser:
    """Parses structured data files (CSV, Excel, TSV) based on processing template."""

    def parse(self, file_path: str, template: FileProcessingTemplate) -> pd.DataFrame:
        """Read file into DataFrame based on template configuration."""
        logger.info(f"Parsing file: {file_path} (type={template.file_type})")

        if template.file_type in ('csv', 'tsv'):
            return self._parse_delimited(file_path, template)
        elif template.file_type in ('xlsx', 'xls'):
            return self._parse_excel(file_path, template)
        else:
            raise ValueError(f"Unsupported file type: {template.file_type}")

    def _parse_delimited(self, file_path: str, template: FileProcessingTemplate) -> pd.DataFrame:
        """Parse a delimited file (CSV/TSV)."""
        df = pd.read_csv(
            file_path,
            delimiter=template.delimiter,
            header=0 if template.has_header else None,
            dtype=str,  # Keep all as string for tokenization
        )
        if not template.has_header:
            df.columns = [f'col_{i}' for i in range(len(df.columns))]

        logger.info(f"Parsed delimited file: {len(df)} rows, {len(df.columns)} columns")
        return df

    def _parse_excel(self, file_path: str, template: FileProcessingTemplate) -> pd.DataFrame:
        """Parse an Excel file."""
        df = pd.read_excel(
            file_path,
            header=0 if template.has_header else None,
            dtype=str,
            sheet_name=template.sheet_name or 0,
        )
        if not template.has_header:
            df.columns = [f'col_{i}' for i in range(len(df.columns))]

        logger.info(f"Parsed Excel file: {len(df)} rows, {len(df.columns)} columns")
        return df
