from pyplc.sfc import SFC,POU
from pyplc.utils.trig import TRIG
from pyplc.utils.misc import TON
from pyplc.ld import LD

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

class MotorST(SFC):
    """Управление двигателем звезда-треугольник обратная связь и звонок
    """
    START = 1
    STOP = 2
    BELL = 1000
    E_NONE = 0
    E_TIMEOUT = -1
    ison = POU.input(False,hidden=True)
    emergency = POU.input(False,hidden=True)
    star = POU.output(False,hidden=True)
    tria = POU.output(False,hidden=True)
    powered = POU.output(False)
    bell = POU.output(False,hidden=True)
    manual = POU.var( False )

    def __init__(self,ison:bool=False, star:bool=False,tria:bool = False,bell:bool=False,powered:bool=False, emergency: bool=False, heat: int = 3000, id:str=None,parent:POU=None) -> None:
        super().__init__( id,parent )
        self.emergency = emergency
        self.ison = ison
        self.star = star
        self.tria= tria
        self.bell=bell
        self.error=MotorST.E_NONE
        self.manual = False
        self.powered = powered
        self._remote = False
        self.heat = heat    #переход звезда - треугольник в мсек
        self.subtasks = (TON(clk=lambda: self.tria and self.powered and not self.ison,q = self._emergency), LD.no(emergency).out(self._emergency).end() )
    def _emergency(self,on: bool):
        if on==True:
            self.powered = False
            self.star = False
            self.tria = False
                    
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

        if (self.manual or self._remote) and not self.emergency:        
            self.log(f'пуск двигателя звезда {self.heat} мсек')
            self.star = True
            self.powered = True
            for _ in self.pause(self.heat):
                if not self.manual and not self._remote:
                    break
                yield
            
            self.log('пуск двигателя треугольник')    
            self.star = False
            self.tria = True
            yield from self.till( lambda: self.ison, min=500,max=1000 )
            
            if not self.ison:
                self.log('нет обратной связи')
                self.error = MotorST.E_TIMEOUT
                self.powered = False
            else:
                self.log('двигатель включен')

    def __powerOff(self):
        self.log('останов двигателя')
        for _ in self.till( lambda: self.ison, min=500,max=1000 ):
            self.powered = False
            self.star = False
            self.tria = False
            yield

        if self.ison:
            self.log('нет обратной связи')
            self.error = MotorST.E_TIMEOUT
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
