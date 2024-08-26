import time, asyncio
import traceback

from .async_util.iterator_util import is_iterator

from .SmallErrors import PIDError
from .SmallSignals import SmallSignals
from .list_util.linkedList import Node
from .TaskState import TaskState



class SmallTask(SmallSignals, Node):
    '''
    @Class smallTask() - Object that contains Tasks contents: The routine,
        information, name, ID number, signals and other functions that tasks
        will need to interact with the OS and other Tasks.
    '''


    def __init__(self,priority,routine,**kwargs):
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
            @arg args - tuple(obj) - list of arguments to be passed in when routine is called.
        '''

        self.pid =  -1
        self.priority = priority
        self.isReady = 1
        self.isLocked = 0
        self.isWatcher = False
        self.parent = None
        self.OS = None
        self.placeholder  = 0
        self.state = TaskState()
        self.children = list()

        #Set the return value to the OS.
        return_val = {'return_status':0}
        self.state.update(return_val,'system')

        self.routine = self.wrap(routine)


        SmallSignals.__init__(self,self.OS,kwargs)
        Node.__init__(self)

        #Async
        self.asyncTaskHandle = None
        self.isInProgress = 0 
        self.isAsync = False


        #NEEDS to be changed to function with state preserved in the task
        self.updateFunc = None

        if kwargs:
            if kwargs.get('name',False):
                self.name = kwargs['name']
            if kwargs.get('update',False):
                self.updateFunc = kwargs['update']
            if kwargs.get('parent',False):
                self.parent = kwargs['parent']
            if kwargs.get('isReady',False):
                self.isReady = kwargs['isReady']
            if kwargs.get('isWatcher',False):
                self.isWatcher = kwargs['isWatcher']
            if kwargs.get('isAsync', False):
                self.isAsync = kwargs['isAsync']
            if kwargs.get('args', False):
                self.args = kwargs['args']

        return


    def wrap(self, func):
        def wrapper(self):

            data = self.state.getState(None,'system')
            if self.isAsync: 
                async def newRoutine(self):
                    try:
                        await func(self)
                    except asyncio.CancelledError as e:
                        self.isInProgress = 0
                    except Exception as e:
                        raise e
                    finally:
                        self.isInProgress = 0
                        
                if data[0].get('has_run',-1) == -1:
                    blob = data[0]
                    blob['has_run'] = 1
                    self.state.update(blob,'system')
                    self.isInProgress = 1
                    self.asyncTaskHandle = asyncio.create_task(newRoutine(self))
            elif is_iterator(func(self)):
                try:
                    if data[0].get('has_run',-1) == -1:
                        blob = {'has_run':1}
                        self.state.update(blob,'system')
                        self.f = func(self)
                        next(self.f)
                    else:
                        self.f.send(None)

                except StopIteration as e:
                    self.f.close()
            else:
                func(self)
            return self.state.getState('return_status','system')[0]
        return wrapper
            

    def excecute(self):
        '''
        @function execute() - Checks to see if the task() is ready
            or locked. If the task() is not locked and ready the routine()
            function is executed.
        @return - int - the result of the routine. 0 executed | -1 not executed
        '''
        if not self.routine: return 0
        if self.isReady and not self.isLocked:
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
            if self.updateFunc(self) == 1:
                self.isReady = 1
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
            if self.pid == -1:
                self.pid = pid
            else:
                raise PIDError('PID can only be set once.')
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


    def build(self,priority,task,ready=1,name='',parent=None):
            '''
            @function build - lets the smallsignal class create smallTasks. 
            @return - smallTask() 
            '''
            task = SmallTask(priority,
                            task,
                            isReady=ready,
                            name=name,
                            parent=parent)
            return task


    def fork(self,new_task):
        '''
        @function fork - taks in smallTasks and feeds them to to smallOS 
            labels the tasks as children.
        '''

        new_task.parent = self
        pid = self.OS.fork(new_task)
        self.children.append(pid)
        return pid
    
    ##Change this into a function that is a generator that 
    # spanws a process that spawns off the children and then wrap the children so that when they are 
    # done they trigger a signal handler in the generator process that records it as done and then
    # checks status of all other children. When they are done, feed the data to this process 
    # so that the original task in the demo can call next() on the waitOnasync function and get an array
    # of results. 
    def waitOnAsync(self, newTasks, priority=None):
   
        def wrapChildren(routine):
            async def newRoutine(self):
                await routine(self)
                parentPid = self.parent.getID()
                result = self.sendSignal(parentPid,6)
                if result != 0:
                    data = self.state.getState(None,'system')[0]
                    data['return_status'] = -1
                    self.state.update(data,'system')
                return
            return newRoutine
        
        def handleFinishedAsync(self):
            if self.checkSignal(6):
                flag = True
                pids = self.state.getState('pids')[0]
                for pid in pids:
                    child = self.OS.tasks.search(pid)
                    if child == -1:
                        flag &= True 
                    else:
                        flag &= bool(child.asyncTaskHandle) and child.asyncTaskHandle.done()
                if flag:
                    self.sendSignal(self.getID(), 7)
            return

        def spawnerRoutine(self):
            name = 'ChildOf ' + str(self.getID())
            pids = []
            for asyncTask in self.args['tasks']:
                task = SmallTask(priority,
                                    wrapChildren(asyncTask),
                                    name=name,
                                    isAsync=1)
                pids.append(self.fork(task))
            self.state.update({'pids':pids})
            yield self.sigSuspendV2(7)
            self.sendSignal(self.parent.getID(),5)
            return 
        
        if not priority:
            priority = self.priority

        parentPid = self.getID()
        name = 'ChildOf ' + str(self.getID())

        self.sigSuspendV2(5)

        args = {
            "tasks": newTasks,
        }

        asyncSpawner = SmallTask(
            priority,
            spawnerRoutine,
            name=name,
            parent=parentPid,
            handlers=handleFinishedAsync,
            args=args
        )

        self.fork(asyncSpawner)

        return 


    def kill(self, flags={}):
        if not self.OS: return -1

        if self.isAsync:
            self.asyncTaskHandle.cancel()

        if '-r' in flags:
            for child in self.children:
                child.kill()
        
        if self.parent:
            self.parent.children.remove(self.getID())
         
        self.OS.tasks.delete(self.getID())


    def getExeStatus(self):
        '''
        @function getExeStatus() - Checks all of the process's statuses to see
            if the process is ready to be executed. 
        @return - bool - True for if the Task can be Executed and False if 
            it is not. 
        '''
        status = (self.isReady == 1) and (self.isWaiting == 0)
        status &= (self.isSleep == 0) and (not self.isAsync or self.isInProgress == 0)
        return status 


    def getDelStatus(self):
        '''
        @function getDelStatus() - Checks all of the process's statuses to 
        see if the process needs to be deleted.
        @return - bool - True for if the process can be deleted and False if 
            it can not.       
        '''
        status = (self.isReady == 0) and (self.isWaiting == 0)
        status &= (self.isSleep == 0) and (not self.isAsync or self.asyncTaskHandle.done())
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



