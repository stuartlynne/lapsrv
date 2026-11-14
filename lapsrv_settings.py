"""Operator configuration for Tk and the primarily-used web display."""
import hmac,ipaddress,json
from urllib.parse import urlsplit
from aiohttp import web


def authorized(request,store):
    peer=request.remote or ''
    try:local=ipaddress.ip_address(peer).is_loopback
    except ValueError:local=False
    host=urlsplit('//'+request.host).hostname
    origin=request.headers.get('Origin')
    if origin and urlsplit(origin).netloc!=request.host:raise web.HTTPForbidden(text='Settings must be changed from this server page')
    if local and host in ('localhost','127.0.0.1','::1') and not any(h.lower().startswith(('forwarded','x-forwarded')) for h in request.headers):return
    supplied=request.headers.get('X-Lapsrv-Admin','')
    if not supplied or not hmac.compare_digest(supplied,store.admin_token()):raise web.HTTPUnauthorized(text='Operator token required; see the admin.token file beside settings.json')


SETTINGS_HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lapsrv settings</title>
<style>body{font:16px system-ui;margin:1.5rem auto;max-width:850px;padding:0 1rem;background:#f8fafc;color:#132137}h1{font-size:1.6rem}fieldset{margin:1rem 0;border:1px solid #bbc7d7;border-radius:8px;padding:1rem}label{display:grid;grid-template-columns:minmax(170px,1fr) 2fr;gap:1rem;margin:.6rem 0}input,select,textarea,button{font:inherit;padding:.45rem;max-width:100%;box-sizing:border-box}button{cursor:pointer}#status{white-space:pre-wrap;padding:.8rem;background:#e6edf7}small{display:block;color:#4b5870}.row{display:flex;gap:.5rem;flex-wrap:wrap}@media(max-width:580px){label{grid-template-columns:1fr;gap:.1rem}}</style></head><body>
<a href="/">← Approaching riders</a><h1>Lapsrv settings</h1><small>CrossMgr is read-only. The early reader feeds lapsrv only.</small>
<div class="row"><input id="admin" type="password" placeholder="Operator token (remote access only)" autocomplete="off"><button id="load">Load settings</button></div>
<p id="status">Loading…</p><form id="form">
<fieldset><legend>CrossMgr target</legend>
<label>Saved target<select id="target"></select></label>
<label>Save current target as<input id="name" required></label>
<label>MCP URL<input id="url" type="url" required></label>
<label>Bearer-token file<input id="token_file" placeholder="Path on the lapsrv host"></label>
<label>GUI instance (optional)<input id="instance"></label>
<label>Current GUI race path (optional)<input id="race_path"></label>
<label>Race timezone<input id="timezone" required></label>
<details><summary>Gateway aliases and timezone override</summary><label>Timezone file (optional)<input id="timezone_file" placeholder="Local tzfile fallback for naive timestamps"></label><label>Canonical → gateway names<textarea id="tool_names" rows="4"></textarea></label><small>Include race.roster, race.review, bridge.identity and bridge.snapshot when using renamed gateway tools.</small></details>
</fieldset><fieldset><legend>Race source</legend>
<label>Source<select id="mode"><option value="current">Current CrossMgr GUI race</option><option value="saved">Saved CMN on MCP host</option></select></label>
<label>Saved CMN path<input id="saved_race_path"></label>
<label>Refresh interval (seconds)<input id="poll_seconds" type="number" min="1" max="120" step="1"></label>
</fieldset><fieldset><legend>Receiver and display</legend>
<label>RFID bind address<input id="listen_host"></label><label>RFID port<input id="port" type="number" min="1" max="65535"></label>
<label>Web bind address<input id="web_host"></label><label>Web port<input id="web" type="number" min="1" max="65535"></label>
<label>Health-check hosts (up to 3)<input id="ip_address" placeholder="Space-separated addresses"></label>
<label>Group gap (seconds)<input id="group_gap_seconds" type="number" min="0" step="0.1"></label>
<label>Group retention (seconds)<input id="group_max_age_seconds" type="number" min="1"></label>
<label>Show unknown EPCs<input id="show_unknown_tags" type="checkbox"></label>
<label>Disable Tk display<input id="no_gui" type="checkbox"></label>
<label>Export directory<input id="export_dir"></label>
<label>Log level<select id="log_level"><option>DEBUG</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select></label>
</fieldset><div class="row"><button type="submit">Save and apply</button><button id="refresh" type="button">Refresh current race now</button></div>
<small>Receiver/web bind addresses, ports, health-check hosts, Tk visibility and export directory take effect after restarting lapsrv. Other settings apply without restarting the receiver.</small></form>
<script>
let settings=null,revision=null;
const $=id=>document.getElementById(id), text=id=>$(id).value;
const fields=['mode','saved_race_path','poll_seconds','listen_host','port','web_host','web','group_gap_seconds','group_max_age_seconds','show_unknown_tags','no_gui','export_dir','log_level'];
const targetFields=['url','token_file','instance','race_path','timezone','timezone_file'];
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-Lapsrv-Admin':text('admin'),...options.headers}});if(!r.ok)throw new Error(await r.text());return await r.json();}
function target(){const p=settings.targets[text('target')];$('name').value=text('target');for(const f of targetFields)$(f).value=p[f]||'';$('tool_names').value=JSON.stringify(p.tool_names||{},null,2);}
async function load(){try{const d=await api('/api/settings');settings=d.settings;revision=d.revision;$('target').replaceChildren(...Object.keys(settings.targets).map(n=>new Option(n,n)));$('target').value=settings.selected_target;target();for(const f of fields){if($(f).type==='checkbox')$(f).checked=!!settings[f];else $(f).value=settings[f];}$('ip_address').value=settings.ip_address.join(' ');$('status').textContent='Settings loaded. Token contents are never stored here.'+(d.restart_required.length?' Restart required: '+d.restart_required.join(', '):'');}catch(e){$('status').textContent=e.message;}}
$('target').onchange=target;$('load').onclick=load;
$('form').onsubmit=async e=>{e.preventDefault();try{if(!settings)throw new Error('Load settings first');const data=structuredClone(settings);for(const f of fields)data[f]=$(f).type==='checkbox'?$(f).checked:$(f).type==='number'?Number(text(f)):text(f);data.ip_address=text('ip_address').trim().split(/\s+/).filter(Boolean);const name=text('name').trim();if(!name)throw new Error('Enter a target name');data.targets[name]=Object.fromEntries(targetFields.map(f=>[f,text(f)]));data.targets[name].tool_names=JSON.parse(text('tool_names')||'{}');data.selected_target=name;const r=await api('/api/settings',{method:'POST',body:JSON.stringify({settings:data,revision})});await load();$('status').textContent='Saved. CrossMgr connection is refreshing.'+(r.restart_required.length?' Restart required: '+r.restart_required.join(', '):'');}catch(e){$('status').textContent=e.message;}};
$('refresh').onclick=async()=>{try{await api('/api/settings/refresh',{method:'POST',body:'{}'});$('status').textContent='Refreshing CrossMgr…';}catch(e){$('status').textContent=e.message;}};load();
</script></body></html>'''


class SettingsWeb:
    def __init__(self,store,started,on_change,on_refresh):self.store=store;self.started=started;self.on_change=on_change;self.on_refresh=on_refresh
    def restart(self):
        from lapsrv_config import RESTART_FIELDS
        current=self.store.snapshot();return [f for f in RESTART_FIELDS if current[f]!=self.started[f]]
    def routes(self,app):
        app.router.add_get('/settings',self.page);app.router.add_get('/api/settings',self.get);app.router.add_post('/api/settings',self.post);app.router.add_post('/api/settings/refresh',self.refresh)
    async def page(self,request):return web.Response(text=SETTINGS_HTML,content_type='text/html',headers={'Cache-Control':'no-store','X-Frame-Options':'DENY'})
    async def get(self,request):
        authorized(request,self.store);data,revision=self.store.read()
        return web.json_response(dict(settings=data,revision=revision,restart_required=self.restart()),headers={'Cache-Control':'no-store'})
    async def post(self,request):
        authorized(request,self.store)
        try:
            payload=await request.json();self.store.save(payload['settings'],expected_revision=payload['revision']);self.on_change()
        except (ValueError,TypeError,KeyError) as exc:raise web.HTTPBadRequest(text=str(exc)) from None
        return web.json_response(dict(ok=True,revision=self.store.revision,restart_required=self.restart()))
    async def refresh(self,request):authorized(request,self.store);self.on_refresh();return web.json_response(dict(ok=True))


def tk_settings(parent,store,on_change):
    import tkinter as tk
    from tkinter import ttk,messagebox
    data,revision=store.read();window=tk.Toplevel(parent);window.title('Lapsrv settings');window.geometry('710x720')
    body=ttk.Frame(window,padding=12);body.pack(fill='both',expand=True)
    values={};target_keys=('url','token_file','instance','race_path','timezone')
    def field(name,label,value,row):
        ttk.Label(body,text=label).grid(row=row,column=0,sticky='w',pady=2);var=tk.StringVar(value=str(value));entry=ttk.Entry(body,textvariable=var);entry.grid(row=row,column=1,sticky='ew',pady=2);values[name]=var
    profile=tk.StringVar(value=data['selected_target']);picker=ttk.Combobox(body,textvariable=profile,values=list(data['targets']),state='readonly');picker.grid(row=0,column=1,sticky='ew');ttk.Label(body,text='Saved target').grid(row=0,column=0,sticky='w')
    field('name','Save current target as',data['selected_target'],1)
    for i,key in enumerate(target_keys,2):field(key,key.replace('_',' ').title(),data['targets'][profile.get()].get(key,''),i)
    def selected(event=None):
        values['name'].set(profile.get())
        for key in target_keys:values[key].set(data['targets'][profile.get()].get(key,''))
    picker.bind('<<ComboboxSelected>>',selected)
    keys=['mode','saved_race_path','poll_seconds','listen_host','port','web_host','web','group_gap_seconds','group_max_age_seconds','export_dir']
    for i,key in enumerate(keys,7):field(key,key.replace('_',' ').title(),data[key],i)
    field('ip_address','Health-check hosts',' '.join(data['ip_address']),17)
    unknown=tk.BooleanVar(value=data['show_unknown_tags']);nogui=tk.BooleanVar(value=data['no_gui'])
    ttk.Checkbutton(body,text='Show unknown EPCs',variable=unknown).grid(row=18,column=1,sticky='w');ttk.Checkbutton(body,text='Disable Tk on next start',variable=nogui).grid(row=19,column=1,sticky='w')
    def save():
        try:
            import copy
            result=copy.deepcopy(data)
            for key in keys:result[key]=float(values[key].get()) if key in ('poll_seconds','group_gap_seconds','group_max_age_seconds') else int(values[key].get()) if key in ('port','web') else values[key].get()
            result.update(ip_address=values['ip_address'].get().split(),show_unknown_tags=unknown.get(),no_gui=nogui.get())
            target=dict(data['targets'][profile.get()]);target.update({k:values[k].get() for k in target_keys});name=values['name'].get().strip();result['targets'][name]=target;result['selected_target']=name
            store.save(result,expected_revision=revision);on_change();window.destroy()
        except (ValueError,TypeError) as exc:messagebox.showerror('Settings',str(exc),parent=window)
    ttk.Button(body,text='Save and apply',command=save).grid(row=20,column=1,sticky='ew',pady=8)
    ttk.Label(body,text='Network listeners, health checks and export directory change on restart.\nGateway tool aliases and extra options are available at /settings.').grid(row=21,column=0,columnspan=2)
    body.columnconfigure(1,weight=1)
    return window
