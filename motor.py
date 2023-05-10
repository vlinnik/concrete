from pyplc.sfc import *
from pyplc.utils.trig import TRIG

@sfc(inputs=['ison'],outputs=['on','off','bell','powered'],vars=['manual'])
class Motor(SFC):
    START = 1
    STOP = 2
    BELL = 1000
    E_NONE = 0
    E_TIMEOUT = -1

    def __init__(self,ison=None, on=None, off=None, bell=None) -> None:                
        """_summary_

        Args:
            ison (_type_, optional): _description_. Defaults to None.
            on (_type_, optional): _description_. Defaults to None.
            off (_type_, optional): _description_. Defaults to None.
            bell (_type_, optional): _description_. Defaults to None.
        """
        self.ison = ison
        self.on = False
        self.off= False
        self.bell=False
        self.error=Motor.E_NONE
        self.command = 0
        self.manual = False
        self.t_manual = TRIG(clk=lambda: self.manual)
        self.powered = False
        self.subtasks = [ self.t_manual ]

    def _ringBell(self):
        self.log('ring the bell')
        for x in self.pause(Motor.BELL):
            self.bell = True
            yield True
        self.bell = False

    def _powerPulse(self):
        self.log('power on pulse')
        for x in self.till( lambda: self.ison, min=500,max=1000 ):
            self.on = True
            self.powered = True
            if self.t_manual.q and not self.manual:
                break
            yield True
        
        self.on = False

        if not self.ison:
            self.log('power on failed')
            self.error = Motor.E_TIMEOUT
            self.powered = False
        else:
            self.log('succesfully powered on')
                        
    def _powerOn(self):
        self.log('power on...')
        if Motor.BELL>0:
            for x in self._ringBell():
                if not self.manual and self.t_manual.q :
                    self.log(f'user canceled power on procedure')
                    break
                yield x
                
        if self.manual:        
            for x in self._powerPulse():
                yield x

    def _powerOff(self):
        self.log('power off pulse')
        for x in self.till( lambda: self.ison, min=1,max=2 ):
            self.powered = False
            self.off = True
            yield True
        self.off = False
        if self.ison:
            self.log('power off timeout')
            self.error = Motor.E_TIMEOUT
        else:
            self.log('powered off')
            
    @sfcaction
    def main(self):
        if self.manual and self.t_manual.q :
            for x in self._powerOn():
                yield x
        elif not self.manual and self.t_manual.q:
            for x in self._powerOff():
                yield x
