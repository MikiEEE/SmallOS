import binSearchList as bList
from SmallTask import smallTask
import time



def insertPrev(root, newNode):
    '''
    @function insertPrev() - takes in a rootNode and newNode and 
        inserts the newNode behind the rootNode.
    @param root -  Node() - a doubly-linked-list node that the 
        newNode is added behind. 
    @param newNode - Node() - a doubly-linked-list node that is 
        being added behind the root.
    @return void
    '''
    temp = root.prev 

    root.prev = newNode
    newNode.prev = temp

    newNode.next = root
    if temp:
        temp.next = newNode
    return 


def insertNext(root,newNode):
    '''
    @function insertNext() - takes in a rootNode and newNode and 
        inserts the newNode infront of the rootNode.
    @param root -  Node() - a doubly-linked-list node that the 
        newNode is added infront of. 
    @param newNode - Node() - a doubly-linked-list node that is 
        being added in front of the root.
    @return void
    '''
    temp = root.next

    root.next = newNode
    newNode.next = temp

    newNode.prev = root
    if temp:
        temp.prev = newNode
    return


def removeNode(node):
    '''
    @function removeNode() - Removes the Node() from the 
        doubly-linked-list
    @param node -  Node() - Node to be removed from the list.
    @return void

    ***NOTE
        The node is not deleted from memory but only 
        from the list. ***
    '''
    prev = node.prev
    next = node.next 

    if prev:
        prev.next = next
    if next:
        next.prev = prev
    return 






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




class smallPID():
    '''
    @class smallPID() - Used to select and keep track 
        of process ID's in use and available. 
    '''

    def __init__(self, max=2**16):
        '''
        @param 
        '''
        self.pastPid = 0
        self.maxPID = max
        self.usedPID = set()


    def newPID(self):
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
        @param newSel - the priority of the new task. 
        @return - int - 0 on a valid priority and -1 on an invalid priority. 
        '''
        if 0 < newSel < len(self.cats):
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
        if priority < len(self.cats):

            pid = self.newPID()
            if pid == -1: return -1

            task.setID(pid)
            length = len(self.tasks)

            index = bList.insert(self.tasks,pid,0,length,func=self.func)
            self.tasks.insert(index, task)

            if self.cats[priority] == None:
                self.cats[priority] = self.tasks[index]
            else:
                insertNext(self.cats[priority],task)

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
        index = bList.search(self.tasks,pid,0,length,self.func)
        if index != -1: return index
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
        index = bList.search(self.tasks,pid,0,length,self.func)
        if index == -1: return -1
        removeNode(self.tasks[index])
        del self.tasks[index]
        self.freePID(pid)
        return 0


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



if __name__ == '__main__':
    tasks = OSList(10)

    secs = time.time()
    for x in range(2**6):
        tasks.insert(smallTask(x % 10,None,1, name=str(x)))
    print(time.time() - secs)

    print(tasks)

    print([x.priority for x in tasks.cats[0:4]])
    cursor = tasks.pop()
    while cursor != None:
        cursor.isReady = 0
        print(cursor.name, cursor.getID(), cursor.priority)
        cursor = tasks.pop()

    print(len(tasks))






