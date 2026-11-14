import asyncio,copy,datetime as dt,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import lapsrv
from lapsrv_config import SettingsStore,DEFAULTS
from lapsrv_mcp import MCPReader,source_key,epc,error_message


class ErrorMessageTests(unittest.TestCase):
    def test_nested_auth_failure_explains_target_credentials(self):
        import httpx
        request=httpx.Request('POST','http://timing:8050/mcp')
        response=httpx.Response(401,request=request)
        failure=httpx.HTTPStatusError('transport failure',request=request,response=response)
        group=ExceptionGroup('unhandled errors in a TaskGroup',[ExceptionGroup('nested',[failure])])
        detail=error_message(group)
        self.assertIn('401 Unauthorized',detail)
        self.assertIn('bearer-token file',detail)
        self.assertNotIn('TaskGroup',detail)


def fixture():
    settings=copy.deepcopy(DEFAULTS);settings['targets']['local']['timezone']='UTC'
    roster=dict(name='Race A',date='2026-11-13',state='running',start_time=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=100)).isoformat(),finish_time=None,is_time_trial=False,
        rows=[dict(bib=24,first_name='Brittany',last_name='Rider',team='Team',category='Wave',categories=['Wave','Women'],tags={'Tag':'000ABC','Tag2':'00DEF'}),dict(bib=7,first_name='Other',last_name='Rider',team='',category='Wave',categories=['Wave'],tags={'Tag':'000777'})],
        categories=[dict(name='Wave',wave=True,laps=3,start_offset='1:00'),dict(name='Women',wave=False,laps=None,start_offset='1:00')])
    review=dict(rows=[dict(bib=24,category='Wave',status='Finisher',first_time=None,position='1',calculated_times=[0,80,160],calculated_interpolation=[False,False,True],passings=[dict(seconds=80)],start_offset='1:00'),dict(bib=24,category='Women',status='Finisher',position='1',calculated_times=[0,20,100],calculated_interpolation=[False,False,True],passings=[dict(seconds=80)],start_offset='1:00')])
    return dict(roster=roster,review=review,settings=settings,origin=dict(instance='one',race_path='/races/a.cmn'))


class ConfigurationTests(unittest.TestCase):
    def test_private_atomic_roundtrip_profiles_and_revision(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':str(Path(d)/'absent')}):
            p=Path(d)/'settings.json';store=SettingsStore(p);data=store.snapshot();data['targets']['remote']=dict(data['targets']['local'],url='http://other:8050/mcp');data['selected_target']='remote'
            store.save(data,expected_revision=0);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertEqual(SettingsStore(p).snapshot()['selected_target'],'remote')
            with self.assertRaises(ValueError):store.save(data,expected_revision=0)
            invalid=copy.deepcopy(data);invalid['targets']['remote']['url']='http://secret:password@other/mcp'
            with self.assertRaises(ValueError):store.save(invalid)
            self.assertEqual(SettingsStore(p).snapshot(),data)
    def test_cli_is_optional_and_overrides_do_not_persist_unless_requested(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':str(Path(d)/'absent')}):
            p=Path(d)/'settings.json';args=lapsrv.build_arg_parser().parse_args(['--config',str(p),'--port','0','--no-gui'])
            store=lapsrv.configure(args);self.assertEqual(store.snapshot()['port'],0);self.assertEqual(SettingsStore(p).snapshot()['port'],53136)
            self.assertTrue(args.no_gui)
    def test_borrows_racevideo_profiles_but_never_token_contents(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'crossmgr.json';p.write_text(json.dumps(dict(selected_target='remote',targets={'remote':dict(url='http://remote:8050/mcp',token_file='/private/token',tool_names={'race.roster':'gateway_roster'})})))
            with patch.dict(os.environ,{'RACEVIDEO_CROSSMGR_CONFIG':str(p)}):
                store=SettingsStore(Path(d)/'lap.json');self.assertEqual(store.snapshot()['targets']['remote']['tool_names']['race.roster'],'gateway_roster')


class StateTests(unittest.TestCase):
    def state(self):
        state=lapsrv.SharedState(lapsrv.RaceConfig());state.mcp_required=True;return state
    def test_roster_includes_before_first_finish_multiple_tags_and_category_context(self):
        state=self.state();data=fixture();state.apply_mcp(data)
        self.assertEqual(state.config.riders_by_tag['ABC'].bib,'24');self.assertEqual(state.config.riders_by_tag['DEF'].bib,'24')
        self.assertEqual(state.config.riders_by_bib['7'].first_name,'Other')
        self.assertEqual(state.config.categories['Women'].race_laps,3)
        self.assertEqual(state.results_by_bib['24']['raceTimes'],[0,80,160]) # No second wave offset.
        passing=state.record_passing('000abc',dt.datetime.now().astimezone(),'early')
        self.assertEqual(passing.bib,'24');self.assertEqual(passing.name,'Brittany Rider');self.assertEqual(passing.category,'Women')
        self.assertTrue(state.mcp_ready)
    def test_ambiguous_epcs_do_not_silently_pick_a_rider(self):
        state=self.state();data=fixture();data['roster']['rows'][1]['tags']['Tag']='0abc';state.apply_mcp(data)
        self.assertNotIn('ABC',state.config.riders_by_tag);self.assertIsNone(state.record_passing('ABC',dt.datetime.now().astimezone()))
    def test_disconnect_never_uses_old_race_mapping_and_new_event_clears_runtime(self):
        state=self.state();data=fixture();state.apply_mcp(data);state.record_passing('ABC',dt.datetime.now().astimezone())
        state.invalidate_mcp('offline');self.assertIsNone(state.record_passing('ABC',dt.datetime.now().astimezone()))
        other=copy.deepcopy(data);other['origin']['race_path']='/races/b.cmn';other['roster']['rows'][0]['bib']=99;other['review']['rows']=[];state.apply_mcp(other)
        self.assertEqual(len(state.passings),0);self.assertEqual(state.config.riders_by_tag['ABC'].bib,'99')
    def test_stale_source_refuses_mapping_and_profile_rename_keeps_observations(self):
        state=self.state();data=fixture();state.apply_mcp(data)
        state.record_passing('ABC',dt.datetime.now().astimezone())
        renamed=copy.deepcopy(data);settings=renamed['settings'];settings['targets']['renamed']=settings['targets'].pop('local');settings['selected_target']='renamed'
        state.apply_mcp(renamed);self.assertEqual(len(state.passings),1)
        state.mcp_last_success-=state.mcp_max_age+1
        self.assertFalse(state.mcp_is_ready());self.assertIsNone(state.record_passing('ABC',dt.datetime.now().astimezone()))
    def test_source_utc_start_wins_over_workstation_timezone(self):
        state=self.state();data=fixture();data['roster'].update(start_time='2026-11-08T13:00:00',start_time_utc='2026-11-08T20:00:00+00:00')
        state.apply_mcp(data)
        self.assertEqual(state.mcp_race_start,dt.datetime(2026,11,8,20,tzinfo=dt.timezone.utc).timestamp())
    def test_time_trial_start_offset_and_finished_clock(self):
        state=self.state();data=fixture();data['roster']['is_time_trial']=True;data['review']['rows'][0]['first_time']=30
        state.apply_mcp(data);self.assertEqual(state.tt_start_offset('24'),30)
        data['roster']['state']='finished';start=dt.datetime.fromisoformat(data['roster']['start_time']);data['roster']['finish_time']=(start+dt.timedelta(seconds=200)).isoformat();state.apply_mcp(data)
        self.assertEqual(state.current_race_time(),200);self.assertIsNone(state.race_clock_wall)


class ReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_snapshot_roster_before_first_read_and_no_mutation_tools(self):
        client=MCPReader();data=fixture();settings=data['settings']
        identity=dict(instance='one',race_path='/races/a.cmn',state='running');snapshot=dict(identity,path='/private/live.cmn',snapshot_sha256='abc')
        inputs=[dict(path='/private/live.cmn',sha256='abc')]
        roster=dict(inputs=inputs,race=dict(data['roster'],total=2));review=dict(inputs=inputs,race=dict(data['review'],total=2))
        client.call=AsyncMock(side_effect=[identity,snapshot,roster,review])
        result=await client.fetch_session(object(),settings)
        self.assertEqual(result['roster']['rows'][1]['bib'],7)
        self.assertEqual([c.args[2] for c in client.call.call_args_list],['bridge.identity','bridge.snapshot','race.roster','race.review'])
        with self.assertRaisesRegex(ValueError,'read-only'):await MCPReader().call(object(),{},'bridge.apply',{})
    async def test_state_change_bypasses_nonrunning_snapshot_cache(self):
        client=MCPReader();data=fixture();settings=data['settings']
        identity=dict(instance='one',race_path='/races/a.cmn',state='running');snapshot=dict(identity,path='/private/live.cmn',snapshot_sha256='abc')
        roster=dict(inputs=[],race=dict(data['roster'],total=2));review=dict(inputs=[],race=dict(data['review'],total=2))
        client.call=AsyncMock(side_effect=[identity,snapshot,roster,review]);await client.fetch_session(object(),settings)
        ended=dict(identity,state='finished');finished=copy.deepcopy(roster);finished['race']['state']='finished'
        client.call=AsyncMock(side_effect=[ended,dict(snapshot,state='finished',snapshot_sha256='def'),finished,review])
        result=await client.fetch_session(object(),settings)
        self.assertEqual(result['roster']['state'],'finished');self.assertEqual(client.call.await_count,4)
    async def test_unstarted_race_loads_roster_without_review_that_requires_passings(self):
        client=MCPReader();data=fixture();data['roster'].update(state='unstarted',start_time=None)
        identity=dict(instance='one',race_path='/races/a.cmn',state='unstarted');snapshot=dict(identity,path='/private/live.cmn',snapshot_sha256='abc')
        client.call=AsyncMock(side_effect=[identity,snapshot,dict(inputs=[],race=dict(data['roster'],total=2))])
        result=await client.fetch_session(object(),data['settings']);self.assertEqual(result['review']['rows'],[])
    async def test_workbook_changes_and_cross_race_switch_are_rejected(self):
        data=fixture();identity=dict(instance='one',race_path='/races/a.cmn',state='running');snap=dict(identity,path='/private/s.cmn',snapshot_sha256='abc')
        client=MCPReader();client.call=AsyncMock(side_effect=[identity,snap,dict(inputs=['a'],race=dict(data['roster'],total=2)),dict(inputs=['b'],race=dict(data['review'],total=2))])
        with self.assertRaisesRegex(ValueError,'Workbook changed'):await client.fetch_session(object(),data['settings'])
        client.call=AsyncMock(side_effect=[identity,dict(snap,race_path='/races/b.cmn')])
        with self.assertRaisesRegex(ValueError,'changed race'):await client.fetch_session(object(),data['settings'])
