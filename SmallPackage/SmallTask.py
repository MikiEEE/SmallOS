import time
import traceback

from .smallSignals import smallSignals
from .list_util.linkedList import Node


class smallTask(smallSignals, Node):
    '''
    @Class smallTask() - Object that contains Tasks contents: The routine,
        information, name, ID number, signals and other functions that tasks
        will need to interact with the OS and other Tasks.
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
        self.OS = None
        self.placeholder  = 0

        #NEEDS to be changed to function with state preserved in the task
        self.updateFunc = None

        super().__init__(self.OS,kwargs)
        Node.__init__(self)

        if kwargs:
            if kwargs.get('name',False):
                self.name = kwargs['name']
            if kwargs.get('update',False):
                self.updateFunc = kwargs['update']
            if kwargs.get('parent',False):
                self.parent = kwargs['parent']
        return


    def excecute(self):
        '''
        @function execute() - Checks to see if the task() is ready
            or locked. If the task() is not locked and ready the routine()
            function is executed.
        @return - int - the result of the routine. 0 executed | -1 not executed
        '''
        if self.isReady and not self.isLocked:
            self.setUpPlace()
            self.isReady = 0
            result = self.routine(self)
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

    def setOS(self, OS):
        '''
        @function setOS - sets the object's OS to the current OS.
        '''
        self.OS = OS


    def build(self,priority,task,ready,name='',parent=None):
            task = smallTask(priority,task,
                            ready, name=name,
                            parent=parent)
            return task

    def getExeStatus(self):
        '''
        @function getExeStatus() - Checks all of the process's statuses to see
            if the process is ready to be executed. 
        @return - bool - True for if the Task can be Executed and False if 
            it is not. 
        '''
        status = (self.isReady == 1) and (self.isWaiting == 0)
        status = status and (self.isSleep == 0)
        return status 


    def getDelStatus(self):
        '''
        @function getDelStatus() - Checks all of the process's statuses to 
        see if the process needs to be deleted.
        @return - bool - True for if the process can be deleted and False if 
            it can not.       
        '''
        status = (self.isReady == 0) and (self.isWaiting == 0)
        status &= (self.isSleep == 0)
        return status 


    def stat(self):
        '''
        @function stat() - gets a string of the statuses in greater detail. 
        '''
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



