"""Monthly continuity preserves every error and publishes only approved, valid snapshots."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import json, shutil, sqlite3, subprocess, sys, unittest, uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main_workbook as main
ROOT=Path(__file__).resolve().parents[1]

class MainWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.data=ROOT/'tests/results'/('main-'+uuid.uuid4().hex)
        self.data.mkdir(parents=True)
        with self.db() as c:
            c.execute('CREATE TABLE runs (id TEXT PRIMARY KEY,start TEXT,end TEXT,status TEXT,message TEXT,created TEXT,count INTEGER,points REAL,issues INTEGER,scheduled_day TEXT)')
            main.initialize(c)

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.data/'test.sqlite');c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    def row(self,day,category='Searching',points=1):
        r=['']*28;r[0]='New';r[1]='SAME-ORDER-123';r[6]=category
        r[10]=(date.fromisoformat(day)-date(1899,12,30)).days+.5
        r[14]=r[15]=int(r[10])
        r[13]=points;r[18]='Example Searcher';r[20]='Example Typer'
        r[22]='Search' if category=='Searching' else 'Type';r[23]=r[18] if r[22]=='Search' else r[20]
        return r

    def seed(self,start,end,rows,status='complete'):
        rid=uuid.uuid4().hex;folder=self.data/'runs'/rid;folder.mkdir(parents=True)
        collection=dict(start=start,end=end,count=len(rows),points=sum(r[13] for r in rows))
        for name,obj in [('payload.json',main.make_payload(ROOT,rows)),('collection.json',collection),('validation.json',dict(passed=True,**collection))]:
            (folder/name).write_text(json.dumps(obj),encoding='utf8')
        with self.db() as c:c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,start,end,status,'test','2026-10-04',len(rows),collection['points'],0,None))
        return rid

    def build(self,args,folder):
        result=subprocess.run([str(a) for a in args],capture_output=True,text=True)
        if result.returncode:raise ValueError(result.stdout+result.stderr)

    def choose(self,rid,add=True,runner=None):
        return main.decide(ROOT,self.data,self.db,runner or self.build,rid,add)

    def read(self,month):
        with self.db() as c:file=main.download(self.data,c,month)
        return json.loads((file.parent/'payload.json').read_text())['data'][1:]

    def test_same_order_on_two_days_and_identical_same_day_errors_are_all_kept(self):
        a=self.row('2026-10-01');b=self.row('2026-10-02','Typing',2)
        first=self.seed('2026-10-01','2026-10-01',[a,a.copy()])
        second=self.seed('2026-10-02','2026-10-02',[b])
        self.choose(first);result=self.choose(second)
        self.assertEqual(self.read('2026-10'),[a,a,b])
        self.assertEqual(result['books'][0]['count'],3);self.assertEqual(result['books'][0]['points'],4)
        self.choose(second);self.assertEqual(len(self.read('2026-10')),3)
        # Keep an output for the release's Microsoft Open XML validation step.
        fixture=ROOT/'tests/results'/('report-main-'+uuid.uuid4().hex);fixture.mkdir()
        with self.db() as c:shutil.copy2(main.download(self.data,c,'2026-10'),fixture/'report.xlsx')
        print('MAIN_FIXTURE='+str(fixture/'report.xlsx'))

    def test_no_leaves_book_unchanged_then_yes_can_add_it(self):
        first=self.seed('2026-10-01','2026-10-01',[self.row('2026-10-01')]);self.choose(first)
        second=self.seed('2026-10-02','2026-10-02',[self.row('2026-10-02')])
        with self.db() as c:before=main.download(self.data,c,'2026-10')
        self.choose(second,False)
        with self.db() as c:self.assertEqual(main.download(self.data,c,'2026-10'),before)
        self.choose(second);self.assertEqual(len(self.read('2026-10')),2)

    def test_overlap_replaces_only_selected_days_without_order_deduplication(self):
        a=self.row('2026-10-01');b=self.row('2026-10-02');c=self.row('2026-10-03')
        self.choose(self.seed('2026-10-01','2026-10-03',[a,b,c]))
        changed=self.row('2026-10-02','Typing',3)
        self.choose(self.seed('2026-10-02','2026-10-02',[b,changed]))
        self.assertEqual(self.read('2026-10'),[a,b,changed,c])

    def test_empty_report_replaces_its_day_and_preserves_other_days(self):
        a=self.row('2026-10-01');b=self.row('2026-10-02')
        self.choose(self.seed('2026-10-01','2026-10-02',[a,b]))
        self.choose(self.seed('2026-10-01','2026-10-01',[]))
        self.assertEqual(self.read('2026-10'),[b])

    def test_cross_month_range_goes_to_the_correct_workbooks(self):
        a=self.row('2026-09-30');b=self.row('2026-10-01')
        self.choose(self.seed('2026-09-30','2026-10-01',[a,b]))
        self.assertEqual(self.read('2026-09'),[a]);self.assertEqual(self.read('2026-10'),[b])

    def test_build_failure_does_not_publish_any_partial_month_or_decision(self):
        first=self.seed('2026-09-30','2026-09-30',[self.row('2026-09-30')]);self.choose(first)
        with self.db() as c:before=main.books(c)
        rid=self.seed('2026-09-30','2026-10-01',[self.row('2026-09-30'),self.row('2026-10-01')])
        def fail_second_month(args,folder):
            if folder.parent.name=='2026-10':raise ValueError('Simulated build failure')
            self.build(args,folder)
        with self.assertRaisesRegex(ValueError,'Simulated'):self.choose(rid,runner=fail_second_month)
        with self.db() as c:
            self.assertEqual(main.books(c),before)
            self.assertIsNone(c.execute('SELECT * FROM main_choices WHERE run_id=?',(rid,)).fetchone())

    def test_unverified_or_out_of_range_source_is_rejected(self):
        failed=self.seed('2026-10-01','2026-10-01',[],status='failed')
        with self.assertRaisesRegex(ValueError,'verified'):self.choose(failed)
        bad=self.seed('2026-10-01','2026-10-01',[self.row('2026-10-02')])
        with self.assertRaisesRegex(ValueError,'outside'):self.choose(bad)
        with self.db() as c:self.assertEqual(main.books(c),[])

    def test_explicit_boolean_required_and_paths_rejected(self):
        for rid,add in [('a'*32,'yes'),('../runs',True)]:
            with self.assertRaises(ValueError):self.choose(rid,add)
        with self.db() as c:
            with self.assertRaises(ValueError):main.download(self.data,c,'../../runs')

if __name__=='__main__':unittest.main()
