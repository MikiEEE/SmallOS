import sys
sys.path.append('..')

from nose.tools import assert_raises
from SmallPackage.list_util.binSearchList import search, insert
from SmallPackage.SmallTask import smallTask


class element():
	def __init__(self, num):
		self.num = num


def buildList(func):
	testList = range(1000)
	def wrapper():
		func(testList)
		return
	return wrapper


def buildSpecialList(func):
	testList = [element(num) for num in range(1000)]
	def wrapper():
		func(testList)
		return
	return wrapper


	

@buildList
def test_search_outOfBound(testList):
	#test for index above range
	length = len(testList) + 1
	target = length
	assert_raises(IndexError,search,testList,target,0,length)

	#test for index out of range
	length -= 1
	target = -1
	assert_raises(IndexError,search,testList,target,-1,length)
	return 


@buildList
def test_search_there(testList):
	#test for all elements when in the list.
	length = len(testList)
	for num in testList:
		result = search(testList,num,0,length)
		assert testList[result] == num
	return 


@buildList
def test_search_notThere(testList):
	#tests for when elements aren't in the list
	length = len(testList)
	for num in testList:
		result = search(testList,-1,0,length)
		assert result == -1
	return


@buildSpecialList
def test_search_lambda(testList):
	#test search functionality with a lambda extraction
	extract = lambda tList, index: tList[index].num
	length = len(testList)

	for num, obj in enumerate(testList):
		target = num
		result = search(testList,target,0,length,extract)
		assert result != -1
	return


@buildList
def test_insert_outOfBound(testList):
	#test for index above range
	length = len(testList) + 1
	target = length
	assert_raises(IndexError,insert,testList,target,0,length)

	#test for index out of range
	length -= 1
	target = -1
	assert_raises(IndexError,insert,testList,target,-1,length)
	return 	

@buildList
def test_insert(testList):
	length = len(testList)

	for num in range(2*length):



if __name__ == '__main__':
	testList = range(1000)
	length = len(testList) + 1
	target = length
	assert search(testList,target,0,length) == -1

