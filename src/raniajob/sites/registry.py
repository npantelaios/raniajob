from __future__ import annotations

from typing import Callable, Dict

from .generic import parse_generic_site


PARSERS: Dict[str, Callable] = {
    "generic": parse_generic_site,
}


def get_parser(site_type: str) -> Callable:
    if site_type not in PARSERS:
        raise ValueError(f"Unsupported site type: {site_type}")
    return PARSERS[site_type]
