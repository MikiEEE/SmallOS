#Kernals will be swappable depending on what hardware you are running on.


class SmallIO():
    '''
    @class smallIO() - controls print Input-Output 

    ***NOTE***
    This will probably be moved into the kernal class as a variable. 
    And will most likley be piped into the different processes on a terminal
    selection basis.

    TODO: Turn appPrintQueue into a circular buffer.
    '''

    def __init__(self, buffer_length):
        '''
        @fucntion __init__() - sets up the terminal toggle 
             and printqueuing veriables. 
        '''
        self.terminalToggle = False
        self.appPrintQueue = list()
        self.buffer_length = buffer_length
        return 


    def print(self, *args):
        '''
        @function print() - Prints output to terminal for application display.
        @param *args - takes in arguments, does not automatically add newline.
        @return - void.
        '''
        msg = ''.join([str(arg) for arg in args])
        if self.terminalToggle == False:
            self.kernel.write(msg)
        elif len(self.appPrintQueue) < self.buffer_length:
            self.appPrintQueue.append(msg)
        else:
            self.appPrintQueue.pop(0)
            self.appPrintQueue.append(msg)
        return


    def sPrint(self, *args):
        '''
        @function sPrint() - Prints output to terminal for OS-related display.
        @param *args - takes in arguments, does not automatically add newline.
        @return - void.
        '''
        if self.terminalToggle == True:
            msg = ''.join([str(arg) for arg in args])
            self.kernel.write(msg) 
        return


    def toggleTerminal(self):
        '''
        @function toggleTerminal() - Toggles the terminal from displaying application output
            to OS command output and vice-versa.
        @return - void.
        '''
        self.terminalToggle = not self.terminalToggle
        msg = ''.join('*' for x in range(16)) + '\n'
        self.kernel.write(msg)
        if self.terminalToggle == False:
            for num in range(len(self.appPrintQueue)):
                msg = self.appPrintQueue.pop(0)
                self.print(msg)
        return 
