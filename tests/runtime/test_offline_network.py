import unittest
from harness.runtime.offline_network import offline_network_valid


class OfflineNetworkTests(unittest.TestCase):
    def test_distinct_namespace_loopback_only(self):
        header='header one\nheader two\n'
        lo=header+' lo: 0 0 0 0\n'
        self.assertTrue(offline_network_valid('net:[1]','net:[2]',lo))
        for args in [('net:[1]','net:[1]',lo),(None,'net:[2]',lo),
                     ('net:[1]','bad',lo),('net:[1]','net:[2]',header),
                     ('net:[1]','net:[2]',lo+' eth0: 0 0 0 0\n')]:
            self.assertFalse(offline_network_valid(*args))
