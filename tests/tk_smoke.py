"""Run with xvfb-run: validate Tk edits and render the settings dialog."""
import os,tempfile,tkinter as tk
from pathlib import Path
from unittest.mock import patch
from PIL import ImageGrab
from lapsrv_config import SettingsStore
from lapsrv_settings import tk_settings

with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':directory+'/absent'}):
    store=SettingsStore(Path(directory)/'settings.json');store.save(store.snapshot())
    root=tk.Tk();root.withdraw();changed=[]
    window=tk_settings(root,store,lambda:changed.append(True));root.update()
    body=window.winfo_children()[0]
    def field(row):return next(w for w in body.grid_slaves(row=row,column=1) if w.winfo_class()=='TEntry')
    def enter(row,value):field(row).delete(0,'end');field(row).insert(0,value)
    button=body.grid_slaves(row=20,column=1)[0]
    enter(9,'invalid')
    with patch('tkinter.messagebox.showerror') as error:
        button.invoke();assert error.called
    assert not changed and window.winfo_exists()
    enter(9,'3');enter(1,'Sunday test');enter(2,'http://timing-laptop:8050/mcp')
    root.update()
    x,y=window.winfo_rootx(),window.winfo_rooty();ImageGrab.grab().crop((x,y,x+window.winfo_width(),y+window.winfo_height())).save('artifacts/settings-tk.png')
    button.invoke();assert changed
    saved=SettingsStore(store.path).snapshot();assert saved['selected_target']=='Sunday test' and saved['poll_seconds']==3
    root.destroy()
print('Tk passed: validation error is shown; named target and settings persist')
