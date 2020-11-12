import time
import sys
import traceback
import select

from .OSlist import OSList
from .SmallErrors import MaxProcessError



class SmallKernal():
    '''
    This is where the System Call Interface will go. 
    Example: if you were setting up a a2d module or PWM, put 
    that in here. 
    '''

    def __init__(self):
        pass






class SmallIO():
    '''
    @class smallIO() - controls print Input-Output 

    ***NOTE***
    This will probably be moved into the kernal class as a variable. 
    And will most likley be piped into the different processes on a terminal
    selection basis.

    TODO: Turn appPrintQueue into a circular buffer.
    '''

    def __init__(self):
        '''
        @fucntion __init__() - sets up the terminal toggle 
             and printqueuing veriables. 
        '''
        self.terminalToggle = False
        self.appPrintQueue = list()
        return 


    def print(self, *args):
        '''
        @function print() - Prints output to terminal for application display.
        @param *args - takes in arguments, does not automatically add newline.
        @return - void.
        '''
        msg = ''.join([str(arg) for arg in args])
        if self.terminalToggle == False:
            sys.stdout.write(msg) 
            sys.stdout.flush()
        elif len(self.appPrintQueue) < 1024:
            self.appPrintQueue.append(msg)
        else:
            self.appPrintQueue.pop(0)
            self.appPrintQueue.append(msg)
        return


    def sPrint(self, *args):
        '''
        @function sPrint() - Prints output to terminal for OS-related display.
        @param *args - takes in arguments, does not automatically add newline.
        @return - void.
        '''
        if self.terminalToggle == True:
            msg = ''.join([str(arg) for arg in args])
            sys.stdout.write(msg) 
            sys.stdout.flush()
        return


    def toggleTerminal(self):
        '''
        @function toggleTerminal() - Toggles the terminal from displaying application output
            to OS command output and vice-versa.
        @return - void.
        '''
        self.terminalToggle = not self.terminalToggle
        msg = ''.join('*' for x in range(16)) + '\n'
        sys.stdout.write(msg) 
        sys.stdout.flush()
        if self.terminalToggle == False:
            for num in range(len(self.appPrintQueue)):
                msg = self.appPrintQueue.pop(0)
                self.print(msg)
        return 








class SmallOS(SmallIO):
    '''
    @class - smallOS() - operating system api that manages and runs
        smallTasks()
    '''


    def __init__(self,size=2**10,**kwargs):
        '''
        @function __init__() - initializes the smallTask() list
            that will contain all of the tasks.
        @param tasks - list() - *optional parameter* list of small tasks
        '''
        self.sleepTasks = list()
        self.waitingTasks = list()
        self.wakeUpdate = list()
        self.shells = list()
        self.tasks = OSList(10,size)
        SmallIO.__init__(self)
        if kwargs:
            if kwargs.get('tasks',False):
                tasks = kwargs['tasks']
                self.fork(tasks)
            if kwargs.get('shells',False):
                shells = kwargs['shells']
                if isinstance(shells, list):
                    self.shells.extend(shells) 
                else:
                    self.shells.append(shells) 


    def start(self):
        '''
        @function start() - starts the OS
        @return void
        '''
        self.tasks.resetCatSel()
        cursor = self.tasks.pop()

        while len(self.tasks) != 0:

            if select.select([sys.stdin,],[],[],0.0)[0]:
                inpt = sys.stdin.readline()
                for shell in self.shells:
                    shell.run(self,inpt)

            update = cursor.update()
            result = -1   
            
            if cursor.getExeStatus():
                result = cursor.excecute()
            else:
                self.tasks.setCatSel(cursor.checkSleep())
            
            if update == -1 and result == 0 and cursor.getDelStatus():
                self.tasks.delete(cursor.pid)

            cursor = self.tasks.pop()

            if cursor == None: 
                self.tasks.resetCatSel()
                cursor = self.tasks.pop()
        return


    def fork(self,children):
        '''
        @function fork() - adds a task to the running tasks of the OS.
        @return - int() - upon success returns a positive integer upon,
             failure returns -1.
        '''
        if isinstance(children,list):
            ids = list()
            for item in childern:
                pid = self.tasks.insert(item)
                if pid != - 1: 
                    item.setOS(self)
                ids.append(pid)
        else:
            ids = self.tasks.insert(children)
            if ids != -1:
                children.setOS(self)
        return ids


    def __str__(self):
        '''
        @function __str__() - returns the string representation 
            of all the Tasks in the task list. 
        '''
        AllTasks = list(self.tasks.tasks)
        string = str()
        for count,routine in enumerate(AllTasks):
            string += str(count+1)+ '. ' + str(routine) + '\n'
        return string



if __name__ == '__main__':
        update21= updater1()
        # task_1 = smallTask(4,forkDemo,1,name='Parent', handlers=handler)
        OS = smallOS()
        # OS.addTasks([task_1])
        OS.start()
        print(OS)
