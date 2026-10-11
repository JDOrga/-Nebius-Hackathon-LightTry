"""OFFLINE archive byte safety, not Cosmos image evidence."""
import io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from next.runtime.export_product_chunks import payload,combine,PARTS
class ProductChunkTests(unittest.TestCase):
 def test_exact_union_keeps_proof_gbuffers_canonical_not_duplicate_or_tensor(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'run';root.mkdir();cases={'result.jpg':b'SYNTHETIC_NOT_GPU','presets/0/'+('a'*32)+'/relit_frames_0000/photo.jpg':b'SYNTHETIC_NOT_GPU','receipt.json':b'{}','execution.json':b'{}','parameter-proof.json':b'{}','presets/0/flat.jpg':b'DUPLICATE_FLAT','presets/0/tensor.npz':b'TENSOR','presets/0/env_ldr.png':b'BITMAP'}
   for label in ('basecolor','normal','depth','roughness','metallic'):cases['inverse/gbuffer_frames/photo.'+label+'.jpg']=label.encode()
   for name,data in cases.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
   paths=[]
   for part in PARTS:
    data=payload(root,part);self.assertLessEqual(len(data),163840);p=Path(tmp)/(part+'.tar.gz');p.write_bytes(data);paths.append(p)
   merged=Path(tmp)/'merged.tar.gz';record=combine(paths,merged);self.assertEqual(record['parts'],5)
   with tarfile.open(merged,'r:gz') as tar:
    self.assertEqual(set(tar.getnames()),set(cases)-{'presets/0/flat.jpg','presets/0/tensor.npz','presets/0/env_ldr.png'})
   with self.assertRaises(FileExistsError):combine(paths,merged)
   with self.assertRaises(ValueError):payload(root,'../secret')
 def test_canonical_mismatch_and_duplicate_reject(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'a.tar.gz'
   with tarfile.open(p,'w:gz') as tar:
    info=tarfile.TarInfo('receipt.json');info.size=2;tar.addfile(info,io.BytesIO(b'{}'))
   with self.assertRaises(ValueError):combine([p,p],Path(tmp)/'bad.tar.gz')
if __name__=='__main__':unittest.main()
