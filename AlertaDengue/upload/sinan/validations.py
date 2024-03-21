import os
from pathlib import Path
from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from upload.sinan.utils import EXPECTED_FIELDS


def validate_file_exists(file_path: str) -> None:
    if not os.path.exists(file_path):
        raise ValidationError(_(f'File {file_path} not found'))


def validade_file_type(file_name: str) -> None:
    file_path = Path(file_name)

    if file_path.suffix.lower() not in [".csv", ".dbf"]:
        raise ValidationError(_(f"Unknown file suffix {file_path.suffix}"))


def validate_residue_file_exists(file_path: str) -> None:
    if file_path:
        if not os.path.exists(file_path):
            raise ValidationError(_(f'File {file_path} not found'))


def validate_residue_file_name(file_path: str) -> None:
    if file_path:
        fpath = Path(file_path)

        if not fpath.name.startswith("RESIDUE_"):
            raise ValidationError(_(
                f"Residue file name {fpath.name} doesn't start with RESIDUE_"
            ))


def validade_year(year: int) -> None:
    if year > datetime.now().year:
        raise ValidationError(_(f"Invalid year {year}"))

    if year < 1970:
        raise ValidationError(_(f"Invalid year {year}"))


def validate_fields(columns: list[str]) -> None:
    if not all([c in EXPECTED_FIELDS.values() for c in columns]):
        raise ValidationError(
            "Required field(s): "
            f"{list(set(EXPECTED_FIELDS.values()).difference(set(columns)))} "
            "not found in data file"
        )
