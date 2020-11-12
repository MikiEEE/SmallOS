import sys, unittest

sys.path.append('..')

from SmallPackage.taskState import taskState

class test_taskState(unittest.TestCase):

	def test_update_and_retieval(self):
		state = taskState()
		data = {'mice':10,'men':'blob','blob':{'10':20}}

		blank_state = state.getState(None,'data')
		self.assertEqual(blank_state,dict())

		state.update(data,'data')
		new_state = state.getState()
		self.assertEqual(new_state, data)

		one_var = state.getState('men','data')
		self.assertEqual(data['men'],one_var)

		with self.assertRaises(KeyError) as test:
			one_var = state.getState('mmmmm')
			print(one_var)


	def test_Free(self):
		state = taskState()
		data = {'mice':10}

		isFree = state.isFree('mice','data')
		self.assertEqual(isFree, True)

		state.update(data)
		isFree = state.isFree('mice','data')
		self.assertEqual(isFree, False)

		state.free('mice','data')
		isFree = state.isFree('mice','data')
		self.assertEqual(isFree, True)
		



if __name__ == '__main__':
	unittest.main()