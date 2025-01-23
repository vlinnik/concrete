from pyplc.pou import POU
from pyplc.sfc import *
from pyplc.utils.misc import TOF,TON

class Transport(POU):    
    """Управление транспортными конвейерами"""
    ison = POU.input(False,hidden=True)
    lock = POU.input(False)
    hold_on = POU.input(False)
    out = POU.output(False,hidden=True)
    power = POU.output(False,hidden=True)
    pt = POU.var(5,persistent=True)
    manual = POU.var(False)
    active = POU.var(False)    
    def __init__(self,hold_on:bool=False,ison:bool=False,power:bool=False,out:bool=False,pt:int=5,lock: bool = False,id:str=None,parent:POU=None):
        """Управление транспортным конвейером

        Args:
            hold_on (bool, optional): Если включили то не выключать пока True. Defaults to False.
            ison (bool, optional): состояние ВКЛЮЧЕНО. Defaults to False. Hidden
            pt (int, optional): задержка отключения в сек. Defaults to 5.
            active (bool): Включена логика работы. Иначе out повторяет auto
        
        Outputs:
            out (bool) : если включение удалось повторяет auto
            power (bool) : управление включением конвейера
        """        
        super().__init__(id,parent)
        self.pt = pt
        self.__auto = False
        self.ison = ison
        self.manual = False
        self.power = power
        self.out = out
        self.active = True
        self.lock = lock
        self.hold_on = hold_on
        self.__power = TOF(clk=lambda: self.__auto, pt = pt*1000)
        self.__startup = TON(clk=lambda: self.ison, pt = 2000 )

    @property
    def auto(self): return self.__auto
        
    @auto.setter 
    def auto(self,on: bool):
        self.__auto = on
        
    def set_auto(self,on):
        self.auto = on
    
    def __call__(self, pt: int = None ):
        with self:
            pt = self.overwrite('pt',pt)
            if self.active:
                if self.power and self.hold_on:
                    pass
                else:
                    self.power = (self.__power( pt = pt*1000) or self.manual) and not self.lock
                self.out = self.__startup(  ) and self.__auto
            else:
                self.power = self.manual
                self.out = self.__auto 

class Gear(SFC):
    """Управление ИМ с датчиком вращения (нория, конвейер)

    Поддерживает включение по месту и в автоматическом режиме дистанционно, в автоматическом режиме
    включение ограничено сигналом lock (блокировка)
    """
    remote = POU.input(False,hidden=True)
    rot = POU.input(False,hidden=True)
    lock = POU.input(False)
    out = POU.output(False)
    manual = POU.var(False)
    rotating = POU.var(False)
    active = POU.var(False,persistent=True)
    pt = POU.var(1000,persistent=True)
    def __init__(self,remote: bool=False, rot:bool = False, lock:bool = False, out:bool=False, ms: int = 2000,pt: int = 0, id:str=None, parent:POU=None ) -> None:
        super().__init__(id, parent)
        self.rot = rot
        self.out = out
        self.manual = False
        self.rotating = False
        self.active = False
        self.remote = remote
        self.lock = lock
        self.delay = TOF(clk = lambda: self.remote)
        self.ms = ms
        self.pt = pt

    def auto(self,on:bool = None):
        if on is None:
            return
        
        if self.active:
            self.out = (on or self.manual) and not self.lock
        else:
            self.out = self.manual

    def main(self):
        """Определение наличия вращения двигателя
        """
        while True:
            last = self.rot
            for x in self.pause(self.ms):
                self.auto( self.delay( pt = self.pt*1000) )
                yield x
                if self.rot!=last:
                    self.rotating = True
                    break
                last = self.rot
            if last==self.rot and self.ms>0:
                self.rotating = False
            elif self.ms<=0:
                self.auto( self.delay( pt = self.pt*1000) )
                self.rotating = self.rot
            yield
