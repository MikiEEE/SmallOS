import os
import sys 
import pdb  


class baseShell():

	def __init__(self):
		return 

	def run(self, OS, inpt):
		inpt_set = set(inpt.split())
		if 'sw' in inpt_set:
			# pdb.set_trace()
			OS.toggleTerminal()
			# OS.sPrint('CMD: ',end=' ')
			# OS.sPrint('\n\n\n\n\n')
		if 'stat' in inpt_set:
			if len(inpt_set) == 1:
				OS.sPrint(OS)
			elif len(inpt_set) == 2:
				task = OS.tasks.search(int(inpt.split()[-1]))
				OS.sPrint(task.stat())
			# OS.sPrint('CMD: ',end=' ')
		if 'count' in inpt_set:
			# pdb.set_trace()
			msg = ''.join([str(len(OS.tasks)),' process(es) running'])
			OS.sPrint(msg,'\n')
			# OS.sPrint('CMD: ',end=' ')
		if 'exit' in inpt_set:
			sys.exit(0)
		if 'kill' in inpt_set:
			OS.tasks.delete(int(inpt.split()[-1]))
		# if ''.join(inpt) != '':
		OS.sPrint('CMD: ')
		# print('',end='')
		return

