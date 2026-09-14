import os
import ssl
from types import SimpleNamespace
import unittest
from unittest import mock

import http_client


class VerifiedTransportTests(unittest.TestCase):
    def setUp(self):
        http_client._verified_context.cache_clear()

    def tearDown(self):
        http_client._verified_context.cache_clear()

    def test_missing_default_bundle_loads_an_available_system_store(self):
        context = mock.Mock()
        context.cert_store_stats.side_effect = [{"x509_ca": 0}, {"x509_ca": 150}]
        with (mock.patch.dict(os.environ, {}, clear=True),
              mock.patch.object(http_client.ssl, "create_default_context", return_value=context),
              mock.patch.object(http_client.ssl, "get_default_verify_paths", return_value=SimpleNamespace(capath=None)),
              mock.patch.object(http_client.Path, "is_file", return_value=True)):
            self.assertIs(http_client.verified_context(), context)
        context.load_verify_locations.assert_called_once_with(cafile=http_client.SYSTEM_CA_FILES[0])

    def test_existing_default_trust_store_is_kept(self):
        context = mock.Mock()
        context.cert_store_stats.return_value = {"x509_ca": 150}
        with (mock.patch.dict(os.environ, {}, clear=True),
              mock.patch.object(http_client.ssl, "create_default_context", return_value=context)):
            http_client.verified_context()
        context.load_verify_locations.assert_not_called()

    def test_invalid_explicit_override_is_not_silently_replaced(self):
        with (mock.patch.dict(os.environ, {"SSL_CERT_FILE": "/custom/missing-ca.pem"}, clear=True),
              mock.patch.object(http_client.ssl, "create_default_context", side_effect=FileNotFoundError) as create):
            with self.assertRaises(FileNotFoundError):
                http_client.verified_context()
        create.assert_called_once_with(cafile="/custom/missing-ca.pem", capath=None)

    def test_requests_verify_certificates_and_hostnames_and_preserve_timeout(self):
        request = object()
        with (mock.patch.dict(os.environ, {}, clear=True),
              mock.patch.object(http_client.urllib.request, "urlopen") as urlopen):
            http_client.open_url(request, timeout=12)
        args, kwargs = urlopen.call_args
        self.assertEqual(args, (request,))
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs["context"].check_hostname)

    def test_trust_context_changes_when_explicit_environment_changes(self):
        with mock.patch.object(http_client.ssl, "create_default_context") as create:
            with mock.patch.dict(os.environ, {"SSL_CERT_FILE": "/one.pem"}, clear=True):
                http_client.verified_context()
            with mock.patch.dict(os.environ, {"SSL_CERT_FILE": "/two.pem"}, clear=True):
                http_client.verified_context()
        self.assertEqual(create.call_count, 2)
