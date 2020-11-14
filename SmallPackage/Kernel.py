import sys
import time




class Kernel():
	'''
	@class Kernel - This is a soft interface that should have implementations carried
		out in other classes.

	    This is where the System Call Interface will go. 
	    Example: if you were setting up a a2d module or PWM, put 
	    that in here. 
    '''

	def write(self,msg):
		pass

	def time_epoch(self):
		pass






class Unix(Kernel):

	'''
	For Unix like Systems. 
	'''
	def __init__(self):
		pass

	def write(self, msg):
		sys.stdout.write(msg) 
		sys.stdout.flush()
		return 

	def time_epoch(self):
		return time.time()






class ESP8266(Kernel):
	'''
	For Future 
	'''

	def __init__(self):
		pass




