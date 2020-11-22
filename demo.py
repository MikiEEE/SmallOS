from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask
from SmallPackage.Kernel import Unix
from shells import baseShell

import pdb

def update(self):

    #Retrieve the system state from the datastore. 
    data, status = self.state.getState('update','system')

    if status != 0:

        #if update dict is not in the system's data 
        # add it along with the first data entry.

        time_start = self.OS.kernel.time_epoch()
        data = {'update':time_start}

        #Make sure the system namespace has been chosen 
        #to avoid clashing.
        self.state.update(data, 'system')
        return 0

    #Get the old and new values and subtract them to 
    #see if one second has passed.
    new_time = self.OS.kernel.time_epoch()
    previous_time = data

    #If one second has passed return one 
    #signaling that the task will be reactivated.
    if new_time - previous_time > 1:
        data = {'update':new_time}
        self.state.update(data)
        return 1

    return 0







def handler(self):
    #Check to see if this signal has been triggered 
    #If it has do something.
    if self.checkSignal(2):
        self.OS.print('from:',self.name,'ouch','\n')
    return  







def send(self):
    #Sends a signal back to the parent task.
    parent = self.parent
    parent = parent.pid
    self.OS.print('Sending Signal \n')
    self.sendSignal(parent,1)
    return 






def forkDemo(self):
    '''
    @func Fork Demo - demonstrates using small os to be able to 
        switch between tasks and let routines be executed in the 
        middle of the main task.

        Allowing more concurrent code. 
    '''


    if self.pid == 0:
        #This function is being used by both the parent and child processes.
        #If this is the parent process enter this branch. 

        # if self.getPlace():
        #Number of process to be added.
        num_processes = 2**4
        for num in range (num_processes):

            #Establish process priority.
            priority = num%6+ 2

            #Establish routine to be run.
            func = forkDemo

            #Set Ready state(optional) assumed to be 1.
            isReady = 1

            #create the task. 
            task = SmallTask(priority,func,isReady=isReady,name=str(num))

            #Add the task to running process. 
            #NOTE the task.fork will set task to be the parent process.
            pid = self.fork(task)


        #Initiate Child Process to wake the parent process up.
        child = SmallTask(9,forkDemo,isReady=1,name='child')
        self.fork(child)

        #Suspend the parent task until the specified signal is recieved.
        self.OS.print('Parent is going to sleep','\n')
        yield self.sigSuspendV2(1)


        # elif self.getPlace():
        #Upon waking up the parent task
        self.OS.print('PARENT Done', '\n')


    elif self.name == 'child':
        #This loop is entered when the process 
        #named child calls uses this function.
        print('sending')
        self.sendSignal(0,1)


    else:
        #All of the tasks created in the loop 
        #that the parent task iterates through
        #will go into this section of code since 
        #their pids are not 0 and their name is 
        #not child.

        self.OS.print(self.parent,'\n')
        self.sendSignal(0,2)
    return







def pHDemo(self):

    # if self.getPlace():
    self.OS.print('First Phrase','\n')
    child = self.OS.fork(SmallTask(8,send,isReady=1,parent=self,update=update, name='sender'))
    yield self.sigSuspendV2(1,{'child':child})

    # if self.getPlace():
    self.OS.print('Second \n')
    yield self.sigSuspendV2(1) 

    # if self.getPlace():
    self.OS.print('third \n')
    yield self.sigSuspendV2(1) 

    # if self.getPlace():
    self.OS.print('fourth \n')
    pid, status = self.state.getState('child')
    self.OS.tasks.delete(pid)
    return 







def sleepDemo( self):
    # if self.getPlace():
    self.OS.print('First Phrase','\n')
    # self.OS.fork(SmallTask(8,send,1,parent=self,update=update21), self)
    nums = [1,3,[5,7,9]]
    yield self.sleep(0,{'nums':nums})

    # if self.getPlace():
    self.OS.print('Second \n')
    yield self.sleep(0,{'nums':[1,4]})

    # if self.getPlace():
    self.OS.print('third \n')
    yield self.sleep(0,{'nums':[1,5]})

    # if self.getPlace():
    self.OS.print('fourth \n')
    return 







def sleepAndSuspendDemo( self):
    print('hello')
    if self.getPlace():
        self.OS.print('First Phrase','\n')
        self.fork(SmallTask(8,send))
        yield self.sigSuspendV2(1)

    if self.getPlace():
        self.OS.print('Second \n')
        yield self.sleep(1)

    if self.getPlace():
        self.OS.print('third \n')
        # self.sigSuspendV2( 0,1) 

    # if self.getPlace():
    #     self.OS.print('fourth \n')
    return 







#@task
def execDemo(self):
    cmd = '''self.OS.print('HELLO','\\n',self,'\\n')'''
    cmd = compile(cmd,'demo.py','exec')
    exec(cmd)
    return 





def loop_demo(self):
    for i in range(100):
        print(i)
        # yield self.sleep(3)
        if i == 50:
            self.OS.print('Sleeeping...','\n')
            yield self.sleep(.0001)




if __name__ == '__main__':
    import traceback

    #move baseShell into OS by default , output piping, make shell more robust, Describe each demo,
    #Make cleaner, add adjustable signal lengths, Turn Shell into own process
    #Turn OSlist into Balanced Bin Tree?
    #work through innerloops.
    #Create config file.
    #remove placeholder class


    #Priority is set to 2 to give higher priority (quick) system tasks
    #such as a2d reading input checking a chance to run quickly.  
    priority = 1

    base = baseShell()
    demo_1 = SmallTask(priority,forkDemo,isReady=1,name='Parent1', handlers=handler)
    demo_2 = SmallTask(priority,pHDemo, name='Parent2',handlers=handler)
    demo_3 = SmallTask(priority,sleepDemo, name='Parent3')
    demo_4 = SmallTask(priority,sleepAndSuspendDemo, name='Parent4')
    demo_5 = SmallTask(priority,execDemo,name='Parent5')
    demo_6 = SmallTask(priority+2,loop_demo,name='Parent6')
    
    #Instantiate and configure the OS.
    OS = SmallOS(shells=base)
    OS.setKernel(Unix())
    # pdb.set_trace()
    tasks = [demo_1,demo_2,demo_3,demo_4,demo_5]
    tasks = [demo_1,demo_6]
    # tasks = [demo_3]
    fails = list()
    OS.fork(tasks)
    # OS.addTasks([demo_4])
    OS.start()
    # for num, demo in enumerate(tasks):
    #     try:
    #         OS.fork(demo)
    #         OS.start()
    #     except: 
    #         print(traceback.format_exc())
    #         fails.append(num + 1)

    # if len(fails) == 0:
    #     print('ALL DEMOS COMPLETED SUCCESSFULLY')
    # else:
    #     print(fails)
    # self.OS.print('\n')

