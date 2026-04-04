import sys
import time
import select




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

	def sleep(self, secs):
		pass

	def io_wait(self, readables, writables, timeout=None):
		return [], []
	



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

	def sleep(self, secs):
		time.sleep(secs)
		return

	def io_wait(self, readables, writables, timeout=None):
		if not readables and not writables:
			if timeout and timeout > 0:
				time.sleep(timeout)
			return [], []
		ready_read, ready_write, _ = select.select(readables, writables, [], timeout)
		return ready_read, ready_write

	def socket_send(self, data):
		return 

	def socket_recv(self, buffer_size):
		return 
	
	def socket_bind(self,ip:str,port:int):
		return



class ESP8266(Kernel):
	'''
	For Future 
	'''

	def __init__(self):
		pass


