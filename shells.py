import os
import sys 
import pdb  


'''
This is just an example of a shell and I intend to make this much more
Robust


Shells must include the following function(s):
setOS() - Where the shell's reference to the OS is set. 

'''

class BaseShell():

	def __init__(self):
		return 
	
	def setOS(self,OS):
		self.OS = OS
		return

	async def run(self, inpt):
		inpt_set = set(inpt.split())
		if 'sw' in inpt_set:
			# pdb.set_trace()
			self.OS.toggleTerminal()
			# OS.sPrint('CMD: ',end=' ')
			# OS.sPrint('\n\n\n\n\n')
		if 'stat' in inpt_set:
			if len(inpt_set) == 1:
				self.OS.sPrint(self.OS)
			elif len(inpt_set) == 2:
				task = self.OS.tasks.search(int(inpt.split()[-1]))
				self.OS.sPrint(task.stat())
			# OS.sPrint('CMD: ',end=' ')
		if 'count' in inpt_set:
			# pdb.set_trace()
			msg = ''.join([str(len(self.OS.tasks)),' process(es) running'])
			self.OS.sPrint(msg,'\n')
			# OS.sPrint('CMD: ',end=' ')
		if 'exit' in inpt_set:
			sys.exit(0)
		if 'kill' in inpt_set:
			self.OS.tasks.search(int(inpt.split()[-1])).kill()
		# if ''.join(inpt) != '':

		if 'exec' in inpt_set:
			i = list(inpt.split())
			i = ' '.join(i[1:])
			exec(i)
		self.OS.sPrint('CMD: ')
		# print('',end='')
		return

