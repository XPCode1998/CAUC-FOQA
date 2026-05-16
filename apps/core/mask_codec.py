from __future__ import annotations

from typing import Iterable

from apps.core.models import QAR


def get_mask_fields() -> list[str]:
    return list(QAR.get_fields())


def get_mask_index_map() -> dict[str, int]:
    return {name: idx for idx, name in enumerate(get_mask_fields())}


def build_mask_list_from_instance(qar_obj: QAR, field_names: Iterable[str] | None = None) -> list[int]:
    fields = list(field_names) if field_names is not None else get_mask_fields()
    return [1 if getattr(qar_obj, field, None) is not None else 0 for field in fields]


def build_mask_list_from_row(row: dict, field_names: Iterable[str] | None = None) -> list[int]:
    fields = list(field_names) if field_names is not None else get_mask_fields()
    return [1 if row.get(field) is not None else 0 for field in fields]
