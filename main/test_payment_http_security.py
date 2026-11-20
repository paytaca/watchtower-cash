import io
import socket
import ssl
from unittest import TestCase
from unittest.mock import Mock, patch

import requests
from urllib3.exceptions import SSLError
from urllib3.util.ssl_ import create_urllib3_context

from main.utils.payment_http import (
    MAX_RESPONSE_BYTES, UnsafePaymentURL, _destination,
    _PinnedHTTPSConnection, payment_request,
)


def answers(*addresses):
    return [
        (socket.AF_INET6 if ':' in address else socket.AF_INET,
         socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (address, 443))
        for address in addresses
    ]


class ResponseStream(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.body_reads = 0

    def read(self, *args):
        self.body_reads += 1
        return super().read(*args)


class ResponseSocket:
    def __init__(self, body=b'public response', status=200, extra_headers=b''):
        packet = (b'HTTP/1.1 %d Test\r\nContent-Length: %d\r\n' % (status, len(body))
                  + extra_headers + b'Connection: close\r\n\r\n' + body)
        self.stream = ResponseStream(packet)
        self.sent = []

    def makefile(self, *args, **kwargs):
        return self.stream

    def sendall(self, data):
        self.sent.append(bytes(data))

    def settimeout(self, timeout):
        pass

    def close(self):
        pass

    def getpeercert(self):
        return {'subjectAltName': (('DNS', 'merchant.example'),)}


class PaymentHTTPSecurityTests(TestCase):
    def setUp(self):
        self.resolver = patch('main.utils.payment_http.socket.getaddrinfo', return_value=answers('8.8.8.8')).start()
        self.connect = patch('main.utils.payment_http.create_connection').start()
        self.addCleanup(patch.stopall)

    def test_public_get_uses_pinned_ip_and_original_host(self):
        sock = ResponseSocket()
        self.connect.return_value = sock
        response = payment_request('GET', 'http://merchant.example/invoice?id=1')
        self.assertEqual(response.content, b'public response')
        self.assertEqual(response.url, 'http://merchant.example/invoice?id=1')
        self.assertEqual(self.connect.call_args.args[0], ('8.8.8.8', 80))
        sent = b''.join(sock.sent)
        self.assertIn(b'GET /invoice?id=1 HTTP/1.1', sent)
        self.assertIn(b'Host: merchant.example', sent)

    def test_post_preserves_body_and_payment_headers(self):
        sock = ResponseSocket(body=b'{"memo":"accepted"}')
        self.connect.return_value = sock
        response = payment_request('POST', 'http://merchant.example/pay', data=b'synthetic-payment',
                                   headers={'Content-Type': 'application/bitcoincash-payment'})
        self.assertEqual(response.json(), {'memo': 'accepted'})
        sent = b''.join(sock.sent)
        self.assertIn(b'POST /pay HTTP/1.1', sent)
        self.assertIn(b'Content-Type: application/bitcoincash-payment', sent)
        self.assertTrue(sent.endswith(b'synthetic-payment'))

    def test_https_request_keeps_verification_and_host_through_the_adapter(self):
        sock = ResponseSocket()
        self.connect.return_value = sock
        with patch('urllib3.connection.ssl_wrap_socket', return_value=sock) as wrap:
            response = payment_request('GET', 'https://merchant.example/invoice')
        self.assertEqual(response.content, b'public response')
        self.assertEqual(wrap.call_args.kwargs['server_hostname'], 'merchant.example')
        self.assertEqual(wrap.call_args.kwargs['ssl_context'].verify_mode, ssl.CERT_REQUIRED)
        self.assertIn(b'Host: merchant.example', b''.join(sock.sent))

    def test_private_and_special_ip_literals_never_connect(self):
        hosts = (
            '127.0.0.1', '0.0.0.0', '10.0.0.2', '172.16.0.1', '192.168.1.1',
            '169.254.169.254', '100.100.100.200', '192.0.0.8', '192.0.2.1',
            '224.0.0.1', '255.255.255.255', '[::1]', '[::]', '[fe80::1]',
            '[fd00::1]', '[ff02::1]', '[::ffff:127.0.0.1]',
            '[::ffff:8.8.8.8]', '[64:ff9b::7f00:1]', '[2002:7f00:1::]',
        )
        for method in ('GET', 'POST'):
            for host in hosts:
                with self.subTest(method=method, host=host), self.assertRaises(UnsafePaymentURL):
                    payment_request(method, 'http://' + host + '/')
        self.connect.assert_not_called()

    def test_private_or_mixed_dns_answers_never_connect(self):
        for result in (answers('10.0.0.2'), answers('8.8.8.8', '127.0.0.1'),
                       answers('8.8.8.8', '::1'), []):
            self.resolver.return_value = result
            with self.subTest(result=result), self.assertRaises(UnsafePaymentURL):
                payment_request('GET', 'https://merchant.example/')
        self.connect.assert_not_called()

    def test_alternative_numeric_hosts_resolving_to_loopback_are_blocked(self):
        self.resolver.return_value = answers('127.0.0.1')
        for host in ('2130706433', '0x7f000001', '127.1', '0177.0.0.1'):
            with self.subTest(host=host), self.assertRaises(UnsafePaymentURL):
                payment_request('GET', 'http://' + host + '/')
        self.connect.assert_not_called()

    def test_dns_is_not_resolved_again_at_connection_time(self):
        self.resolver.side_effect = [answers('8.8.8.8'), answers('127.0.0.1')]
        self.connect.return_value = ResponseSocket()
        payment_request('GET', 'http://merchant.example/')
        self.resolver.assert_called_once_with('merchant.example', 80, type=socket.SOCK_STREAM)
        self.assertEqual(self.connect.call_args.args[0], ('8.8.8.8', 80))

    def test_public_address_fallback_only_uses_validated_answers(self):
        self.resolver.return_value = answers('2606:4700:4700::1111', '8.8.8.8')
        self.connect.side_effect = [OSError('synthetic unavailable IPv6'), ResponseSocket()]
        self.assertEqual(payment_request('GET', 'http://merchant.example/').status_code, 200)
        targets = [call.args[0] for call in self.connect.call_args_list]
        self.assertEqual(targets, [('2606:4700:4700::1111', 80), ('8.8.8.8', 80)])

    def test_invalid_urls_and_nonstandard_ports_are_rejected(self):
        urls = (None, '', 42, 'file:///etc/passwd', 'gopher://merchant.example/',
                '//merchant.example/', 'http://user:password@merchant.example/',
                'http://merchant.example:8000/', 'https://merchant.example:9000/',
                'http://merchant.example:0/', 'http://merchant.example:bad/',
                'http://merchant.example\\@127.0.0.1/', 'http://merchant.example/\r\n',
                'http://[fe80::1%25eth0]/', 'http://%31%32%37.0.0.1/')
        for url in urls:
            with self.subTest(url=url), self.assertRaises(UnsafePaymentURL):
                payment_request('GET', url)
        self.connect.assert_not_called()

    def test_dns_errors_fail_closed(self):
        self.resolver.side_effect = socket.gaierror('synthetic resolution failure')
        with self.assertRaises(UnsafePaymentURL):
            payment_request('GET', 'http://merchant.example/')
        self.connect.assert_not_called()

    def test_redirects_are_rejected_without_following_or_consuming_the_body(self):
        for method in ('GET', 'POST'):
            for status in (301, 302, 303, 307, 308):
                sock = ResponseSocket(body=b'do not read', status=status,
                                      extra_headers=b'Location: http://127.0.0.1:3010/\r\n')
                self.connect.reset_mock()
                self.connect.return_value = sock
                with self.subTest(method=method, status=status), self.assertRaises(UnsafePaymentURL):
                    payment_request(method, 'http://merchant.example/', data=b'payment' if method == 'POST' else None)
                self.connect.assert_called_once()
                self.assertEqual(sock.stream.body_reads, 0)

    def test_environment_proxies_and_netrc_are_not_used(self):
        self.connect.return_value = ResponseSocket()
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:3010/', 'ALL_PROXY': 'http://127.0.0.1:3010/'}), \
                patch('requests.sessions.get_netrc_auth') as netrc:
            payment_request('GET', 'http://merchant.example/')
            netrc.assert_not_called()
        self.assertEqual(self.connect.call_args.args[0], ('8.8.8.8', 80))

    def test_oversized_responses_are_rejected(self):
        self.connect.return_value = ResponseSocket(body=b'x' * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(UnsafePaymentURL):
            payment_request('GET', 'http://merchant.example/')

    def test_response_read_deadline_is_enforced(self):
        response = Mock(status_code=200)
        response.iter_content.return_value = iter([b'x'])
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('main.utils.payment_http._PaymentSession') as session, \
                patch('main.utils.payment_http.time.monotonic', side_effect=[0, 31]):
            session.return_value.__enter__.return_value.request.return_value = response
            with self.assertRaises(requests.exceptions.Timeout):
                payment_request('GET', 'http://merchant.example/')

    def test_connection_timeout_remains_a_requests_error(self):
        self.connect.side_effect = socket.timeout('synthetic timeout')
        with self.assertRaises(requests.exceptions.ConnectTimeout):
            payment_request('GET', 'http://merchant.example/')

    def test_https_keeps_original_sni_and_requires_certificate_verification(self):
        context = create_urllib3_context(cert_reqs=ssl.CERT_REQUIRED)
        conn = _PinnedHTTPSConnection('merchant.example', timeout=5,
                                      pinned_addresses=('8.8.8.8',), ssl_context=context)
        conn.set_cert(cert_reqs=ssl.CERT_REQUIRED)
        tls_socket = Mock()
        tls_socket.getpeercert.return_value = {'subjectAltName': (('DNS', 'merchant.example'),)}
        with patch('urllib3.connection.ssl_wrap_socket', return_value=tls_socket) as wrap:
            conn.connect()
            self.assertEqual(wrap.call_args.kwargs['server_hostname'], 'merchant.example')
            self.assertEqual(wrap.call_args.kwargs['ssl_context'].verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(conn.is_verified)
        self.assertEqual(self.connect.call_args.args[0], ('8.8.8.8', 443))

    def test_https_rejects_a_certificate_for_another_hostname(self):
        conn = _PinnedHTTPSConnection('merchant.example', timeout=5,
                                      pinned_addresses=('8.8.8.8',),
                                      ssl_context=create_urllib3_context(cert_reqs=ssl.CERT_REQUIRED))
        conn.set_cert(cert_reqs=ssl.CERT_REQUIRED)
        tls_socket = Mock()
        tls_socket.getpeercert.return_value = {'subjectAltName': (('DNS', 'other.example'),)}
        with patch('urllib3.connection.ssl_wrap_socket', return_value=tls_socket), \
                self.assertRaises((ssl.CertificateError, SSLError)):
            conn.connect()

    def test_tls_verification_cannot_be_disabled(self):
        for verify in (False, None, ''):
            with self.subTest(verify=verify), self.assertRaises(ValueError):
                payment_request('GET', 'https://merchant.example/', verify=verify)
        self.connect.assert_not_called()

    def test_public_ipv6_and_idna_hosts_normalize_safely(self):
        self.assertEqual(_destination('https://[2606:4700:4700::1111]/')[2], '2606:4700:4700::1111')
        destination = _destination('https://BÜCHER.example./invoice#ignored')
        self.assertEqual(destination[0], 'https://xn--bcher-kva.example/invoice')
