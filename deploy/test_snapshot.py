import importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('snapshot',Path(__file__).with_name('build_snapshot.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class SnapshotTest(unittest.TestCase):
 def test_dst_coverage_and_no_auth_export(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);db=root/'cache.sqlite';assets=root/'assets';assets.mkdir()
   for n in ['index.html','app.js','style.css','plotly.min.js']:(assets/n).write_text('fixture')
   with sqlite3.connect(db) as c:
    c.executescript('CREATE TABLE hours(contract TEXT,timestamp TEXT,kwh REAL,temperature_c REAL,quality TEXT);CREATE TABLE metadata(contract TEXT,payload TEXT);')
    c.executemany('INSERT INTO hours VALUES (?,?,?,?,?)',[('private-contract','2026-11-01T04:00:00+00:00',1,4,'R'),('private-contract','2026-11-02T04:00:00+00:00',2,4,'R')])
    c.execute('INSERT INTO metadata VALUES (?,?)',('private-contract',json.dumps({'password':'NEVER-EXPORT','access_token':'NEVER-EXPORT','rate':'D'})))
   mod.build(db,root/'out',assets)
   raw=(root/'out/data.json').read_text();data=json.loads(raw)
   self.assertEqual(data['expected']['2026-11-01'],25);self.assertEqual(len(data['hours']),2)
   self.assertNotIn('NEVER-EXPORT',raw);self.assertNotIn('private-contract',raw)
 def test_empty_cache_rejects_publication(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'db'
   with sqlite3.connect(p) as c:c.execute('CREATE TABLE hours(contract TEXT)')
   with self.assertRaises(ValueError):mod.build(p,Path(t)/'out',Path(t))
if __name__=='__main__':unittest.main()
