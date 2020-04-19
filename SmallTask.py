import time
import traceback

'''
The SmallOS project was made entirely for education purposes
and was made with the intent of being entirely opensource. 
Enjoy!
-Michael Emperador
'''

class Node():
    '''
    @class Node() - Holds no data on its own, 
        developed with the intent of being a super class
        and being inherited. 
        
        ***NOTE
        Whatever inherits this class will be given the support
        for this data so long as the nametags next and prev are
        are not taken. 
        ***
    '''
    next=None
    prev=None

    def __init__(self):
        self.next = None
        self.prev = None 
        return 





class placeHolder():
    #determines where task resumes in the event of a sigsuspend() call.

    def __init__(self):
        self.placeholder = 0 
        self.lastPlaceHolder = 0 
        self.timeKeeper = 0
        self.incrementor = 0
        self.isUsed = False
        return 


    def getPlace(self) -> bool:
        if self.isUsed == True:
            return False

        if self.timeKeeper == 0:
            self.isUsed = True
            return True 
        else:
            self.timeKeeper -= 1
            return False


    def setUpPlace(self):
        self.isUsed = False
        return


    def setPlaceholder(self):
        self.incrementor += 1
        self.timeKeeper = self.incrementor
        return 


    def getPlaceholder(self):
        return self.placeholder


    def placeHolderReset(self):
        self.placeholder = 0
        return





class smallSignals(placeHolder):

    def __init__(self, kwargs):
        self.signals = [0] * 5
        self.isWaiting = 0
        self.isSleep = 0
        self.wakeSigs = list()
        self.handlerVars = list()
        self.isWaiting = 0
        self.sleepTime = 0
        self.timeOfSleep = 0
        self.taskVars = list()

        super().__init__()
        if kwargs:
            if kwargs.get('handlers',False):
                self.handlers = kwargs['handlers']
            else: self.handlers = None
        return 

    
    def getSignals(self):
        '''
        @function getSignals() - returns the ID number
            of all the signals that have been recieved.
        @return - list - contains the number place's of all
            the signals recieved.
        '''
        recieved = list()
        for num, sig in enumerate(self.signals):
            if sig:
                recieved.append(num)
        return recieved


    def sendSignal(self,OS,pid,sig):
        '''
        @function sendSignal() - Sends signals to a task
            with a specific Process ID.
        @param OS - OSobj - OS object being used for its information of
            all the tasks.
        @param pid - int() - ID of process that will recieve the signals.
        @param sig - int() - Signal number to be sent to the process.
        @return - int() - -1 upon failure or incorrect signal entry
            and 0 upon success.
        '''
        if sig < len(self.signals) and sig > -1:
            task = OS.tasks.search(pid)
            if task == -1: return -1 
            task.acceptSignal(OS,sig)
            return 0
        return -1


    def acceptSignal(self, OS, sig):
        '''
        @function acceptSignal() - Allows the Task
            to recieve the signal. Makes sure the signal is valid
        @param sig - int() - signal to be accepted.
        @return - int() - 0 upon suceess, -1 upon failure.
        '''
        if sig < len(self.signals) and sig > -1:
            self.signals[sig] = 1
            if self.handlers:
                handlerTask = smallTask(self.priority,
                                        self.signalHandler,
                                        1, name='handler'
                                        ,parent=self)
                OS.fork(handlerTask)
            if sig in self.wakeSigs:
                self.isWaiting = 0
                self.isReady = 1
                self.wakeSigs.remove(sig)
            return 0
        else:
            return -1


    def sleep(self,OS,secs,*args):
        '''
        @function sleep() -  Suspends process and gives control
            back to the OS until the desired time has passed.
        @param OS - OSobj - OS object that manages processes and has
            all task information.
        @param secs - atleast the number of seconds for the task to be 
            sleep.
            *NOTE* Insert Negative one to wake up task in signal Handler with custom
                        Signal.
        @return 0 upon success, -1 upon an error.
        '''
        self.saveState(0, args)
        self.setPlaceholder()
        self.isSleep = 1
        if secs == -1:
            self.sleepTime = -1
        else:
            self.timeOfSleep = time.time()
            self.sleepTime = secs
        return 0

    def wake(self):
        self.isSleep = 0
        return


    def checkSleep(self):
        if self.isSleep == 1:
            if self.sleepTime == -1: return -1

            if time.time() - self.timeOfSleep >= self.sleepTime:
                self.isReady = 1
                self.isSleep = 0
                return self.priority
            else: 
                return -1
        else: 
            return -1


    def sigSuspendV2(self,OS, *argv):
        '''
        @function sigSuspendV2() - Suspends the task until the corresponding 
            signal is recieved. Then the thread is revisited in the next
            getPlace() code block. 
        @param OS - smallOS - OS object that manages tasks.
        @param argv - variables to be saved when the next placeholder
            is executed. 
        @return - void

        '''
        self.saveState(argv)
        #sig is assumed 1
        self.wakeSigs.append(1)
        self.isWaiting = 1
        self.isReady = 0
        self.setPlaceholder()
        return 


    def saveState(self,*argv):
        '''
        @function saveState() - Saves all the variables passed in
            to a list that can be retrieved with a getState() function
            call.
        @param argv - comma seperated variables to be saved. 
        @return - void 

        ***NOTE
            Soon to be deprecated because the state holder will be a dict(). 
        '''
        args = [x for x in argv]
        if len(args) > 0:
            self.taskVars.extend(args)
        return
    

    def getState(self):
        '''
        @function getVars() - Retrieves the previous state
        that was saved.
        @return - list - of variables saved from previous saveState() call.
        '''
        if len(self.taskVars) >= 1:
            return self.taskVars[0]
        else:
            return list()


    def signalHandler(self,OS,task):
        '''
        @function signalHandler() - calls the inputed signal handler functions.
            Clears all signals afterwards.
        @param OS - OSobj - OS object that manages processes and has
            all task information.
        @param task - handler task object, parent is passed into the
            added hanlder function
        @return 0 upon success, -1 upon a nonexistent handler.
        '''
        if self.handlers:
            self.handlers(OS,task.parent)
            status = 0
        else:
            self.signals = [0] * 5
            status = -1
        return status


    def checkSignal(self, sig):
        '''
        @function checkSignal() - Checks to see if the signal entered
            has been recieved. Sets the signal to zero after the signal has been checked.
        @sig - int - The signal to be checked. 
        @return - bool - True if the signal was recieved before and False if it was not.
        '''
        if self.signals[sig] == 1:
            self.signals[sig] = 0
            return True 
        else: 
            return False 





class smallTask(smallSignals, Node):
    '''
    @Class smallTask() - Object that contains Tasks contents: The routine,
        information, name, ID number, signals.
    '''


    def __init__(self,priority,routine,isReady,**kwargs):
        '''
        @function __init__() - initializes variables to be used
            during normal functions.
        @param priority - int() - assigned priority of the Task object when
            compared to by the OS
        @param routine - func(OSobj,self) - function to be perfomed during the running of
            the task.
        @param isReady - bool() - intialialize the task to be
            ready from the beginning when true.
        @kwargs-
            @arg name - str() - optional parameter, add name to the Task.
            @arg update - obj() - optional parameter, update function that
                interacts with task  ready state.
                ***NOTE: Class must contain updateOBJ.update()
                ***NOTE: Updates must also return a 1 to signal to the task
                    to be ready.
            @arg handler - func(OSobj,self,sig) - signal handler function to
                perform actions during the event of a signal being
                recieved.
            @arg parent - task() - parent task that spawned this current task
        '''
        self.pid =  0
        self.priority = priority
        self.routine = routine
        self.isReady = isReady
        self.isLocked = 0
        self.parent = None
        self.placeholder  = 0
        self.updateFunc = None

        super().__init__(kwargs)
        Node.__init__(self)

        if kwargs:
            if kwargs.get('name',False):
                self.name = kwargs['name']
            if kwargs.get('update',False):
                self.updateFunc = kwargs['update']
            if kwargs.get('parent',False):
                self.parent = kwargs['parent']
        return


    def excecute(self,OS):
        '''
        @function execute() - Checks to see if the task() is ready
            or locked. If the task() is not locked and ready the routine()
            function is executed.
        @return void
        '''
        if self.isReady and not self.isLocked:
            self.setUpPlace()
            self.isReady = 0
            result = self.routine(OS,self)
            return result   
        else:
            return -1


    def update(self):
        '''
        @function update() - calls the passed in update function()
            if the status returned from the update function is a 1
            then the isReady state is set to 1.
        @return - int - 0 for success
            and -1 for a non exsistent update function.
        '''

        # if self.isSleep == 1 or self.isWaiting == 1:
        #     return 0
        if self.updateFunc:
            if self.updateFunc.update() == 1:
                self.isReady = 1
                self.placeHolderReset()
            return 0
        else:
            return -1


    def setID(self, pid):
        '''
        @function setID() - sets the process ID of the task.
        @param pid - int - number to be assigned as the identifier
            of the task.
        @return void
        '''
        if isinstance(pid,int):
            self.pid = pid
        else:
            traceback.format_exc()
            raise TypeError('PID must be type Int')
        return


    def getID(self):
        '''
        @function getID() - returns the process ID
        @return pid -int- process identifier.
        '''
        return self.pid


    def getExeStatus(self):
        status = bool(False)
        status = bool(self.isReady == 1) and bool(self.isWaiting == 0)
        status = status and bool(self.isSleep == 0)
        return status 


    def getDelStatus(self):
        status = bool(False)
        status = bool(self.isReady == 0) and bool(self.isWaiting == 0)
        status = status and bool(self.isSleep == 0)
        return status 


    def stat(self):
        msg = "\nisReady={}\nisWaiting={}\nisSleep={}\n".format(self.isReady,
                                                    self.isWaiting,
                                                    self.isSleep)
        msg = str(self) + msg
        return msg


    def __str__(self):
        '''
        @function __str__() - returns the string reprsentation of the
            Task
        '''
        name =''
        if self.name == '':
            name = 'Unamed Process'
        else:
            name = self.name
        return 'PID={}, name={}, priority={},status={}'.format(self.pid,
                                                    name,
                                                    self.priority,
                                                    self.getExeStatus())



