"""Empty TitleVision export validation must not hide changed or missing data."""
from pathlib import Path
import json,sys,tempfile,unittest,openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reconcile import reconcile,HEADERS

class ReconcileTests(unittest.TestCase):
 def fixture(self,folder,mutate=None):
  w=openpyxl.Workbook();w.active.title='SearchReport';w.active.append(['Results']);w.active.append(['No errors found'])
  c=w.create_sheet('SearchCriteria')
  for key,value in [('Originators',''),('Users',''),('Teams',''),('Start Date','9/27/2026 12:00:00 AM'),('End Date','9/28/2026 12:00:00 AM'),('Min Points',''),('Max Points',''),('Tasks',''),('Codes',''),('Deleted','Any'),('Commit Date Start',''),('Commit Date End',''),('Status','New, Accepted')]:c.append([key,value])
  if mutate:mutate(w)
  w.save(folder/'source.xlsx')
  (folder/'source.json').write_text('[]')
  (folder/'collection.json').write_text(json.dumps(dict(start='2026-09-27',end='2026-09-27',count=0,points=0)))
  (folder/'filters.json').write_text(json.dumps([dict(id='_uec_lstStatuses',value=['New','Accepted'])]))
 def test_verified_empty_export(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);self.fixture(p);reconcile(p)
   self.assertEqual(json.loads((p/'reconciled.json').read_text())['count'],0)
 def test_wrong_criteria_are_not_empty_proof(self):
  for cell,value in [('B4','9/26/2026 12:00:00 AM'),('B5','9/29/2026 12:00:00 AM'),('B13','New'),('B10','No'),('B1','one vendor')]:
   with self.subTest(cell=cell),tempfile.TemporaryDirectory() as t:
    p=Path(t);self.fixture(p,lambda w:w['SearchCriteria'].__setitem__(cell,value))
    with self.assertRaises(ValueError):reconcile(p)
 def test_missing_changed_or_extra_data_is_not_empty_proof(self):
  for mutate in [lambda w:w.active.append(['Unexpected row']),lambda w:w.active.__setitem__('B2','hidden data'),lambda w:w.remove(w['SearchCriteria']),lambda w:w.create_sheet('OtherData'),lambda w:w.active.__setitem__('A2','')]:
   with self.subTest(mutate=mutate),tempfile.TemporaryDirectory() as t:
    p=Path(t);self.fixture(p,mutate)
    with self.assertRaises(ValueError):reconcile(p)
 def test_source_rows_cannot_be_discarded_for_empty_export(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);self.fixture(p);(p/'source.json').write_text(json.dumps([{'values':['unexpected']*20}]))
   with self.assertRaises(ValueError):reconcile(p)
 def test_populated_export_preserves_duplicate_errors_and_schema_checks(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);row=['']*20;row[1]='Same order';row[9]='Full Title';row[12]='9/27/2026';row[15]='2'
   w=openpyxl.Workbook();w.active.append(HEADERS);w.active.append(row);w.active.append(row);w.save(p/'source.xlsx')
   (p/'source.json').write_text(json.dumps([{'values':row,'id':str(i)} for i in range(2)]));reconcile(p)
   self.assertEqual(len(json.loads((p/'source.json').read_text())),2)
   w.active['A1']='Unexpected Status';w.save(p/'source.xlsx')
   with self.assertRaises(ValueError):reconcile(p)
if __name__=='__main__':unittest.main()
