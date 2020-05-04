import unittest, os, sys, time

sys.path.append('..')

from SmallPackage.OSlist import OSList
from SmallPackage.SmallTask import smallTask

tasks = OSList(10)

class test_OSlist(unittest.TestCase):


	def test_insert(self):
		for x in range(2**8):
			tasks.insert(smallTask(x % 10,None,1, name=str(x)))
		self.assertEqual([x for x in range(256)], [x.pid for x in tasks.list()])
		return 
		

	def test__popOrder(self):
		pass

	def test_searchFound(self):
		pass

	def test_searchNotFound(self):
		pass

	def test_pop(self):
		pass

	def test_deleteFound(self):
		pass

	def test_deleteNotFound(self):
		pass

	def test_incrementCat(self):
		pass

	def test_availCat(self):
		pass

	def test_availCatNone(self):
		pass

	def test_setCatAvail(self):
		pass

	def test_len(self):
		pass

	def test_str(self):
		pass

if __name__ == '__main__':
	unittest.main()
