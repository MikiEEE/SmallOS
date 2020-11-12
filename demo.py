from SmallPackage.SmallOS import SmallOS
from SmallPackage.SmallTask import SmallTask
from SmallPackage.Kernel import Unix
from shells import baseShell
import time, traceback 


class updater1():
    times = list()
    timeout = 0

    def __init__(self, timeout=1):
        self.times = list()
        self.timeout = timeout


    def update(self):
        self.times.append(time.time())
        if len(self.times) < 2:
            return 0
        elif self.times[1] - self.times[0] > self.timeout:
            self.times.pop(0)
            return 1
        else:
            del self.times[1]
            return 0
        return

update21= updater1(1)

def forkDemo(self):

    if self.pid == 0:
        if self.getPlace():
            vars = list()
            vars.append(1)
            pids = [self.OS.fork(SmallTask(x%7+ 1,forkDemo,1,parent=self,name=str(x))) for x in range(2**9)]
            self.OS.print("Adding \n")
            self.OS.fork(SmallTask(9,forkDemo,1,name='child',parent=self))
            self.OS.print("PARENT SLEEPING\n")
            self.sigSuspendV2(1)
        elif self.getPlace():
            self.OS.print("PARENT Done \n")

    elif self.name == 'child':
        self.sendSignal(0,1)
         # pass
    else:
        self.sendSignal(0,2)
    return 0


def handler(self):
    if self.checkSignal(2):
        self.OS.print('from:',self.name,'ouch','\n')
    return 0 


def send(self):
    parent = self.parent
    parent = parent.pid
    self.OS.print("Sending Signal \n")
    self.sendSignal(parent,1)
    return 0


def pHDemo(self):

    if self.getPlace():
        self.OS.print("First Phrase","\n")
        child = self.OS.fork(SmallTask(8,send,1,parent=self,update=update21, name='sender'))
        self.sigSuspendV2(1,{'child':child})

    if self.getPlace():
        self.OS.print("Second \n")
        self.sigSuspendV2(1) 

    if self.getPlace():
        self.OS.print("third \n")
        self.sigSuspendV2(1) 

    if self.getPlace():
        self.OS.print("fourth \n")
        pid = self.state.getState('child')
        self.OS.tasks.delete(pid)
    return 0


def sleepDemo( self):
    if self.getPlace():
        self.OS.print("First Phrase","\n")
        # self.OS.fork(SmallTask(8,send,1,parent=self,update=update21), self)
        nums = [1,3,[5,7,9]]
        self.sleep(0,{'nums':nums})

    if self.getPlace():
        self.OS.print("Second \n")
        self.sleep(0,{'nums':[1,4]})

    if self.getPlace():
        self.OS.print("third \n")
        self.sleep(0,{'nums':[1,5]})

    if self.getPlace():
        self.OS.print("fourth \n")
    return 0


def sleepAndSuspendDemo( self):
    print('hello')
    if self.getPlace():
        self.OS.print("First Phrase","\n")
        self.OS.fork(SmallTask(8,send,1,parent=self))
        self.sigSuspendV2(1)

    if self.getPlace():
        self.OS.print("Second \n")
        self.sleep(1)

    if self.getPlace():
        self.OS.print("third \n")
        # self.sigSuspendV2( 0,1) 

    # if self.getPlace():
    #     self.OS.print("fourth \n")
    return 0

#@task
def execDemo(self):
    cmd = '''self.OS.print('HELLO','\\n',self,'\\n')'''
    cmd = compile(cmd,"demo.py","exec")
    exec(cmd)
    return 0


if __name__ == '__main__':
    #move baseShell into OS by default , output piping, make shell more robust, Describe each demo,
    #Make cleaner, add adjustable signal lengths, Turn Shell into own process
    #work through innerloops.
        update21= updater1()
        base = baseShell()
        demo_1 = SmallTask(1,forkDemo,1,name='Parent1', handlers=handler)
        demo_2 = SmallTask(1,pHDemo,1, name='Parent',handlers=handler)
        demo_3 = SmallTask(1,sleepDemo,1, name='Parent')
        demo_4 = SmallTask(1,sleepAndSuspendDemo,1, name='Parent')
        demo_5 = SmallTask(1,execDemo,1, name='Parent')
        OS = SmallOS(shells=base)

        OS.setKernel(Unix())

        tasks = [demo_1,demo_2,demo_3,demo_4,demo_5]
        fails = list()
        #self.OS.addTasks([demo_1,demo_2,demo_3,demo_4])
        # self.OS.addTasks([demo_4])
        # self.OS.start()
        for num, demo in enumerate(tasks):
            try:
                OS.fork(demo)
                OS.start()
            except: 
                print(traceback.format_exc())
                fails.append(num + 1)

        if len(fails) == 0:
            print('ALL DEMOS COMPLETED SUCCESSFULLY')
        else:
            print(fails)
        # self.OS.print('\n')

