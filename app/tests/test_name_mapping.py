from pathlib import Path
import json,sys,unittest,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import name_mapping


class NameMappingTests(unittest.TestCase):
 def test_install_and_role_specific_lookup(self):
  folder=Path(__file__).resolve().parent/'results'/('roster-'+uuid.uuid4().hex);folder.mkdir(parents=True)
  config={'schema':2,'search':{'kishorek':{'id':'INV060','name':'Kishore R'}},'type':{'deepikak':{'id':'INV160','name':'Kanna Deepika'}},'legacy':{'unknown':'Existing Name'}}
  result=name_mapping.install(folder,json.dumps(config).encode())
  self.assertEqual((result['searchAliases'],result['typingAliases']),(1,1))
  loaded=name_mapping.load(folder)
  self.assertEqual(name_mapping.mapped(loaded,'KishoreK_ADSSearchType','Search'),'Kishore R')
  self.assertEqual(name_mapping.mapped(loaded,'KishoreK_ADSSearchType','Type'),'Kishore R')
  self.assertEqual(name_mapping.mapped(loaded,'DeepikaK_ADSSearchType','Type'),'Kanna Deepika')
  self.assertEqual(name_mapping.mapped(loaded,'Unknown_ADSSearchType','Search'),'Existing Name')
  self.assertIsNone(name_mapping.mapped(loaded,'NotListed_ADSSearchType','Search'))
  self.assertTrue(name_mapping.summary(folder)['loaded'])
  config['search']['kishorek']['name']='=HYPERLINK("unsafe")'
  with self.assertRaisesRegex(ValueError,'name is invalid'):name_mapping.install(folder,json.dumps(config).encode())
  self.assertEqual(name_mapping.mapped(name_mapping.load(folder),'KishoreK_ADSSearchType','Search'),'Kishore R')


if __name__=='__main__':unittest.main()
