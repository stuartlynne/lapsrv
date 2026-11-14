"""Read-only CrossMgr MCP transport. Early RFID reads never enter this client."""
from __future__ import annotations
import asyncio,copy,datetime as dt,json,logging,time
from pathlib import Path
from zoneinfo import ZoneInfo

READ_TOOLS={'bridge.identity','bridge.snapshot','instances.list','race.roster','race.review'}


def error_message(exc):
    """Expose transport failures hidden inside AnyIO exception groups."""
    import httpx
    if isinstance(exc,BaseExceptionGroup):
        return '; '.join(dict.fromkeys(error_message(child) for child in exc.exceptions))
    if isinstance(exc,httpx.HTTPStatusError):
        status=exc.response.status_code
        if status==401:return 'HTTP 401 Unauthorized: check the bearer-token file for the selected MCP target'
        if status==403:return 'HTTP 403 Forbidden: this token cannot access the selected MCP target'
        return f'HTTP {status}: {exc.response.reason_phrase}'
    if isinstance(exc,(httpx.TimeoutException,TimeoutError)):return 'CrossMgr MCP request timed out'
    return str(exc) or type(exc).__name__


def epc(value):
    # CrossMgr's tag contract ignores leading zero padding, including 96-bit EPCs.
    text=''.join(str(value or '').split()).upper()
    if text.startswith('0X'):text=text[2:]
    return (text.lstrip('0') or '0') if text else ''


def source_key(settings):
    return json.dumps([settings['targets'][settings['selected_target']],settings['mode'],settings['saved_race_path'] if settings['mode']=='saved' else None],sort_keys=True)


def race_epoch(value,timezone,timezone_file=""):
    if not value:return None
    parsed=dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if timezone_file:
            with Path(timezone_file).expanduser().open('rb') as stream:zone=ZoneInfo.from_file(stream,key=timezone)
        else:zone=ZoneInfo(timezone)
        a=parsed.replace(tzinfo=zone,fold=0);b=parsed.replace(tzinfo=zone,fold=1)
        if a.utcoffset()!=b.utcoffset():raise ValueError('Race start is ambiguous in this timezone; configure the correct source timezone')
        parsed=a
    return parsed.timestamp()


class MCPReader:
    def __init__(self):self.cached_key=None;self.cached=None;self.checked=0
    async def call(self,session,target,name,args):
        if name not in READ_TOOLS:raise ValueError('Lapsrv MCP is read-only')
        result=await session.call_tool(target.get('tool_names',{}).get(name,name),args)
        if result.isError:
            detail=next((c.text for c in result.content if c.type=='text'),'MCP request failed')
            raise ValueError(f'{name}: {detail}')
        data=result.structuredContent
        if data is None:data=json.loads(next(c.text for c in result.content if c.type=='text'))
        return data['result'] if isinstance(data,dict) and set(data)=={'result'} else data
    async def pages(self,session,target,name,path):
        first=await self.call(session,target,name,dict(path=path,trusted_pickle=True,limit=500))
        if not isinstance(first.get('race'),dict):raise ValueError(name+' returned no race')
        result=copy.deepcopy(first)
        for offset in range(500,int(first['race'].get('total',len(first['race'].get('rows',[])))),500):
            page=await self.call(session,target,name,dict(path=path,trusted_pickle=True,limit=500,offset=offset))
            if page.get('inputs')!=first.get('inputs'):raise ValueError('Race/workbook changed while paging; retry')
            result['race']['rows'].extend(page['race']['rows'])
        return result
    async def fetch_session(self,session,settings,force=False):
        target=settings['targets'][settings['selected_target']];origin={};key=source_key(settings)
        if settings['mode']=='current':
            select={k:target[k] for k in ('instance','race_path') if target.get(k)}
            identity=await self.call(session,target,'bridge.identity',select)
            if not identity.get('race_path') or identity.get('state')=='none':raise ValueError('No current CrossMgr race; select a GUI instance or a saved CMN')
            # Finished/unstarted states are rechecked at least once a minute for
            # metadata edits; running snapshots follow the configured poll rate.
            if not force and self.cached_key and self.cached_key[:3]==(key,identity['instance'],identity['race_path']) and time.monotonic()-self.checked<60 and identity['state']!='running' and self.cached['roster']['state']==identity['state']:return dict(self.cached,settings=copy.deepcopy(settings))
            origin=await self.call(session,target,'bridge.snapshot',dict(instance=identity['instance'],race_path=identity['race_path']))
            if origin['instance']!=identity['instance'] or origin['race_path']!=identity['race_path']:raise ValueError('CrossMgr changed race during snapshot; retry')
            path=origin['path'];cache_key=(key,origin['instance'],origin['race_path'],origin['snapshot_sha256'])
        else:
            path=settings['saved_race_path'];origin=dict(race_path=path,instance='saved');cache_key=None
        if cache_key and not force and cache_key==self.cached_key and time.monotonic()-self.checked<60:return dict(self.cached,settings=copy.deepcopy(settings))
        try:roster=await self.pages(session,target,'race.roster',path)
        except Exception as exc:raise ValueError('Full roster unavailable: check race.roster support and its gateway alias if used. '+error_message(exc)) from None
        if roster['race'].get('state')=='unstarted':review=dict(inputs=roster['inputs'],race=dict(rows=[],is_time_trial=roster['race'].get('is_time_trial',False)))
        else:review=await self.pages(session,target,'race.review',path)
        if review['inputs']!=roster['inputs']:raise ValueError('Workbook changed between roster and results; retry')
        result=dict(roster=roster['race'],review=review['race'],origin=origin,settings=copy.deepcopy(settings),fetched_at=time.time())
        self.cached,self.cached_key,self.checked=result,cache_key,time.monotonic()
        return result
    async def fetch(self,settings,force=False):
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from datetime import timedelta
        target=settings['targets'][settings['selected_target']]
        headers={}
        if target.get('token_file'):headers['Authorization']='Bearer '+Path(target['token_file']).expanduser().read_text().strip()
        async with httpx.AsyncClient(headers=headers,timeout=30) as http:
            async with streamable_http_client(target['url'],http_client=http) as (reader,writer,_):
                async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=30)) as session:
                    await session.initialize();return await self.fetch_session(session,settings,force)


class MCPMonitor:
    def __init__(self,state,store):
        self.state=state;self.store=store;self.client=MCPReader();self.stop_event=asyncio.Event();self.wake=asyncio.Event();self.force=False
    async def run(self):
        while not self.stop_event.is_set():
            settings,revision=self.store.read();key=source_key(settings)
            if key!=getattr(self,'key',None):self.key=key;self.state.invalidate_mcp('CrossMgr source changed')
            force=self.force;self.force=False;self.wake.clear()
            try:
                result=await self.client.fetch(settings,force)
                if self.store.revision==revision and not self.stop_event.is_set():self.state.apply_mcp(result)
            except asyncio.CancelledError:raise
            except Exception as exc:
                if self.store.revision==revision:
                    text=error_message(exc)
                    # Never log credentials even if an HTTP implementation embeds
                    # request headers in its exception. Tokens live only in files.
                    target=settings['targets'][settings['selected_target']]
                    if target.get('token_file'):
                        try:
                            secret=Path(target['token_file']).expanduser().read_text().strip()
                            if secret:text=text.replace(secret,'[redacted]')
                        except OSError:pass
                    self.state.invalidate_mcp(text);logging.getLogger('lapsrv.mcp').warning('CrossMgr: %s',text)
            try:await asyncio.wait_for(self.wake.wait(),timeout=settings['poll_seconds'])
            except asyncio.TimeoutError:pass
    async def stop(self):self.stop_event.set();self.wake.set()
