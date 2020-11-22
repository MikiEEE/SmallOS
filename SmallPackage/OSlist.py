

from .list_util.linkedList import insertNext, removeNode
from .list_util.binSearchList import insert, search


# import time



class smallPID():
    '''
    @class smallPID() - Creates and keeps track of avialable
        Process ID's
    '''

    def __init__(self, max=2**16):
        '''
        @function __init__() - Initializes essential maintenence 
            structures.
        @param max - int - The max number of process ID's.
            Valid process ID's are 0 - (max - 1).
        @return - void
        '''
        self.pastPid = 0
        self.maxPID = max
        self.usedPID = set()
        return


    def newPID(self):
        '''
        @function newPID() - Creates a new valid PID. 
        @return - int - positive integer on succes 
            -1 on failure.
        '''
        if len(self.usedPID) < self.maxPID:
            pid = self.pastPid
            while pid%self.maxPID in self.usedPID: pid+=1
            self.usedPID.add(pid%self.maxPID)

            if self.pastPid >= self.maxPID:
                self.pastPid = 0
            self.pastPid = pid
            return pid%self.maxPID
        else:
            return -1


    def freePID(self,pid):
        '''
        @function freePID - removes the pid from the used 
            pid set() making the pid available for future 
            use.
        @return - void
        '''
        if pid in self.usedPID:
            self.usedPID.remove(pid)
        return 





class OSList(smallPID): 
    '''
    @class OSList - Creates Binary Search List that contains
        elements of class SmallTask(). All elements are stored
        in the list by order of PID; however all elements are also 
        Nodes of a LinkedList that is sorted by priority. 
        
        Plan on adding a speed optimized and less space efficient mode 
        in the near future.
    '''

    def __init__(self, priors=5, length=2**12):
        '''
        @function __init__() - takes in the number of priorities to be  
            used in the OS to create the linked list and takes in the
            amount of allowed processes and sets up the datastructures. 
        @param proiors - int - the number of priorities allowed on the system. 
                                numbers: 0 - (priors - 1)
        @length - int - the number of allowed processes. 
        '''
        smallPID.__init__(self,length)
        self.cats = [None] * priors
        self.catSelect = 0
        self.tasks = list()
        self.current = None
        self.sleepList = None
        self.func = lambda data, index: data[index].getID()
        return 


    def resetCatSel(self):
        '''
        @function resetCatSel() - reinitializes the catSelect variable to 
            zero so self.pop() function can start from the highest priority. 
        @return - void 
        '''
        catSelect = 0
        return 


    def setCatSel(self, newSel):
        '''
        @function setCatSel() - when a valid higher priority task is
            added to the tasklist the next self.pop() result will be set to 
            look to that higher priority rather then the previous next element. 

            ***Note***
            Accomplishes this by seting current to None so when pop() is called
            it looks for the next available category.
        
        @param newSel - the priority of the new task. 
        @return - int - 0 on a valid priority and -1 on an invalid priority. 
        '''
        if 0 <= newSel < len(self.cats):
            if self.catSelect > newSel:
                self.catSelect = newSel
                self.current = None
            return 0
        return -1


    def availCat(self,sel=0):
        '''
        @function availCat() - goes through the categories 
            and finds the next available task category. 
        @param sel - int - the starting index of of the category select
            list. 
        @return - SmallTask() - a non-void task to be executed. 
        '''
        result = None
        for task in self.cats[sel:]:
            if task != None:
                result = task
                break
        return result


    def incrementCat(self):
        '''
        @function incrementCat() - increments the category tracker
            by 1 and if the ctracker is out of array bounds, the tracker
            is set back to 0. 
        @return - void
        '''
        if self.catSelect < len(self.cats):
            self.catSelect += 1
        if self.catSelect == len(self.cats):
            self.catSelect = 0
        return 


    def pop(self):
        '''
        @function pop() - gets the current highest priority node 
            in the queue, works through the entire queue.
        @return - SmallTask() - the highest priority object 
            in the queue.
        '''
        if self.current == None:
            self.current = self.availCat()
        elif self.current.next != None:
            self.current = self.current.next
        else: 
            self.incrementCat()
            self.current = self.availCat(self.catSelect)

        if self.current != None and self.current.priority >  self.catSelect:
            self.catSelect = self.current.priority
        return self.current


    def insert(self, task):
        '''
        @function insert() - inserts the task 
            inorder (by pid) in the task list array and adds 
            task to a doubly-linked-list in order (by priority)
        @param task - SmallTask() - to be added to the OSlist.
        @return - int - positive integer on success, -1 on failure. 
        '''
        priority = task.priority
        if 0 < priority < len(self.cats):

            pid = self.newPID()
            if pid == -1: return -1

            task.setID(pid)
            length = len(self.tasks)

            index = insert(self.tasks,pid,0,length,func=self.func)
            self.tasks.insert(index, task)

            #If there is no task with that priority make it the head of the 
            #list node. Otherwise add it onto the list sorted by priority.
            if self.cats[priority] == None:
                self.cats[priority] = self.tasks[index]
            else:
                insertNext(self.cats[priority],task)

            #If a higher priority task is added then the current running 
            # priority it will be set.
            self.setCatSel(priority)
            return pid
        return -1


    def search(self,pid):
        '''
        @function search() - performs binary search to find and retrieve 
            a process by pid. 
        @param pid - int - the pid of the requested process. 
        @return - SmallTask() on success | -1 on Failure - returns the task with 
            the matching pid on success and -1 if a process with that pid does not exist.  
        '''
        length = len(self.tasks)
        index = search(self.tasks,pid,0,length,self.func)
        if index == -1: return index
        return self.tasks[index]


    def delete(self,pid):
        '''
        @function delete() - performs binary search to find and delete a process
            by pid.
        @param pid - int - the pid of the requested process.
        @return  - int - 0 on successful deletion and -1 if the process is not
            found.
        '''
        length = len(self.tasks)
        index = search(self.tasks,pid,0,length,self.func)
        if index == -1: return -1

        removeNode(self.tasks[index])
        priority = self.tasks[index].priority

        if self.cats[priority].getID() == self.tasks[index].getID():
            self.cats[priority] = self.cats[priority].next

        del self.tasks[index]
        self.freePID(pid)
        return 0


    def list(self):
        '''
        @function list() - returns a list of all of the tasks
            in the OSlist.
        '''
        return [task for task in self.tasks]


    def moveToSleepList(self,sleep_task):
        
        #Remove From the priority category list 
        #but keep in the pid list  for searching
        removeNode(sleep_task)
        priority = sleep_task.priority

        if self.cats[priority].getID() == sleep_task.getID():
            self.cats[priority] = self.cats[priority].next

        #Clear the active tasks from the memory
        sleep_task.next = None
        sleep_task.prev = None

        #Add to sleep list
        if self.sleepList == None:
            self.sleepList = sleep_task
        else:
            insertNext(self.sleepList, sleep_task)
        return


    def notifyWake(self,woken_task):

        priority = woken_task.priority

        #Determine if it is the head of Sleep list
        if self.sleepList.getID() == woken_task.getID():

            if woken_task.next != None:
                self.sleepList = self.sleepList.next 
            else:
                self.sleepList = None
        
        removeNode(woken_task)
        woken_task.prev = None
        woken_task.next = None

        if self.cats[priority] == None:
            self.cats[priority] = woken_task
        else:
            insertNext(self.cats[priority],woken_task)

        return self.setCatSel(priority)


    def __len__(self):
        '''
        @function __len__() - returns the number of tasks 
            within the OSlist().
        '''
        return len(self.tasks)


    def __str__(self):
        '''
        @function __str__() - return the string representation 
            of all the tasks within the OSlist()
        '''
        return '\n'.join([str(x) for x in self.tasks])





# if __name__ == '__main__':

#     tasks = OSList(10)

#     secs = time.time()
#     # for x in range(2**6):
#     #     tasks.insert(smallTask(x % 10,None,1, name=str(x)))
#     pid1 = tasks.insert(smallTask(1,None, name=str(1)))
#     pid2 = tasks.insert(smallTask(2,None, name=str(2)))
#     pid3 = tasks.insert(smallTask(3,None, name=str(3)))
#     pid4 = tasks.insert(smallTask(4,None, name=str(4)))
#     pid5 = tasks.insert(smallTask(5,None, name=str(5)))

   
#     print([x.priority for x in tasks.cats[0:4]])
#     cursor = tasks.pop()
#     while cursor != None:
#         cursor.isReady = 0
#         print(cursor.name, cursor.getID(), cursor.priority)
#         cursor = tasks.pop()

#     print(len(tasks))



