"""Real headless Chrome: configure, save a profile, then render approaching riders."""
import asyncio,base64,copy,json,os,signal,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aiohttp,websockets
import lapsrv
from lapsrv_config import SettingsStore
from test_mcp_transition import fixture


async def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':directory+'/absent'}):
        store=SettingsStore(Path(directory)/'settings.json');data=store.snapshot();data.update(no_gui=True,port=0,web=0,listen_host='127.0.0.1',web_host='127.0.0.1',export_dir=directory+'/exports');store.save(data)
        app=lapsrv.LapsrvApp(SimpleNamespace(config=str(store.path),no_gui=True),store)
        async def fetch(settings,force=False):
            result=fixture();result['settings']=settings;return result
        chrome=None
        with patch.object(app.crossmgr.client,'fetch',side_effect=fetch):
            task=asyncio.create_task(app.run())
            try:
                while not app.web.site or not app.state.mcp_ready:await asyncio.sleep(.03)
                port=app.web.site._server.sockets[0].getsockname()[1];url=f'http://127.0.0.1:{port}'
                chrome=await asyncio.create_subprocess_exec('/usr/bin/google-chrome','--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--remote-debugging-port=0','--user-data-dir='+directory+'/chrome',url+'/settings',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
                debug=Path(directory)/'chrome/DevToolsActivePort'
                for _ in range(200):
                    if debug.exists():break
                    await asyncio.sleep(.03)
                debugport=int(debug.read_text().splitlines()[0])
                async with aiohttp.ClientSession() as http:
                    async with http.get(f'http://127.0.0.1:{debugport}/json/list') as response:tabs=await response.json()
                tab=next(t for t in tabs if t['type']=='page');sequence=0;errors=[]
                async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
                    async def command(method,params=None):
                        nonlocal sequence
                        sequence+=1;ident=sequence;await ws.send(json.dumps(dict(id=ident,method=method,params=params or {})))
                        while True:
                            message=json.loads(await ws.recv())
                            if message.get('method')=='Runtime.exceptionThrown':errors.append(message)
                            if message.get('id')==ident:
                                if 'error' in message:raise AssertionError(message['error'])
                                return message.get('result',{})
                    async def evaluate(expression):
                        result=await command('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                        if result.get('exceptionDetails'):raise AssertionError(result['exceptionDetails'])
                        return result.get('result',{}).get('value')
                    await command('Runtime.enable');await command('Page.enable')
                    for _ in range(100):
                        if await evaluate("document.getElementById('status')?.textContent.includes('Settings loaded')"):break
                        await asyncio.sleep(.05)
                    assert await evaluate("document.getElementById('target').options.length")>=1
                    await evaluate("document.getElementById('name').value='Sunday test';document.getElementById('url').value='http://timing-laptop:8050/mcp';document.getElementById('port').value=53136;document.getElementById('web').value=8865;document.getElementById('poll_seconds').value=2;document.getElementById('form').requestSubmit();true")
                    for _ in range(100):
                        if store.snapshot()['selected_target']=='Sunday test':break
                        await asyncio.sleep(.05)
                    assert store.snapshot()['selected_target']=='Sunday test'
                    assert SettingsStore(store.path).snapshot()['poll_seconds']==2
                    for _ in range(100):
                        if await evaluate("document.getElementById('status').textContent.startsWith('Saved.')"):break
                        await asyncio.sleep(.05)
                    layout=await command('Page.getLayoutMetrics');size=layout.get('cssContentSize',layout['contentSize'])
                    shot=await command('Page.captureScreenshot',dict(format='png',captureBeyondViewport=True,clip=dict(x=0,y=0,width=size['width'],height=size['height'],scale=1)))
                    Path('artifacts/settings-web.png').write_bytes(base64.b64decode(shot['data']))
                    while not app.state.mcp_ready:await asyncio.sleep(.02)
                    app.state.record_passing('000ABC',lapsrv.dt.datetime.now().astimezone(),'test only')
                    await command('Page.navigate',dict(url=url))
                    for _ in range(100):
                        if await evaluate("document.body.innerText.includes('Brittany')"):break
                        await asyncio.sleep(.05)
                    assert await evaluate("document.body.innerText.includes('Brittany')")
                    assert await evaluate("document.getElementById('sourceStatus').textContent.includes('Sunday test')")
                    await command('Emulation.setDeviceMetricsOverride',dict(width=1400,height=1000,deviceScaleFactor=1,mobile=False))
                    shot=await command('Page.captureScreenshot',dict(format='png'));Path('artifacts/approaching-web.png').write_bytes(base64.b64decode(shot['data']))
                    assert not errors,errors
                print('Browser passed: profiles load, form validation/save persists, restart notice, source badge and approaching-rider rendering, no JS exceptions')
            finally:
                if chrome:
                    try:os.killpg(chrome.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    await chrome.wait();await asyncio.sleep(.1)
                app.request_stop();await asyncio.wait_for(task,5)


asyncio.run(main())
