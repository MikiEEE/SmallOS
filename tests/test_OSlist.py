import unittest, os, sys, time, copy

sys.path.append('..')

from SmallPackage.OSlist import OSList
from SmallPackage.SmallTask import SmallTask

tasks = OSList(10)

class test_OSlist(unittest.TestCase):


	def test_insert(self):
		for x in range(2**8):
			tasks.insert(SmallTask(x % 10,None, name=str(x)))
		self.assertEqual([x for x in range(256)], [x.pid for x in tasks.list()])
		

	def test__popOrder(self):
		result = list()
		current = tasks.pop()
		while current != None:
			result.append(current.priority)
			current.execute()
			print(current)
			current = tasks.pop()
		sort = copy.deepcopy(result)
		sort = sorted(sort, key=lambda x: x.priority)
		self.assertEqual(result,sort)


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
	# I am currently testing the functionality of moving 
	#something to and from the category list to the leep list so the os will
	# be able to check for awaken processes in the main loop.
	# 
	#I am running into the problem of pop repeats.

	tasks = OSList(10)

	secs = time.time()
	# for x in range(2**6):
	#     tasks.insert(smallTask(x % 10,None,1, name=str(x)))
	pid1 = tasks.insert(SmallTask(1,None, name=str(1)))
	pid2 = tasks.insert(SmallTask(2,None, name=str(2)))
	pid3 = tasks.insert(SmallTask(3,None, name=str(3)))
	pid4 = tasks.insert(SmallTask(4,None, name=str(4)))
	pid5 = tasks.insert(SmallTask(5,None, name=str(5)))

	for task in tasks.list()[1:]:
		tasks.moveToSleepList(task)

	# print([x.priority for x in tasks.cats])
	print([str(task) for task in tasks.list()])
	
	cursor = tasks.pop()

	while cursor != None:
	    cursor.isReady = 0
	    print('popping',cursor.name, cursor.getID(), cursor.priority)
	    print(tasks.catSelect)
	    tasks.delete(cursor.pid)
	    cursor = tasks.pop()

	print('*****')
	for task in tasks.list()[1:]:
		print(task.pid)
		tasks.notifyWake(task)


	cursor = tasks.pop()

	while cursor != None:
	    cursor.isReady = 0
	    print('popping',cursor.name, cursor.getID(), cursor.priority)
	    print(tasks.catSelect)
	    tasks.delete(cursor.pid)
	    cursor = tasks.pop()
	    time.sleep(.5)

	print(len(tasks))














