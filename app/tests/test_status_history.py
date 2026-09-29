"""Decision columns use verified source identities, authors and chronological replies."""
from pathlib import Path
import copy,json,sys,tempfile,unittest,openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from status_history import fields
from reconcile import reconcile,HEADERS

def sample(status='Non-Chargeable',id='219795'):
 values=['']*20;values[0]=status;values[1]='SAME-ORDER';values[2]='ADS SP2';values[9]='Full Title';values[12]=values[16]=values[17]='8/3/2026';values[15]='0'
 order='example-order'
 return {'sourceId':id,'url':'https://tv.datatracetitle.com/OrderOverview.aspx?PublicOrderId='+order,'values':values,
  'statusHistory':{'schema':1,'sourceId':id,'orderId':order,'url':f'https://tv.datatracetitle.com/UserErrors.aspx?EditMode=Status&UserErrorId={id}&PublicOrderId={order}',
   'status':status,'vendor':'ADS SP2','vendorUsers':['ADSSP2_PerformanceModuleManager','brucec_ADSSP2'],
   'comments':[['8/4/2026 4:14:47 PM','ADSSP2_PerformanceModuleManager','Hello,\nPlease review and dispute the error accordingly.'],['8/5/2026 5:06:50 AM','brucec','Training, reason accepted']]}}

class StatusHistoryTests(unittest.TestCase):
 def test_confirmed_mapping_does_not_confuse_client_and_vendor_accounts(self):
  r=sample();self.assertEqual(fields(r),['Disputed',r['statusHistory']['comments'][0][2],'Non-Chargeable','Training, reason accepted'])
  r['statusHistory']['comments'].insert(0,['8/4/2026 3:00:00 PM','brucec_ADSSP2','Earlier vendor note'])
  self.assertEqual(fields(r)[3],'Training, reason accepted')
 def test_status_comes_from_source_not_comment_keywords(self):
  r=sample('Chargeable');self.assertEqual(fields(r)[2],'Chargeable');self.assertEqual(fields(r)[3],'Training, reason accepted')
  r=sample('Disputed');self.assertEqual(fields(r),['Disputed',r['statusHistory']['comments'][0][2],'',''])
  for status in ['Accepted','Auto-Accepted']:
   r=sample(status);self.assertEqual(fields(r),[status,r['statusHistory']['comments'][0][2],'',''])
 def test_final_without_vendor_comment_does_not_invent_a_dispute(self):
  r=sample();r['statusHistory']['comments'].pop(0);self.assertEqual(fields(r),['','','Non-Chargeable','Training, reason accepted'])
  r['statusHistory']['comments']=[];self.assertEqual(fields(r),['','','Non-Chargeable',''])
 def test_external_note_before_vendor_challenge_is_not_a_final_reply(self):
  r=sample();r['statusHistory']['comments'][1][0]='8/3/2026 5:06:50 AM'
  self.assertEqual(fields(r),['Disputed',r['statusHistory']['comments'][0][2],'Non-Chargeable',''])
 def test_latest_reply_sorted_by_date_and_ignores_later_vendor_followup(self):
  r=sample();h=r['statusHistory'];h['comments']=[['8/6/2026 3:00:00 PM','ADSSP2_PerformanceModuleManager','Thank you'],*reversed(h['comments'])]
  self.assertEqual(fields(r)[1],h['comments'][2][2])
  h['comments'].append(['8/7/2026 1:00:00 AM','ChristieR','Revised final reply']);self.assertEqual(fields(r)[3],'Revised final reply');self.assertEqual(fields(r)[1],'Thank you')
 def test_identity_status_vendor_schema_and_conflicting_comments_fail(self):
  for mutate in [lambda h:h.update(sourceId='other'),lambda h:h.update(orderId='other'),lambda h:h.update(url=h['url'].replace('219795','219796')),lambda h:h.update(status='Disputed'),lambda h:h.update(vendor='Other'),lambda h:h.update(schema=2),lambda h:h.update(vendorUsers=[]),lambda h:h['comments'].append(['bad date','brucec','Bad']),lambda h:h['comments'].append(['8/5/2026 5:06:50 AM','ChristieR','Conflicting final'])]:
   r=sample();mutate(r['statusHistory'])
   with self.subTest(record=r),self.assertRaises(ValueError):fields(r)
 def test_old_reports_readable_but_fresh_final_snapshots_require_history(self):
  r=sample();r.pop('statusHistory');self.assertEqual(fields(r),['']*4)
  with self.assertRaises(ValueError):fields(r,required=True)
  r['values'][0]='New';self.assertEqual(fields(r,required=True),['']*4)
 def test_native_export_reconciliation_derives_fields_without_losing_duplicate_orders(self):
  with tempfile.TemporaryDirectory() as temp:
   folder=Path(temp);source=[sample(id='1'),sample('Chargeable',id='2')]
   w=openpyxl.Workbook();w.active.append(HEADERS)
   for r in source:w.active.append(r['values'])
   w.save(folder/'source.xlsx');(folder/'source.json').write_text(json.dumps(source),encoding='utf8')
   (folder/'collection.json').write_text(json.dumps({'statusHistoryVersion':1}),encoding='utf8')
   reconcile(folder);actual=json.loads((folder/'source.json').read_text(encoding='utf8'))
   self.assertEqual([r['sourceId'] for r in actual],['1','2']);self.assertEqual([r['statusFields'][2] for r in actual],['Non-Chargeable','Chargeable'])
   self.assertEqual(actual[0]['statusFields'][1],source[0]['statusHistory']['comments'][0][2])
   source[0].pop('statusHistory');(folder/'source.json').write_text(json.dumps(source),encoding='utf8')
   with self.assertRaises(ValueError):reconcile(folder)

if __name__=='__main__':unittest.main()
