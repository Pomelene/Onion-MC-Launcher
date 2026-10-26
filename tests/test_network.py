"""Anonymous catalog reads recover from proxy faults without replaying auth."""
import io
import ssl
import urllib.error
import urllib.request
from unittest.mock import Mock,patch

from launcher.network import fetch_public,secure_open,SafeRedirectHandler


def request():
    return urllib.request.Request('https://catalog.example/webapp.json',headers={'Accept':'application/json'})


def fetch_with_routes(proxies,outcomes,*,proxy=None):
    routes=[];requests=[];timeouts=[]
    def build(*handlers):
        assert any(isinstance(h,SafeRedirectHandler) for h in handlers)
        routes.append(next(h.proxies for h in handlers if isinstance(h,urllib.request.ProxyHandler)))
        outcome=outcomes[len(routes)-1]
        class Opener:
            def open(self,req,timeout):
                requests.append(req);timeouts.append(timeout)
                if isinstance(outcome,Exception):
                    # Real ProxyHandler modifies the URL/host and headers.
                    req.set_proxy('proxy.example:7890','http')
                    req.add_header('Proxy-Authorization','Basic fixture-proxy-secret')
                    raise outcome
                return outcome
        return Opener()
    with patch('launcher.network.urllib.request.getproxies',return_value=proxies),patch('launcher.network.urllib.request.build_opener',side_effect=build):
        body=fetch_public(request(),limit=100,proxy=proxy)
    return body,routes,requests,timeouts


def test_public_proxy_success_and_proxy_disabled_each_make_one_attempt():
    for proxies in ({},{'https':'http://proxy.example:7890'}):
        body,routes,requests,_=fetch_with_routes(proxies,[io.BytesIO(b'{}')])
        assert body==b'{}' and routes==[proxies] and len(requests)==1


def test_public_proxy_connection_failures_retry_direct_with_fresh_request():
    failures=[urllib.error.URLError(ConnectionRefusedError()),TimeoutError(),
              urllib.error.URLError(ssl.SSLCertVerificationError('fixture'))]
    for code in (407,429,502,503,504):
        failures.append(urllib.error.HTTPError('https://catalog.example/',code,'proxy failure',{},io.BytesIO()))
    failures.append(urllib.error.HTTPError('https://catalog.example/',403,'rate limited',{'X-RateLimit-Remaining':'0'},io.BytesIO()))
    for failure in failures:
        body,routes,requests,timeouts=fetch_with_routes({'https':'http://proxy.example:7890'},[failure,io.BytesIO(b'{}')])
        assert body==b'{}' and routes==[{'https':'http://proxy.example:7890'},{}]
        assert requests[0] is not requests[1] and requests[1].host=='catalog.example'
        assert requests[1].get_header('Proxy-authorization') is None
        assert requests[1].get_header('Accept')=='application/json'
        assert 0<timeouts[0]<=10 and 0<timeouts[1]<=20


def test_public_proxy_body_disconnect_also_retries_and_closes_response():
    class Broken(io.BytesIO):
        def read(self,n):raise ConnectionResetError()
    broken=Broken()
    body,routes,_,_=fetch_with_routes({'https':'http://proxy.example:7890'},[broken,io.BytesIO(b'{}')])
    assert body==b'{}' and len(routes)==2 and broken.closed


def test_explicit_launcher_proxy_overrides_system_proxy():
    _,routes,_,_=fetch_with_routes({'https':'http://system.example:7890'},[io.BytesIO(b'{}')],proxy='http://custom.example:8080')
    assert routes==[{'http':'http://custom.example:8080','https':'http://custom.example:8080'}]


def test_exhausted_routes_stop_without_unbounded_retry():
    for proxies,attempts in (({},1),({'https':'http://proxy.example:7890'},2)):
        with patch('launcher.network.urllib.request.getproxies',return_value=proxies),patch('launcher.network.urllib.request.build_opener') as build:
            build.return_value.open.side_effect=urllib.error.URLError('fixture unavailable')
            try:fetch_public(request(),limit=100)
            except urllib.error.URLError:pass
            else:raise AssertionError('Expected connection failure')
            assert build.call_count==attempts


def test_public_api_errors_and_oversized_data_do_not_trigger_fallback():
    for outcome,expected in [(io.BytesIO(b'x'*101),ValueError)]+[
            (urllib.error.HTTPError('https://catalog.example/',code,'API error',{},io.BytesIO()),urllib.error.HTTPError)
            for code in (401,403,404)]:
        with patch('launcher.network.urllib.request.getproxies',return_value={'https':'http://proxy.example:7890'}):
            opener=Mock()
            if isinstance(outcome,Exception):opener.open.side_effect=outcome
            else:opener.open.return_value=outcome
            with patch('launcher.network.urllib.request.build_opener',return_value=opener) as build:
                try:fetch_public(request(),limit=100)
                except expected:pass
                else:raise AssertionError('Invalid response accepted')
                assert build.call_count==1


def test_public_fallback_never_accepts_credentials_posts_or_plain_http():
    requests=[urllib.request.Request('http://catalog.example/'),urllib.request.Request('https://catalog.example/',data=b'fixture')]
    for key in ('Authorization','Proxy-Authorization','Cookie','X-API-Key'):
        requests.append(urllib.request.Request('https://catalog.example/',headers={key:'fixture'}))
    for req in requests:
        with patch('launcher.network.urllib.request.build_opener') as build:
            try:fetch_public(req,limit=100)
            except ValueError:pass
            else:raise AssertionError('Non-public request accepted')
            build.assert_not_called()


def test_auth_requests_do_not_gain_direct_retry():
    with patch('launcher.network.urllib.request.build_opener') as build:
        build.return_value.open.side_effect=urllib.error.URLError('fixture proxy unavailable')
        try:secure_open(urllib.request.Request('https://login.example/',data=b'fixture'))
        except urllib.error.URLError:pass
        else:raise AssertionError('Expected connection failure')
        assert build.call_count==1 and build.return_value.open.call_count==1
