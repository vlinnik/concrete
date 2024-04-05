from pyplc.sfc import *
from pyplc.utils.trig import TRIG
# from pyplc.utils.misc import TOF

# @sfc(inputs=['ison'],outputs=['on','off','bell','powered'],vars=['manual'],hidden=['ison','bell'])
class Motor(SFC):
    START = 1
    STOP = 2
    BELL = 1000
    E_NONE = 0
    E_TIMEOUT = -1
    ison = POU.input(False,hidden=True)
    on = POU.output(False,hidden=True)
    off= POU.output(False,hidden=True)
    powered = POU.output(False)
    bell = POU.output(False,hidden=True)
    manual = POU.var( False )
    @POU.init
    def __init__(self,ison:bool=False, on:bool=False,off:bool = False,bell:bool=False) -> None:
        """_summary_

        Args:
            ison (_type_, optional): _description_. Defaults to None.
        """
        super().__init__( )
        self.ison = ison
        self.on = on
        self.off= off
        self.bell=bell
        self.error=Motor.E_NONE
        self.command = 0
        self.manual = False
        self.t_manual = TRIG(clk=lambda: self.manual)
        self.powered = False
        self._remote = False
        self.subtasks = [ self.t_manual ]
        
    def remote(self,on: bool):
        if self._remote==on:
            return
        if on:
            self.log('remote power on')
            self.exec(self.action(self._powerOn))
        else:
            self.log('remote power off')
            self.exec(self.action(self._powerOff))
        self._remote = on

    @sfcaction
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
                        
    @sfcaction
    def _powerOn(self):
        self.log('power on...')
        if Motor.BELL>0:
            for x in self.action(self._ringBell):
                if not self.manual and self.t_manual.q :
                    self.log(f'user canceled power on procedure')
                    break
                yield x
                
        if self.manual or self._remote:        
            for x in self._powerPulse():
                yield x

    @sfcaction
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
            self.log('power on, manual mode')
            yield from self.action(self._powerOn)
        elif not self.manual and self.t_manual.q:
            self.log('power off, manual mode')
            for x in self.action(self._powerOff).wait:
                yield x
