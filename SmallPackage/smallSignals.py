from .placeHolder import placeHolder

import time


class smallSignals(placeHolder):
    '''
    @class smallSignals - Class designed to handle all of the 
        signal oriented interprocess communication. 
    '''
    def __init__(self,OS,kwargs):
        '''
        @fucntion __init__() - Takes in kwargs and extracts the signal handler
            function. 
        '''

        #Need to add adjustable signals.
        self.signals = [0] * 32
        self.isWaiting = 0
        self.isSleep = 0
        self.wakeSigs = list()
        self.handlerVars = list()
        self.isWaiting = 0
        self.sleepTime = 0
        self.timeOfSleep = 0
        self.OS = OS
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


    def sendSignal(self,pid,sig):
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
            task = self.OS.tasks.search(pid)
            if task == -1: return -1 
            task.acceptSignal(sig)
            return 0
        return -1


    def acceptSignal(self,sig):
        '''
        @function acceptSignal() - Allows the Task
            to recieve the signal. Makes sure the signal is valid
        @param sig - int() - signal to be accepted.
        @return - int() - 0 upon suceess, -1 upon failure.
        '''
        if sig < len(self.signals) and sig > -1:
            self.signals[sig] = 1
            if self.handlers:
                handlerTask = self.build(self.priority,
                                        self.signalHandler,
                                        1, name='handler'
                                        ,parent=self)
                self.OS.fork(handlerTask)
            if sig in self.wakeSigs:
                self.isWaiting = 0
                self.isReady = 1
                self.wakeSigs.remove(sig)
            return 0
        else:
            return -1


    def sleep(self,secs,*args):
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
        '''
        @function wake() - Wakes the task up by setting the isSleep attribute
            to 0. 
        @return void
        '''
        self.isSleep = 0
        return


    def checkSleep(self):
        '''
        @function checkSleep() - Checks to see if the alotted time has passed 
        if the correct amount of time has passed then the task is woken back up. 
        
        @return - int - Task PID on successful wake up,
        -1 if in INDEFINITE till sig wake mode, 
        -1 if time constraint has not been met yet, 
        -1 if the task isn't sleep.
        
        ***NOTE if this is an embedded application, make sure the time
            library can be imported... if not, it might be best to use 
            the sigsuspendV2() function.        
        '''
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


    def sigSuspendV2(self, *argv):
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


    def signalHandler(self,task):
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
            self.handlers(task.parent)
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