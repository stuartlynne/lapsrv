"""Versioned private settings; target profiles contain token paths, never tokens."""
from __future__ import annotations
import copy,json,math,os,secrets,stat,tempfile,threading
from pathlib import Path
from urllib.parse import urlsplit

TARGET_DEFAULTS=dict(url='http://127.0.0.1:8050/mcp',token_file='~/.config/crossmgr-mcp/token',tool_names={},instance='',race_path='',timezone='America/Vancouver',timezone_file='')
DEFAULTS=dict(version=1,selected_target='local',targets={'local':TARGET_DEFAULTS},mode='current',saved_race_path='',poll_seconds=5.0,
    listen_host='0.0.0.0',port=53136,web_host='0.0.0.0',web=8865,ip_address=[],show_unknown_tags=False,
    group_gap_seconds=2.0,group_max_age_seconds=180.0,no_gui=False,log_level='INFO',
    export_dir='~/.local/share/lapsrv/exports',ui_geometry='1400x900')
RESTART_FIELDS=('listen_host','port','web_host','web','ip_address','no_gui','export_dir')


def validate(values):
    unknown=set(values)-set(DEFAULTS)
    if unknown:raise ValueError('Unknown settings: '+', '.join(sorted(unknown)))
    data=copy.deepcopy(DEFAULTS);data.update(copy.deepcopy(values))
    if data['version']!=1:raise ValueError('Unsupported settings version')
    if not isinstance(data['targets'],dict) or not data['targets']:raise ValueError('Add at least one CrossMgr target')
    for name,target in data['targets'].items():
        if not isinstance(name,str) or not name.strip() or len(name)>80 or not isinstance(target,dict):raise ValueError('Invalid target profile')
        if set(target)-set(TARGET_DEFAULTS):raise ValueError('Unknown target fields')
        target=dict(copy.deepcopy(TARGET_DEFAULTS),**target)
        url=urlsplit(target['url']);port=url.port
        if url.scheme not in ('http','https') or not url.netloc or url.username or url.password:raise ValueError('MCP URL must be HTTP(S), without embedded credentials')
        if not isinstance(target['tool_names'],dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in target['tool_names'].items()):raise ValueError('Tool aliases must be a JSON object of names')
        for field in ('token_file','instance','race_path','timezone','timezone_file'):
            if not isinstance(target[field],str):raise ValueError('Invalid '+field)
        data['targets'][name]=target
    if data['selected_target'] not in data['targets']:raise ValueError('Select an existing CrossMgr target')
    if data['mode'] not in ('current','saved'):raise ValueError('Race source must be current or saved')
    if data['mode']=='saved' and not str(data['saved_race_path']).strip():raise ValueError('Enter a saved CMN path on the MCP host')
    for field in ('port','web'):
        if isinstance(data[field],bool) or not isinstance(data[field],int) or not 0<=data[field]<=65535:raise ValueError(field+' must be a valid TCP port')
    for field,low,high in [('poll_seconds',1,120),('group_gap_seconds',0,300),('group_max_age_seconds',1,86400)]:
        value=float(data[field])
        if not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{field} must be {low}–{high}')
        data[field]=value
    if not isinstance(data['ip_address'],list) or len(data['ip_address'])>3 or not all(isinstance(x,str) and x and not x.startswith('-') for x in data['ip_address']):raise ValueError('Enter up to three IP addresses/hostnames')
    for field in ('show_unknown_tags','no_gui'):
        if not isinstance(data[field],bool):raise ValueError(field+' must be true or false')
    for field in ('listen_host','web_host','export_dir','ui_geometry','log_level','saved_race_path'):
        if not isinstance(data[field],str):raise ValueError('Invalid '+field)
    if data['log_level'].upper() not in ('DEBUG','INFO','WARNING','ERROR','CRITICAL'):raise ValueError('Invalid log level')
    return data


class SettingsStore:
    def __init__(self,path=None,overrides=None):
        self.path=Path(path or os.environ.get('LAPSRV_CONFIG','~/.config/lapsrv/settings.json')).expanduser()
        self.lock=threading.RLock();self.revision=0
        data=json.loads(self.path.read_text()) if self.path.exists() else self.defaults()
        data.update(overrides or {});self.data=validate(data)
    @staticmethod
    def defaults():
        data=copy.deepcopy(DEFAULTS)
        # Adopt RaceVideo's named connection descriptors, not its selected race,
        # workstation paths or any token contents. Subsequent saves are independent.
        source=Path(os.environ.get('RACEVIDEO_CROSSMGR_CONFIG','~/.config/racevideo/crossmgr.json')).expanduser()
        if source.exists():
            raw=json.loads(source.read_text());profiles=raw.get('targets') or {'local':raw}
            targets={}
            for name,profile in profiles.items():
                base={k:v for k,v in raw.items() if k in TARGET_DEFAULTS}
                base.update({k:v for k,v in profile.items() if k in TARGET_DEFAULTS})
                if 'live_race_path' in profile:base['race_path']=profile['live_race_path']
                targets[name]=dict(copy.deepcopy(TARGET_DEFAULTS),**base)
            data['targets']=targets;data['selected_target']=raw.get('selected_target') or next(iter(targets))
        return data
    def read(self):
        with self.lock:return copy.deepcopy(self.data),self.revision
    def snapshot(self):
        with self.lock:return copy.deepcopy(self.data)
    def save(self,values,*,expected_revision=None):
        data=validate(values)
        with self.lock:
            if expected_revision is not None and expected_revision!=self.revision:raise ValueError('Settings changed; reload before saving')
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix=self.path.name+'.',dir=self.path.parent)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
                os.replace(name,self.path)
            finally:
                if os.path.exists(name):os.unlink(name)
            self.data=data;self.revision+=1
            return self.snapshot()
    @property
    def admin_path(self):return self.path.with_name('admin.token')
    def admin_token(self):
        with self.lock:
            self.admin_path.parent.mkdir(parents=True,exist_ok=True)
            if not self.admin_path.exists():
                try:
                    with open(self.admin_path,'x',opener=lambda p,f:os.open(p,f,0o600)) as stream:stream.write(secrets.token_urlsafe(32)+'\n')
                except FileExistsError:pass
            return self.admin_path.read_text().strip()
