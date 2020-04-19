import time
import sys
import traceback
import select

from OSlist import OSList
from SmallErrors import MaxProcessError
'''
The SmallOS project was made entirely for education purposes
and was made with the intent of being entirely opensource. 
Enjoy!
-Michael Emperador
'''




class smallIO():


    def __init__(self):
        self.terminalToggle = False
        self.appPrintQueue = list()


    def smAppPrint(self, *args):
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


    def smShellPrint(self, *args):
        if self.terminalToggle == True:
            msg = ''.join([str(arg) for arg in args])
            sys.stdout.write(msg) 
            sys.stdout.flush()
        return


    def toggleTerminal(self):
        self.terminalToggle = not self.terminalToggle
        msg = ''.join('*' for x in range(16)) + '\n'
        sys.stdout.write(msg) 
        sys.stdout.flush()
        if self.terminalToggle == False:
            for num in range(len(self.appPrintQueue)):
                msg = self.appPrintQueue.pop(0)
                self.smAppPrint(msg)
        return 



class smallOS(smallIO):
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
        smallIO.__init__(self)
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


    def addTasks(self, newTasks):
        '''
        @function addTasks() - takes in a list of tasks
            and returns the respective ids. (IDS may be out of order)
        @param newTasks -  list of new smallTask()s to be added and managed
            by smallOS()
        @return list() - list of ids. ##May be out of order.
        '''
        ids = list()
        for item in newTasks:
                pid = self.tasks.insert(item)
                ids.append(pid)
        return ids


    def addTask(self, newTask):
        return self.tasks.insert(newTask)


    def start(self):
        '''
        @function start() - starts the OS
        @return void
        '''
        print('Starting...\n')
        control = 1
        while control == 1:
            self.runOS()
            taskNum = len(self.tasks)
            if taskNum == 0:
                control = 0
        return 


    def runOS(self):
        '''
        @function runOS() - calls the update function and then executes
            the tasks. In the event of no update function, the Task is deleted after successful
            completion.
        @return void 
        '''
        self.tasks.resetCatSel()
        cursor = self.tasks.pop()
        while cursor != None:
            if len(self.tasks) == 0: break

            if select.select([sys.stdin,],[],[],0.0)[0]:
                inpt = sys.stdin.readline()
                for shell in self.shells:
                    shell.run(self,inpt)

            update = cursor.update()
            result = -1   
            if cursor.getExeStatus():
                result = cursor.excecute(self)
            else:
                self.tasks.setCatSel(cursor.checkSleep())

            if update == -1 and result == 0 and cursor.getDelStatus():
                self.tasks.delete(cursor.pid)
            cursor = self.tasks.pop()
            
            # time.sleep(.4)
        return


    def deleteTask(self, pid):
        self.tasks.delete(pid)
        return 


    def fork(self,children):
        '''
        @function fork() - adds a task to the running tasks of the OS.
        @return - int() - upon success returns a positive integer upon,
             failure returns -1.
        '''
        if isinstance(children,list):
            ids = self.addTasks(children)
        else:
            ids = self.addTask(children)
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
