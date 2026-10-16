"""Provider-style custom/shared Docker network fixtures; no Docker/VM/network calls."""
import copy,unittest
from unittest.mock import Mock
from test_bootstrap_vm_identity import program

class NetworkTests(unittest.TestCase):
 def setUp(self):
  self.vm=program();self.item={'Id':'a'*64,'State':{'Running':True},'Config':{'Image':'fixture','User':'jovyan'},'Mounts':[{'Destination':'/home','RW':True}],'HostConfig':{'NetworkMode':'provider-private'},'NetworkSettings':{'Networks':{'provider-private':{'IPAddress':'172.18.0.8','NetworkID':'c'*64}}}}
  self.network={'Name':'provider-private','Id':'c'*64,'Driver':'bridge','Scope':'local','IPAM':{'Config':[{'Subnet':'172.18.0.0/16'}]}}
  self.inspect=Mock(return_value=[self.network])
 def run_case(self,items=None):return self.vm['private_container'](items or [self.item],'fixture',self.inspect)
 def test_named_bridge_requires_exact_driver_scope_id_and_subnet(self):
  self.assertEqual(self.run_case(),('a'*64,'172.18.0.8'));self.inspect.assert_called_once_with('provider-private')
 def test_shared_namespace_resolves_running_owner_but_preserves_model_container(self):
  owner=copy.deepcopy(self.item);owner.update(Id='b'*64,Name='/sidecar');owner['Config']={'Image':'other','User':'root'}
  self.item['HostConfig']['NetworkMode']='container:'+'b'*64;self.item['NetworkSettings']={'Networks':{}}
  self.assertEqual(self.run_case([self.item,owner]),('a'*64,'172.18.0.8'))
 def test_shared_namespace_name_and_host_namespace(self):
  owner=copy.deepcopy(self.item);owner.update(Id='b'*64,Name='/sidecar');owner['Config']={'Image':'other','User':'root'};owner['HostConfig']['NetworkMode']='host'
  self.item['HostConfig']['NetworkMode']='container:sidecar'
  self.assertEqual(self.run_case([self.item,owner]),('a'*64,'127.0.0.1'));self.inspect.assert_not_called()
 def test_unknown_or_cyclic_namespace_never_guessed(self):
  self.item['HostConfig']['NetworkMode']='container:missing'
  with self.assertRaises(ValueError):self.run_case()
  self.item['HostConfig']['NetworkMode']='container:'+'a'*64
  with self.assertRaisesRegex(ValueError,'CYCLE'):self.run_case()
 def test_non_bridge_driver_scope_and_wrong_network_identity_rejected(self):
  original=copy.deepcopy(self.network)
  for key,value in [('Driver','macvlan'),('Driver','overlay'),('Scope','swarm'),('Id','d'*64),('Name','other')]:
   self.network.clear();self.network.update(copy.deepcopy(original));self.network[key]=value
   with self.assertRaises(ValueError):self.run_case()
 def test_public_multiple_or_wrong_subnet_addresses_rejected(self):
  self.item['NetworkSettings']['Networks']['provider-private']['IPAddress']='8.8.8.8'
  with self.assertRaises(ValueError):self.run_case()
  self.item['NetworkSettings']['Networks']['provider-private']['IPAddress']='172.18.0.8';self.network['IPAM']['Config']=[{'Subnet':'10.0.0.0/8'}]
  with self.assertRaisesRegex(ValueError,'SUBNET'):self.run_case()
  self.item['NetworkSettings']['Networks']['other']={'IPAddress':'10.0.0.1'}
  with self.assertRaisesRegex(ValueError,'UNIQUE'):self.run_case()

if __name__=='__main__':unittest.main()
