from SmallOS import smallOS
from SmallTask import smallTask
from shells import baseShell
from SmallErrors import MaxProcessError

import time, traceback 

'''
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPself.OS.E AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 SOFTWARE.
'''

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
            pids = [self.OS.fork(smallTask(x%7+ 1,forkDemo,1,parent=self,name=str(x))) for x in range(2**9)]
            self.OS.print("Adding \n")
            self.OS.fork(smallTask(9,forkDemo,1,name='child',parent=self))
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
        child = self.OS.fork(smallTask(8,send,1,parent=self,update=update21, name='sender'))
        self.sigSuspendV2(child)

    if self.getPlace():
        self.OS.print("Second \n")
        self.sigSuspendV2() 

    if self.getPlace():
        self.OS.print("third \n")
        self.sigSuspendV2() 

    if self.getPlace():
        self.OS.print("fourth \n")
        pid = self.getState()[0]
        self.OS.tasks.delete(pid)
    return 0


def sleepDemo( self):
    if self.getPlace():
        self.OS.print("First Phrase","\n")
        # self.OS.fork(smallTask(8,send,1,parent=self,update=update21), self)
        self.sleep(1,3,[5,7,9])

    if self.getPlace():
        self.OS.print("Second \n")
        self.sleep(1,4)

    if self.getPlace():
        self.OS.print("third \n")
        self.sleep(1,5)

    if self.getPlace():
        self.OS.print("fourth \n")
    return 0


def sleepAndSuspendDemo( self):
    print('hello')
    if self.getPlace():
        self.OS.print("First Phrase","\n")
        self.OS.fork(smallTask(8,send,1,parent=self))
        self.sigSuspendV2()

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
    #Comment Everything, get rid of unused functions  and make shell more robust
    #Make demself.OS. cleaner, better state saving with dict, Make unittestes, Turn Shell into own process
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

