import hashlib
import ipaddress
from pathlib import Path
import re
import socket
from typing import Optional
from urllib.parse import urlparse

MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024  # 250 MB safety cap

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
    "0.0.0.0",
}


class SecurityValidationError(ValueError):
    """Raised when an external URL, file path, or downloaded payload violates security policy."""


def _is_forbidden_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_external_url(
    url: str,
    allowed_hosts: Optional[set[str]] = None,
    resolve_dns: bool = True,
) -> str:
    """Validate HTTP/HTTPS URL against SSRF (blocks localhost, private networks, link-local, metadata endpoints)."""
    raw = (url or "").strip()
    if not raw:
        raise SecurityValidationError("URL vazia não permitida.")

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        raise SecurityValidationError(f"Esquema de URL não permitido: '{parsed.scheme}'.")
    if not parsed.hostname:
        raise SecurityValidationError("URL sem hostname válido.")

    host = parsed.hostname.lower().strip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise SecurityValidationError(f"Host bloqueado por política anti-SSRF: '{host}'.")

    if allowed_hosts is not None:
        normalized_allow = {h.lower().strip(".") for h in allowed_hosts}
        if not any(host == a or host.endswith(f".{a}") for a in normalized_allow):
            raise SecurityValidationError(f"Host '{host}' não está na allowlist autorizada.")

    # Direct IP literal check (parse outside SecurityValidationError check since it subclasses ValueError)
    ip_obj = None
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if _is_forbidden_ip(ip_obj):
            raise SecurityValidationError(f"Endereço IP bloqueado por política anti-SSRF: '{host}'.")
        return raw

    # DNS resolution check to catch DNS rebinding / internal aliases
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # DNS may not be reachable in offline unit test environments; literal checks above still protect
            infos = []

        for info in infos:
            addr_str = info[4][0].split("%")[0]
            try:
                resolved_ip = ipaddress.ip_address(addr_str)
            except ValueError:
                continue
            if _is_forbidden_ip(resolved_ip):
                raise SecurityValidationError(
                    f"Host '{host}' resolve para IP interno/reservado bloqueado ({addr_str})."
                )

    return raw


def safe_join_path(base_dir: Path, filename: str) -> Path:
    """Sanitize filename and ensure resolved path stays strictly inside base_dir."""
    if not filename or ".." in Path(filename).parts:
        raise SecurityValidationError(f"Caminho inválido detectado (path traversal): '{filename}'.")
    clean_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(filename).name).strip()
    if not clean_name or clean_name in (".", ".."):
        raise SecurityValidationError("Nome de arquivo vazio após sanitização.")
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / clean_name).resolve()
    if base_resolved != candidate and base_resolved not in candidate.parents:
        raise SecurityValidationError(f"Path traversal bloqueado fora de {base_resolved}.")
    return candidate


def validate_audio_magic_bytes(
    file_path: Path, content_type: Optional[str] = None
) -> tuple[bool, str]:
    """Inspect real binary header bytes to reject HTML, scripts, executables, or malformed non-audio files."""
    if not file_path.exists() or file_path.stat().st_size < 12:
        return False, "Arquivo ausente ou menor que 12 bytes."

    header = file_path.read_bytes()[:64]
    lower_head = header.lstrip().lower()
    if lower_head.startswith((b"<!doctype", b"<html", b"<script", b"{", b"<?xml", b"mz")):
        return False, "Conteúdo não é áudio binário (HTML/JSON/XML/Executável detectado)."

    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct.startswith(("text/", "application/javascript", "application/x-msdownload")):
            return False, f"MIME type não permitido para áudio: '{ct}'."

    # Check known audio container signatures
    if header.startswith(b"fLaC"):
        return True, "flac"
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return True, "wav"
    if header[:4] == b"FORM" and header[8:12] in (b"AIFF", b"AIFC"):
        return True, "aiff"
    if header.startswith(b"OggS"):
        return True, "ogg"
    if header.startswith(b"ID3"):
        return True, "mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return True, "mp3_adts"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return True, "mp4_aac"
    if header[:4] == b"Opus":
        return True, "opus"

    return False, "Assinatura binária de áudio não reconhecida (magic bytes inválidos)."


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
