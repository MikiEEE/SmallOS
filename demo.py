from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask
from SmallPackage.Kernel import Unix
from shells import BaseShell

import pdb, select,sys, socket, asyncio,aiohttp

NETWORK_SIGNAL=5


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
    @function Fork Demo - demonstrates using small os to be able to 
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
    '''
    @function pHDemo - The purpose of this function is to create a demonstration 
        of allowing functions to suspend until a signal is recieved. 
    '''

    #Creation of the child process and that will wake up every second and 
    #send a signal to this process so that It can move onto different phases.
    self.OS.print('First Phrase','\n')
    child = self.OS.fork(SmallTask(8,send,isReady=1,parent=self,update=update, name='sender'))
    yield self.sigSuspendV2(1,{'child':child})

    #Second phase of function. 
    self.OS.print('Second \n')
    yield self.sigSuspendV2(1) 

    #Third phase of function
    self.OS.print('third \n')
    yield self.sigSuspendV2(1) 

    #Fourth phase of function
    self.OS.print('fourth \n')
    pid, status = self.state.getState('child')
    self.OS.tasks.delete(child)
    return 







def sleepDemo(self):
    '''
    @function sleepDemo -  Function demonstrates sleep ability. 
        ***NOTE***
        At this time the sleep ability does not support a sleep of 
        0. This will cause the task to be called in loop. 
    '''
    self.OS.print('First Phrase','\n')
    nums = [1,3,[5,7,9]]
    yield self.sleep(0,{'nums':nums})

    self.OS.print('Second \n')
    yield self.sleep(0,{'nums':[1,4]})

    self.OS.print('third \n')
    yield self.sleep(0,{'nums':[1,5]})

    self.OS.print('fourth \n')
    return 







def sleepAndSuspendDemo(self):
    '''
    @function sleepAndSuspendDemo - Function demonstrates ability to
            spin up new tasks, then sleep, then wake when the child tasks 
            wake the main task.
    '''
    print('hello')
    self.OS.print('First Phrase','\n')
    self.fork(SmallTask(8,send))
    yield self.sigSuspendV2(1)

    self.OS.print('Second \n')
    yield self.sleep(1)

    self.OS.print('third \n')
    return 







#@task
def execDemo(self):
    '''
    @function execDemo - Function demonstrates ability to be able to 
            Execute string commands. 
    ***NOTE***
        This is not to be used as of yet.
    '''
    cmd = '''self.OS.print('HELLO','\\n',self,'\\n')'''
    cmd = compile(cmd,'demo.py','exec')
    exec(cmd)
    return 





def loop_demo(self):
    '''
    @function loop_demo - demonstrates the ability to be able to 
            use SMALLOS with loops. 
    ***NOTE***
        Will work on timing mechanism of sleep to take in no parameters, 
        and to make scheduler compatible with this.  
    '''
    for i in range(100):
        self.OS.print(i,'\n')
        if i == 50:
            self.OS.print('Sleeeping...','\n')
            yield self.sleep(.1)
    return






def watcher_IO(self):
    '''
    @Function watcher_IO - This is a high priority watcher function
        Its purpose is to poll for IO interactions
        and pipe data to the respective running process
        
        At this stage in project I recommend you  would 
        have multiple of these polling for different things.
        
        In an Ideal setting, using interrupts to wake up tasks
        like these would be good.
    '''
    while 1:
        if select.select([sys.stdin,],[],[],0.0)[0]:
            inpt = sys.stdin.readline()
            for shell in self.OS.shells:
                shell.run(inpt)
        yield self.sleep(.01)
    return 


def make_request(self,http_request_config):
    '''
        Sets up a socket connection and makes a requets.
        returns a socket connection. 
        Should fork off a new task that reads the request and then
        go to sleep, needs to wake up the original task when finished.
        End of Function must make a call to self.sigsuspendv2()
        Must be yeilded after.
    '''
        # Create a socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect to the server
    client_socket.connect((http_request_config.get('host'),http_request_config.get('port' )))

    # Send the HTTP request
    request = f"GET {http_request_config.get('path')} HTTP/1.1\r\nHost: {http_request_config.get('host')}\r\nConnection: close\r\n\r\n"
    client_socket.sendall(request.encode())


    read_task = SmallTask(1,read_request,args=(client_socket,), parent=self)
    self.OS.fork(read_task)

    return 




def read_request(self):
    '''
        Takes in the socket connection from make request and reads it non 
        blocking otherwise  sleeps
        When finished  writes data to parent task & sends a signal to wake the parent task 
    '''

    client_socket = self.args[0] #Get client socket from args passed in on task creation see make_request()

    client_socket.setblocking(False)

    response = b''
    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            response += data
        except BlockingIOError:
            yield self.sleep(.001)

    # Close the connection
    client_socket.close()

    self.parent.state.update({'message_response':response})
    self.sendSignal(self.parent.pid, NETWORK_SIGNAL)
    return 


def networkDemo(self):
    self.OS.print('Starting network request\n')
    make_request(self,{
        'host': 'www.google.com',
        'port':80,
        'path':'/'
    })
    self.OS.print('Doing Something Else\n')
    yield self.sigSuspendV2(NETWORK_SIGNAL)
    print(self.state.getState(None)[:10])


async def printer(self):
    while 1:
        self.OS.print("Task is running...\n")
        await asyncio.sleep(1)

async def asyncioDemo(self):
    try:
        async def func():
            url = 'http://www.google.com'
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    text = await response.text()
                    return text
        data = await func()
        loop = asyncio.get_event_loop()

        async def print_in_batches(string, batch_size=1):
            for i in range(0, len(string), batch_size):
                sys.stdout.write(string[i:i+batch_size])
                sys.stdout.flush()
                await asyncio.sleep(0)
        await print_in_batches(data)
    except Exception as e:
        print(e)

async def async_watcher_IO(self):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    reader_protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: reader_protocol, sys.stdin)

    while True:
        inpt = await reader.readline()
        if inpt:
            inpt = inpt.decode('utf-8')
            for shell in self.OS.shells:
                await shell.run(inpt)
            # print('INPUT', inpt)
        await asyncio.sleep(0.01)

async def create_async_tasks(self):
    one = 1
    self.OS.print('IIII\n')
    async def sleepwait(self):
        self.OS.print('HELLO\n')
        start  = 1
        while start < 10:
            await asyncio.sleep(1)
            self.OS.print('create task test sleeping\n')
            start += 1 

    await self.waitOnAsync([sleepwait])
    self.OS.print('done\n')

if __name__ == '__main__':
    #Priority is set to 2 to give higher priority (quick) system tasks
    #such as a2d reading input checking a chance to run quickly.  
    priority = 2

    base = BaseShell()
    watcher_IO =  SmallTask(priority-1,async_watcher_IO,isReady=1,name='watcher_IO',isWatcher=True)
    # demo_1 = SmallTask(priority,forkDemo,isReady=1,name='Parent1', handlers=handler)
    # demo_2 = SmallTask(priority,pHDemo, name='Parent2',handlers=handler)
    # demo_3 = SmallTask(priority,sleepDemo, name='Parent3')
    # demo_4 = SmallTask(priority,sleepAndSuspendDemo, name='Parent4')
    # demo_5 = SmallTask(priority,execDemo,name='Parent5')
    # demo_6 = SmallTask(priority+2,loop_demo,name='Parent6')
    # demo_7 = SmallTask(priority+2,networkDemo,name='Parent7')
    # demo_8 = SmallTask(2,printer,name='printer')
    demo_9 = SmallTask(priority+2,create_async_tasks,name='Parent9')

    
    #Instantiate and configure the OS.
    OS = SmallOS(shells=[base]) #Set up shell interface
    OS.setKernel(Unix())      #Set up interface for syscalls
    OS.setEternalWatchers(True)  #Set to end when only watcher tasks remain.

    #Tasks to be executed.
    # tasks = [demo_1,demo_2,demo_3,demo_4,demo_5,demo_6,watcher_IO]
    tasks = [demo_9,watcher_IO]

    handle = None

    # fails = list()
    OS.fork(tasks)

    asyncio.run(OS.start())
    # asyncio.run(asyncioDemo(None))

    #Test how aync tasks also work with yeild. Maybe check for async handle and if it exists  then just call generator next?
    #move baseShell into OS by default , output piping, make shell more robust, Describe each demo,
    #Make watchers run after each task on option
    #Make cleaner, add adjustable signal lengths, Turn Shell into own process
    #Turn OSlist into Balanced Bin Tree?
    #Create config file.
    #create internal  messaging system
    #remove placeholder class
    #Allow SmallTask constructor to take in dict onfiguration objects.


