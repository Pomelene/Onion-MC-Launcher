"""Authentication protocol regressions; no live credentials or Microsoft calls."""
import io,json,tempfile,time,urllib.error,urllib.parse
from pathlib import Path
from unittest.mock import patch
from launcher.auth import microsoft as ms
from launcher.accounts import AccountRecord,AccountStore


def test_oauth_device_and_token_requests_are_form_encoded():
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size=-1):return b'{"access_token":"fake"}'
    seen=[]
    def opened(request,**kwargs):seen.append(request);return Response()
    with patch.object(ms,'secure_open',side_effect=opened):
        ms.refresh_token('app','refresh+value &')
    request=seen[0]
    assert request.get_header('Content-type')=='application/x-www-form-urlencoded'
    assert urllib.parse.parse_qs(request.data.decode())['refresh_token']==['refresh+value &']


def test_poll_pending_slow_down_and_interval():
    clock=[0.0];waits=[]
    def waited(seconds,cancel):waits.append(seconds);clock[0]+=seconds
    code=ms.DeviceCode('CODE','https://microsoft.com/link','device',100,2,'')
    with patch.object(ms.time,'monotonic',side_effect=lambda:clock[0]),patch.object(ms,'_wait',side_effect=waited),patch.object(ms,'_post_form',side_effect=[ms.AuthError('pending',code='authorization_pending'),ms.AuthError('slow',code='slow_down'),{'access_token':'ms'}]):
        assert ms.poll_for_token('app',code)['access_token']=='ms'
    assert waits==[2,2,7],waits


def test_poll_declined_is_terminal():
    code=ms.DeviceCode('CODE','https://microsoft.com/link','device',100,1,'')
    with patch.object(ms,'_wait'),patch.object(ms,'_post_form',side_effect=ms.AuthError('拒绝',code='authorization_declined')) as post:
        try:ms.poll_for_token('app',code)
        except ms.AuthError as error:assert error.code=='authorization_declined'
        else:raise AssertionError('declined login continued')
        assert post.call_count==1


def test_login_cancelled_before_network():
    with patch.object(ms,'request_device_code') as request:
        try:ms.login_with_device_code('app',lambda code:None,lambda:True)
        except ms.LoginCancelled:pass
        else:raise AssertionError('cancelled login continued')
        request.assert_not_called()


def test_minecraft_expiry_is_not_microsoft_expiry():
    with patch.object(ms,'xbox_authenticate',return_value=('xbl','u')),patch.object(ms,'xsts_authorize',return_value=('xsts','u')),patch.object(ms,'_minecraft_token',return_value={'access_token':'mc','expires_in':600}),patch.object(ms,'fetch_profile',return_value=('a'*32,'Player')),patch.object(ms.time,'time',return_value=1000):
        data=ms._complete_login({'access_token':'ms','refresh_token':'new','expires_in':7200})
    assert data['expires_at']==1600
    assert data['refresh_token']=='new' and data['username']=='Player'


def test_cancel_between_auth_stages_stops_next_request():
    cancelled=[False]
    def xbl(token):cancelled[0]=True;return 'xbl','u'
    with patch.object(ms,'xbox_authenticate',side_effect=xbl),patch.object(ms,'xsts_authorize') as xsts:
        try:ms._complete_login({'access_token':'ms'},should_cancel=lambda:cancelled[0])
        except ms.LoginCancelled:pass
        else:raise AssertionError('cancelled login completed')
        xsts.assert_not_called()


def test_unknown_error_does_not_expose_server_body():
    body=json.dumps({'error':'private-token','error_description':'secret-refresh'}).encode()
    error=urllib.error.HTTPError(ms.TOKEN_URL,400,'bad',{},io.BytesIO(body))
    with patch.object(ms,'secure_open',side_effect=error):
        try:ms._post_form(ms.TOKEN_URL,{})
        except ms.AuthError as exc:
            assert 'private-token' not in str(exc) and 'secret-refresh' not in str(exc)
        else:raise AssertionError('error ignored')


def test_verification_url_only_opens_microsoft_https():
    for url in ('https://evil.example/login','http://microsoft.com/link','https://microsoft.com.evil.example/link','https://user:pass@microsoft.com/link'):
        try:ms.verification_url(url)
        except ms.AuthError:pass
        else:raise AssertionError(url)
    assert ms.verification_url('https://microsoft.com/link')


def test_missing_token_expiry_forces_refresh():
    assert AccountRecord('microsoft','Player','a'*32,access_token='old').is_expired()
    assert not AccountRecord('offline','Player','a'*32).is_expired()


def test_record_repr_excludes_secrets():
    record=AccountRecord('microsoft','Player','a'*32,access_token='secret-access',refresh_token='secret-refresh',client_token='secret-client')
    assert 'secret-' not in repr(record)


def test_refresh_profile_mismatch_preserves_old_account():
    with tempfile.TemporaryDirectory() as folder:
        store=AccountStore(Path(folder)/'accounts.json')
        account=AccountRecord('microsoft','Player','a'*32,access_token='old',refresh_token='refresh',client_id='app')
        store.add(account)
        with patch.object(ms,'refresh_minecraft',return_value={'uuid':'b'*32,'username':'Other','access_token':'new','refresh_token':'r','expires_at':9999999999}):
            try:store.refresh(account)
            except RuntimeError:pass
            else:raise AssertionError('profile mismatch accepted')
        assert store.get(account.uuid).access_token=='old'
        assert AccountStore(store.path).get(account.uuid).access_token=='old'


def test_invalid_profile_uuid_is_not_accepted():
    with patch.object(ms,'_get_json',return_value={'id':'invalid','name':'Player'}):
        try:ms.fetch_profile('fake')
        except ms.AuthError:pass
        else:raise AssertionError('invalid player UUID accepted')


def test_profile_uuid_is_normalized():
    with patch.object(ms,'_get_json',return_value={'id':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','name':'Player'}):
        assert ms.fetch_profile('fake')==('a'*32,'Player')


def test_publisher_application_exchange_uses_standard_payload():
    with patch.object(ms,'_post_json',return_value={'access_token':'mc'}) as post:
        ms._minecraft_token('uhs','xsts','own-application')
        post.assert_called_once_with(ms.MC_LOGIN_URL,{'identityToken':'XBL3.0 x=uhs;xsts'})


def test_xbox_identity_mismatch_stops_minecraft_exchange():
    with patch.object(ms,'xbox_authenticate',return_value=('xbl','one')),patch.object(ms,'xsts_authorize',return_value=('xsts','two')),patch.object(ms,'_minecraft_token') as exchange:
        try:ms._complete_login({'access_token':'ms'})
        except ms.AuthError as error:assert error.code=='identity_mismatch'
        else:raise AssertionError('mismatched identity accepted')
        exchange.assert_not_called()


def test_malformed_xbox_claim_is_safe_error():
    for data in ({},{'DisplayClaims':None},{'DisplayClaims':{'xui':[None]}},{'DisplayClaims':{'xui':[{'uhs':17}]}}):
        with patch.object(ms,'_post_json',return_value=data):
            try:ms.xbox_authenticate('fake')
            except ms.AuthError as error:assert error.code=='invalid_response'
            else:raise AssertionError('malformed Xbox claim accepted')


def test_refresh_preserves_publisher_application():
    with patch.object(ms,'refresh_token',return_value={'access_token':'ms'}),patch.object(ms,'_complete_login',return_value={}) as complete:
        ms.refresh_minecraft('own-application','refresh')
        complete.assert_called_once_with({'access_token':'ms'},'refresh',client_id='own-application')


def test_device_poll_survives_transient_connection_failure():
    clock=[0.0];events=[]
    code=ms.DeviceCode('CODE','https://microsoft.com/link','same-device-code',60,1,'')
    def wait(seconds,cancel):clock[0]+=seconds
    with patch.object(ms.time,'monotonic',side_effect=lambda:clock[0]),patch.object(ms,'_wait',side_effect=wait),patch.object(ms,'_post_form',side_effect=[ms.AuthError('temporary',code='network'),{'access_token':'real-result'}]) as post:
        assert ms.poll_for_token('own',code,on_step=events.append)['access_token']=='real-result'
        assert all(call.args[1]['device_code']=='same-device-code' for call in post.call_args_list)
        assert events and clock[0]==4


def test_device_poll_persistent_outage_still_expires():
    clock=[0.0]
    code=ms.DeviceCode('CODE','https://microsoft.com/link','device',7,1,'')
    def wait(seconds,cancel):clock[0]+=seconds
    with patch.object(ms.time,'monotonic',side_effect=lambda:clock[0]),patch.object(ms,'_wait',side_effect=wait),patch.object(ms,'_post_form',side_effect=ms.AuthError('temporary',code='network')):
        try:ms.poll_for_token('own',code)
        except ms.AuthError as error:assert error.code=='expired_token'
        else:raise AssertionError('outage ignored the device code lifetime')


def test_minecraft_403_is_not_assumed_to_be_registration_error():
    error=ms._error(ms.MC_LOGIN_URL,403,{'errorMessage':'private service detail secret-token'})
    assert error.code=='minecraft_forbidden' and error.status==403
    assert 'secret-token' not in str(error) and '未允许此应用' not in str(error)


def test_known_registration_error_is_classified_without_response_echo():
    error=ms._error(ms.MC_LOGIN_URL,403,{'errorMessage':'Invalid app registration, secret-token'})
    assert error.code=='invalid_app_registration' and error.status==403
    assert 'secret-token' not in str(error)
