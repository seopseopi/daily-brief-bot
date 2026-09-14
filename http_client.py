"""Shared HTTPS transport with verified platform trust and existing timeouts.

Some python.org macOS installations have no OpenSSL CA bundle until their
certificate-install command has been run. Use an available OS CA bundle in
that case; never disable hostname checking or certificate verification.
"""

from functools import lru_cache
import os
from pathlib import Path
import ssl
import urllib.request

SYSTEM_CA_FILES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


@lru_cache(maxsize=8)
def _verified_context(cafile, capath):
    # Explicit overrides are intentional, including enterprise trust roots.
    # An invalid explicit path must not silently become a different trust store.
    if cafile or capath:
        return ssl.create_default_context(cafile=cafile or None, capath=capath or None)
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] == 0 and not ssl.get_default_verify_paths().capath:
        for filename in SYSTEM_CA_FILES:
            if Path(filename).is_file():
                context.load_verify_locations(cafile=filename)
                if context.cert_store_stats()["x509_ca"]:
                    break
    return context


def verified_context():
    return _verified_context(os.environ.get("SSL_CERT_FILE", ""), os.environ.get("SSL_CERT_DIR", ""))


def open_url(request, *, timeout):
    """urllib-compatible response; retries remain the responsibility of callers."""
    return urllib.request.urlopen(request, timeout=timeout, context=verified_context())
