"""Base64 / key encoding utilities for Tandem element keys."""

import base64
import struct
from typing import List, Tuple

from .constants import (
    ELEMENT_FLAGS_SIZE,
    ELEMENT_ID_SIZE,
    ELEMENT_ID_WITH_FLAGS_SIZE,
    KEY_FLAGS_LOGICAL,
    KEY_FLAGS_PHYSICAL,
    MODEL_ID_SIZE,
    SYSTEM_ID_SIZE,
)


def _b64_prepare(text: str) -> str:
    """Convert web-safe base64 back to standard base64."""
    result = text.replace("-", "+").replace("_", "/")
    result += "=" * (len(result) % 4)
    return result


def _make_web_safe(text: str) -> str:
    """Convert standard base64 to web-safe base64."""
    return text.replace("+", "-").replace("/", "_").rstrip("=")


def from_short_key_array(text: str, use_full_keys: bool = False, is_logical: bool = False) -> List[str]:
    """Decode encoded local refs to a list of element keys."""
    bin_data = base64.b64decode(_b64_prepare(text))
    if use_full_keys:
        buff = bytearray(ELEMENT_ID_WITH_FLAGS_SIZE)
    else:
        buff = bytearray(ELEMENT_ID_SIZE)
    result = []
    offset = 0
    while offset < len(bin_data):
        if len(bin_data) - offset < ELEMENT_ID_SIZE:
            break
        if use_full_keys:
            flags_value = KEY_FLAGS_LOGICAL if is_logical else KEY_FLAGS_PHYSICAL
            struct.pack_into(">I", buff, 0, flags_value)
            buff[ELEMENT_FLAGS_SIZE:] = bin_data[offset : offset + ELEMENT_ID_SIZE]
        else:
            buff[0:] = bin_data[offset : offset + ELEMENT_ID_SIZE]
        result.append(_make_web_safe(base64.b64encode(buff).decode("utf-8")))
        offset += ELEMENT_ID_SIZE
    return result


def from_xref_key_array(text: str) -> List[Tuple[str, str]]:
    """Decode xref refs to list of (model_id, element_key) tuples."""
    if text is None:
        return []
    bin_data = base64.b64decode(_b64_prepare(text))
    chunk = MODEL_ID_SIZE + ELEMENT_ID_WITH_FLAGS_SIZE
    result = []
    offset = 0
    while offset < len(bin_data):
        if len(bin_data) - offset < chunk:
            break
        model_id = _make_web_safe(base64.b64encode(bin_data[offset : offset + MODEL_ID_SIZE]).decode("utf-8"))
        element_key = _make_web_safe(
            base64.b64encode(bin_data[offset + MODEL_ID_SIZE : offset + chunk]).decode("utf-8")
        )
        result.append((model_id, element_key))
        offset += chunk
    return result


def to_full_key(short_key: str, is_logical: bool = False) -> str:
    """Convert a 20-byte short key to a 24-byte full key with flags."""
    buff = base64.b64decode(_b64_prepare(short_key))
    full_key = bytearray(ELEMENT_ID_WITH_FLAGS_SIZE)
    flags_value = KEY_FLAGS_LOGICAL if is_logical else KEY_FLAGS_PHYSICAL
    struct.pack_into(">I", full_key, 0, flags_value)
    full_key[ELEMENT_FLAGS_SIZE:] = buff
    return _make_web_safe(base64.b64encode(full_key).decode("utf-8"))


def to_short_key(full_key: str) -> str:
    """Convert a 24-byte full key to a 20-byte short key."""
    buff = base64.b64decode(_b64_prepare(full_key))
    key = bytearray(ELEMENT_ID_SIZE)
    key[0:] = buff[ELEMENT_FLAGS_SIZE:]
    return _make_web_safe(base64.b64encode(key).decode("utf-8"))


def to_system_id(key: str) -> str:
    """Convert element key to system ID."""
    buff = base64.b64decode(_b64_prepare(key))
    id_val = (buff[-4] << 24) | (buff[-3] << 16) | (buff[-2] << 8) | buff[-1]
    res = bytearray(SYSTEM_ID_SIZE)
    offset = [0]
    length = _write_var_int(res, offset, id_val)
    tmp = bytearray(length)
    tmp[0:] = res[0:length]
    text = base64.b64encode(tmp).decode("utf-8").rstrip("=")
    return text


def _write_var_int(buff: bytearray, offset: list, value: int) -> int:
    start = offset[0]
    while True:
        byte = value & 0x7F
        value = (value >> 7) & 0xFFFFFFFF
        if value != 0:
            byte |= 0x80
        buff[offset[0]] = byte
        offset[0] += 1
        if not value:
            break
    return offset[0] - start
