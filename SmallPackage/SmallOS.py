import sys
import traceback
import select

from .SmallIO import SmallIO
from .OSlist import OSList
from .SmallErrors import MaxProcessError






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
        self.kernel = None

        SmallIO.__init__(self, 1024)
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

            
            sleep_cursor = self.tasks.sleepList
            while sleep_cursor != None:
                if sleep_cursor.checkSleep() > 0:
                    sleep_cursor.wake()
                sleep_cursor = sleep_cursor.next

            if cursor != None:
                update = cursor.update() 

                result = -1  
                if cursor.getExeStatus():
                    result = cursor.excecute()
                
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
            for item in children:
                pid = self.tasks.insert(item)
                if pid != - 1: 
                    item.setOS(self)
                ids.append(pid)
        else:
            ids = self.tasks.insert(children)
            if ids != -1:
                children.setOS(self)
        return ids


    def setKernel(self, kernel):
        '''
        @function setKernel - set the api for IO and allocation
            of other resources.
        '''
        self.kernel = kernel
        return 


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
