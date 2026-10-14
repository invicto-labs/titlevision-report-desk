"""Dashboard counts must follow saved SP 2 rows without changing the workbook."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib,sys,unittest
import xlsxwriter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dashboard,report_layout

class DashboardTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.file=Path(self.temp.name)/'report.xlsx';dashboard._cache.clear()
 def workbook(self,teams,headers=None,points=None,dates=None):
  with xlsxwriter.Workbook(self.file) as wb:
   ws=wb.add_worksheet('SP 2');ws.write_row(0,0,headers or report_layout.HEADERS)
   for i,team in enumerate(teams,1):
    row=['']*27;row[0]='New';row[1]='SAME-ORDER';row[3]=team;row[12]='CA';row[13]=points[i-1] if points is not None else 0;row[10]=dates[i-1] if dates is not None else '2026-10-01'
    ws.write_row(i,0,row)
 def summary(self):
  with patch.object(dashboard,'workbook_path',return_value=(self.file,'shared')):return dashboard.summary(None,None,'2026-10')
 def test_all_errors_count_including_zero_points_duplicates_and_unknown_teams(self):
  self.workbook(['Search','Type','Typing','VM team','Leadership','Triage','','Custom'])
  before=self.file.read_bytes();r=self.summary()
  self.assertTrue(r['available']);self.assertEqual(r['total'],8)
  self.assertEqual({row['team']:row['count'] for row in r['rows']},{'Search':1,'Typing':2,'VM Team':1,'Leadership':1,'Triage':1,'Unassigned':1,'Other':1})
  self.assertEqual(before,self.file.read_bytes())
 def test_saved_team_edits_change_counts_without_manual_sync(self):
  self.workbook(['Search','Search']);self.assertEqual(self.summary()['rows'][0]['count'],2)
  self.workbook(['Typing','Search']);result=self.summary()
  self.assertEqual(result['rows'][0]['count'],1);self.assertEqual(result['rows'][1]['count'],1);self.assertEqual(result['total'],2)
 def test_missing_or_corrupt_shared_file_does_not_return_cached_totals(self):
  self.workbook(['Search']);self.assertTrue(self.summary()['available']);self.file.unlink()
  self.assertFalse(self.summary()['available']);self.file.write_bytes(b'not an xlsx');self.assertFalse(self.summary()['available'])
 def test_empty_workbook_shows_real_zero_totals(self):
  self.workbook([]);r=self.summary();self.assertTrue(r['available']);self.assertEqual(r['total'],0);self.assertEqual(len(r['rows']),5)
 def test_old_header_spelling_remains_readable(self):
  self.workbook(['Type'],report_layout.PREVIOUS_HEADERS);self.assertEqual(self.summary()['rows'][1]['count'],1)
 def test_invalid_schema_and_team_formulas_are_unavailable(self):
  self.workbook(['Search'],['Changed']*27);self.assertFalse(self.summary()['available'])
  self.workbook(['=1+1']);self.assertFalse(self.summary()['available'])
 def test_read_during_save_fails_instead_of_showing_mixed_snapshot(self):
  self.workbook(['Search'])
  with patch.object(dashboard,'signature',side_effect=[(1,100,1),(2,100,2)]):
   with self.assertRaisesRegex(ValueError,'being saved'):dashboard.read_file(self.file)
 def test_network_error_never_falls_back_to_local(self):
  with patch.object(dashboard,'workbook_path',side_effect=OSError('Network unavailable')):
   r=dashboard.summary(None,None,'2026-10');self.assertFalse(r['available']);self.assertNotIn('total',r)
 def test_invalid_month_cannot_select_a_path(self):
  with self.assertRaises(ValueError):dashboard.workbook_path(None,None,'../../file')
 def test_points_and_latest_created_date_include_duplicates_and_zero_points(self):
  self.workbook(['Search','Typing','VM Team','Search','','Custom'],points=[1.1,2.2,0,3,2,4],dates=['2026-10-02','2026-10-03','2026-10-03','2026-10-01','2026-10-03','2026-10-02'])
  r=self.summary();self.assertEqual(r['points'],12.3);self.assertEqual(r['total'],6)
  self.assertEqual(r['rows'][0]['points'],4.1)
  self.assertEqual(r['latest']['date'],'2026-10-03');self.assertEqual(r['latest']['total'],3);self.assertEqual(r['latest']['points'],4.2)
  self.assertEqual(r['latest']['rows'][2]['count'],1);self.assertEqual(r['latest']['rows'][2]['points'],0)
 def test_numeric_excel_dates_and_empty_latest(self):
  self.workbook(['Search'],dates=[46296]);r=self.summary();self.assertEqual(r['latest']['date'],'2026-10-01')
  self.workbook([]);r=self.summary();self.assertIsNone(r['latest']['date']);self.assertEqual(r['points'],0);self.assertEqual(r['latest']['total'],0)
 def test_invalid_points_or_dates_do_not_show_incomplete_totals(self):
  for points,day in [('=1+2','2026-10-01'),(-1,'2026-10-01'),(1,'not a date')]:
   self.workbook(['Search'],points=[points],dates=[day]);self.assertFalse(self.summary()['available'])

if __name__=='__main__':unittest.main()
