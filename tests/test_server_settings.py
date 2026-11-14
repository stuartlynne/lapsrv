import asyncio,copy,datetime as dt,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import ClientSession,web
import lapsrv
from lapsrv_config import SettingsStore
from lapsrv_settings import authorized
from test_mcp_transition import fixture


class ServerSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_receiver_web_settings_hot_source_and_saved_restart_fields(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':str(Path(d)/'absent')}):
            store=SettingsStore(Path(d)/'settings.json');data=store.snapshot();data.update(port=0,web=0,listen_host='127.0.0.1',web_host='127.0.0.1',no_gui=True,export_dir=str(Path(d)/'exports'));store.save(data)
            app=lapsrv.LapsrvApp(SimpleNamespace(config=str(store.path),no_gui=True),store)
            async def fetch(settings,force=False):
                data=fixture();data['settings']=settings
                if settings['selected_target']=='other':data['roster']['rows'][0]['bib']=99;data['review']['rows']=[]
                return data
            with patch.object(app.crossmgr.client,'fetch',side_effect=fetch):
                task=asyncio.create_task(app.run());writer=None
                try:
                    for _ in range(100):
                        if app.web.site and app.state.mcp_ready:break
                        await asyncio.sleep(.02)
                    self.assertTrue(app.state.mcp_ready)
                    webport=app.web.site._server.sockets[0].getsockname()[1];rfidport=app.jchip.server.sockets[0].getsockname()[1]
                    reader,writer=await asyncio.open_connection('127.0.0.1',rfidport)
                    writer.write(b'N0001Early-test\r');await writer.drain();self.assertEqual(await asyncio.wait_for(reader.readuntil(b'\r'),1),b'GT\r')
                    now=dt.datetime.now();writer.write(('GT0'+now.strftime('%H%M%S')+'00 date='+now.strftime('%Y%m%d')+'\r').encode());await writer.drain()
                    self.assertEqual(await asyncio.wait_for(reader.readuntil(b'\r'),1),b'S0000\r')
                    writer.write(('DA000ABC '+now.strftime('%H:%M:%S.%f')+' 00 date='+now.strftime('%Y%m%d')+'\r').encode());await writer.drain()
                    async with ClientSession() as http:
                        for _ in range(100):
                            async with http.get(f'http://127.0.0.1:{webport}/api/state') as r:snapshot=await r.json()
                            if snapshot['passings']:break
                            await asyncio.sleep(.01)
                        self.assertEqual(snapshot['passings'][0]['bib'],'24')
                        async with http.get(f'http://127.0.0.1:{webport}/settings') as r:self.assertIn('Save and apply',await r.text())
                        async with http.get(f'http://127.0.0.1:{webport}/api/settings') as r:loaded=await r.json()
                        changed=loaded['settings'];changed['targets']['other']=dict(changed['targets']['local'],url='http://other:8050/mcp');changed['selected_target']='other';changed['port']=53137
                        async with http.post(f'http://127.0.0.1:{webport}/api/settings',json=dict(settings=changed,revision=loaded['revision'])) as r:
                            self.assertEqual(r.status,200);saved=await r.json();self.assertEqual(saved['restart_required'],['port'])
                        for _ in range(100):
                            if app.state.mcp_source.get('target')=='other' and app.state.mcp_ready:break
                            await asyncio.sleep(.02)
                        self.assertEqual(app.state.config.riders_by_tag['ABC'].bib,'99')
                        self.assertEqual(app.jchip.server.sockets[0].getsockname()[1],rfidport)
                        self.assertFalse(writer.is_closing())
                        self.assertEqual(SettingsStore(store.path).snapshot()['selected_target'],'other')
                        async with http.post(f'http://127.0.0.1:{webport}/api/settings',json=dict(settings=changed,revision=loaded['revision'])) as r:self.assertEqual(r.status,400)
                        async with http.post(f'http://127.0.0.1:{webport}/api/settings',json=dict(settings=changed,revision=saved['revision']),headers={'Origin':'http://evil.invalid'}) as r:self.assertEqual(r.status,403)
                finally:
                    if writer:writer.close();await writer.wait_closed()
                    app.request_stop();await asyncio.wait_for(task,5)
    def test_remote_configuration_requires_admin_token_and_rejects_cross_origin(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':str(Path(d)/'absent')}):
            store=SettingsStore(Path(d)/'settings.json')
            request=SimpleNamespace(remote='192.168.1.50',host='timing.local:8865',headers={})
            with self.assertRaises(web.HTTPUnauthorized):authorized(request,store)
            request.headers['X-Lapsrv-Admin']=store.admin_token();authorized(request,store)
            request.headers['Origin']='https://different.invalid'
            with self.assertRaises(web.HTTPForbidden):authorized(request,store)
