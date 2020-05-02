




class placeHolder():
    '''
    @class PlaceHolder() - Maintains the positional state of a process 
        in the event of something similar to a sleep() or sigSuspendV2() call.
    '''
    ##THIS IS WHERE I WOULD ADD LOOP SUPPORT 
    def __init__(self):
        '''
        @function __init__() - Sets up initial variables for 
            loop control. 
        @return - void.
        '''
        self.placeholder = 0 
        self.timeKeeper = 0
        self.incrementor = 0
        self.isUsed = False
        return 


    def getPlace(self):
        '''
        @function getPlace() - Used to determine which branch 
            to be gone into based off of where the last sigSuspendV2() 
            call was.
        @return boolean - True If this is the correct branch. 
            False if it is not the correct branch.

        ***NOTE-Typically used in the actual Task code. 

            if task.getPlace():
                do something
                task.sigSupendV2()
            if task.getPlace():
                do something else
        '''
        if self.isUsed == True:
            return False

        if self.timeKeeper == 0:
            self.isUsed = True
            return True 
        else:
            self.timeKeeper -= 1
            return False


    def setUpPlace(self):
        '''
        @function setUpPlace() - Sets up the IsUsed Variable so
            that the correct branch and only that branch can be used. 
        @return void
        '''
        self.isUsed = False
        return


    def setPlaceholder(self):
        '''
        @function setsup the placeholder to know which branch
            to go into next. 
        @return void.
        '''

        #This function in particular is where the loop support
        #will be added.

        self.incrementor += 1
        self.timeKeeper = self.incrementor
        return 


    def getPlaceholder(self):
        '''
        @function getPlaceholder - (Deprecated) - retrieves the placeholder 
            number.
        @return - int() - returns the placholder number.
        '''
        return self.placeholder


    def placeHolderReset(self):
        '''
        @function placeHolderReset -(Depriecated) - Resets the 
            placeholder. 
        @return void.
        '''
        self.placeholder = 0
        return