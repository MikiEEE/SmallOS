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
			# OS.smShellPrint('CMD: ',end=' ')
			# OS.smShellPrint('\n\n\n\n\n')
		if 'stat' in inpt_set:
			if len(inpt_set) == 1:
				OS.smShellPrint(OS)
			elif len(inpt_set) == 2:
				task = OS.tasks.search(int(inpt.split()[-1]))
				OS.smShellPrint(task.stat())
			# OS.smShellPrint('CMD: ',end=' ')
		if 'count' in inpt_set:
			# pdb.set_trace()
			msg = ''.join([str(len(OS.tasks)),' process(es) running'])
			OS.smShellPrint(msg,'\n')
			# OS.smShellPrint('CMD: ',end=' ')
		if 'exit' in inpt_set:
			sys.exit(0)
		if 'kill' in inpt_set:
			OS.tasks.delete(int(inpt.split()[-1]))
		# if ''.join(inpt) != '':
		OS.smShellPrint('CMD: ')
		# print('',end='')
		return

