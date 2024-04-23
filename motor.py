from pyplc.sfc import SFC,POU
from pyplc.utils.trig import TRIG

class Motor(SFC):
    """Управление двигателем, 2 или 1 сигнала для включения, обратная связь и звонок
    """
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

    def __init__(self,ison:bool=False, on:bool=False,off:bool = False,bell:bool=False,powered:bool=False, id:str=None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.ison = ison
        self.on = on
        self.off= off
        self.bell=bell
        self.error=Motor.E_NONE
        self.manual = False
        self.powered = powered
        self._remote = False
        
    def remote(self,on: bool):
        if self._remote==on:
            return
        if on:
            self.log('включение двигателя удаленной командой')
            self.exec(self.__powerOn)
        else:
            self.log('выключение двигателя удаленной командой')
            self.exec(self.__powerOff)
        self._remote = on

    def __ringBell(self):
        self.log('звонок перед пуском')
        for _ in self.pause(Motor.BELL):
            self.bell = True
            yield 
        self.bell = False
        self.log('сейчас жашнем')

    def __powerOn(self):
        self.log('запуск двигателя...')
        if Motor.BELL>0:
            for _ in self.__ringBell():
                if not self.manual and self._remote:
                    self.log(f'отмена запуска')
                    break
                yield
            yield from self.pause(1000)

        if self.manual or self._remote:        
            self.log('пуск двигателя')
            for _ in self.till( lambda: self.ison, min=500,max=1000 ):
                self.on = True
                self.powered = True
                if not self.manual and not self._remote:
                    break
                yield
            
            self.on = False

            if not self.ison:
                self.log('нет обратной связи')
                self.error = Motor.E_TIMEOUT
                self.powered = False
            else:
                self.log('двигатель включен')

    def __powerOff(self):
        self.log('останов двигателя')
        for _ in self.till( lambda: self.ison, min=500,max=1000 ):
            self.powered = False
            self.off = True
            yield
        self.off = False
        if self.ison:
            self.log('нет обратной связи')
            self.error = Motor.E_TIMEOUT
        else:
            self.log('смеситель выключен')
    
    def main(self):        
        t_manual = TRIG(clk=lambda: self.manual)
        while True:
            if t_manual():
                if self.manual: 
                    self.exec( self.__powerOn )
                else:
                    self.exec( self.__powerOff)
            yield
