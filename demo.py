from SmallOS import smallOS
from SmallTask import smallTask
from shells import baseShell
from SmallErrors import MaxProcessError

import time 


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

def forkDemo(OS, taskObj):

    if taskObj.pid == 0:
        if taskObj.getPlace():
            vars = list()
            vars.append(1)
            pids = [OS.fork(smallTask(x%7+ 1,forkDemo,1,parent=taskObj,name=str(x))) for x in range(2**5)]
            OS.smAppPrint("Adding \n")
            OS.fork(smallTask(9,forkDemo,1,name='child',parent=taskObj))
            OS.smAppPrint("PARENT SLEEPING\n")
            taskObj.sigSuspendV2(OS,1)
        elif taskObj.getPlace():
            OS.smAppPrint("PARENT Done \n")

    elif taskObj.name == 'child':
        taskObj.sendSignal(OS,0,1)
         # pass
    else:
        taskObj.sendSignal(OS,0,2)
    return 0


def handler(OS,taskObj):
    if taskObj.checkSignal(2):
        OS.smAppPrint('from:',taskObj.name,'ouch','\n')
    return 0 


def send(OS,taskObj):
    parent = taskObj.parent
    parent = parent.pid
    OS.smAppPrint("Sending Signal \n")
    taskObj.sendSignal(OS,parent,1)
    return 0


def pHDemo(OS,taskObj):
    if taskObj.getPlace():
        OS.smAppPrint("First Phrase","\n")
        child = OS.fork(smallTask(8,send,1,parent=taskObj,update=update21, name='sender'))
        taskObj.sigSuspendV2(OS,child)

    if taskObj.getPlace():
        OS.smAppPrint("Second \n")
        taskObj.sigSuspendV2(OS) 

    if taskObj.getPlace():
        OS.smAppPrint("third \n")
        taskObj.sigSuspendV2(OS) 

    if taskObj.getPlace():
        OS.smAppPrint("fourth \n")
        pid = taskObj.getState()[0]
        OS.tasks.delete(pid)
    return 0


def sleepDemo(OS, taskObj):
    if taskObj.getPlace():
        OS.smAppPrint("First Phrase","\n")
        # OS.fork(smallTask(8,send,1,parent=taskObj,update=update21), taskObj)
        taskObj.sleep(OS,1,3,[5,7,9])

    if taskObj.getPlace():
        OS.smAppPrint("Second \n")
        taskObj.sleep(OS,1,4)

    if taskObj.getPlace():
        OS.smAppPrint("third \n")
        taskObj.sleep(OS,1,5)

    if taskObj.getPlace():
        OS.smAppPrint("fourth \n")
    return 0


def sleepAndSuspendDemo(OS, taskObj):
    print('hello')
    if taskObj.getPlace():
        OS.smAppPrint("First Phrase","\n")
        OS.fork(smallTask(8,send,1,parent=taskObj))
        taskObj.sigSuspendV2(OS)

    if taskObj.getPlace():
        OS.smAppPrint("Second \n")
        taskObj.sleep(OS,1)

    if taskObj.getPlace():
        OS.smAppPrint("third \n")
        # taskObj.sigSuspendV2(OS, 0,1) 

    # if taskObj.getPlace():
    #     OS.smAppPrint("fourth \n")
    return 0

#@task
def execDemo(OS,taskObj):
    cmd = '''OS.smAppPrint('HELLO','\\n',taskObj,'\\n')'''
    cmd = compile(cmd,"demo.py","exec")
    exec(cmd)
    return 0


if __name__ == '__main__':
    #Comment Everything, get rid of unused functions  and make shell more robust
    #Make demos cleaner, better state saving with dict, Make unittestes, 
    #work through innerloops
        update21= updater1()
        base = baseShell()
        demo_1 = smallTask(1,forkDemo,1,name='Parent1', handlers=handler)
        demo_2 = smallTask(1,pHDemo,1, name='Parent',handlers=handler)
        demo_3 = smallTask(1,sleepDemo,1, name='Parent')
        demo_4 = smallTask(1,sleepAndSuspendDemo,1, name='Parent')
        demo_5 = smallTask(1,execDemo,1, name='Parent')
        OS = smallOS(shells=base)

        tasks = [demo_1,demo_2,demo_3,demo_4,demo_5]
        fails = list()
        #OS.addTasks([demo_1,demo_2,demo_3,demo_4])
        # OS.addTasks([demo_4])
        # OS.start()
        for num, demo in enumerate(tasks):
            try:
                OS.addTask(demo)
                OS.start()
            except: 
                fails.append(num + 1)

        if len(fails) == 0:
            print('ALL DEMOS COMPLETED SUCCESSFULLY')
        else:
            print(fails)
        # OS.smAppPrint(OS,'\n')

