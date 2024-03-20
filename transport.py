from pyplc.pou import POU
from pyplc.sfc import *
from pyplc.utils.misc import TOF,TON

# @stl(inputs=['ison','lock'],outputs=['out','power'],vars=['pt','manual','active'],persistent = ['pt'],hidden=['ison','out'])
class Transport(POU):    
    """Управление транспортными конвейерами"""
    ison = POU.input(False,hidden=True)
    lock = POU.input(False)
    out = POU.output(False,hidden=True)
    power = POU.output(False,hidden=True)
    pt = POU.var(5,persistent=True)
    manual = POU.var(False)
    active = POU.var(False)    
    @POU.init
    def __init__(self,auto:bool=False,ison:bool=False,pt:int=5,lock: bool = False):
        """Управление транспортным конвейером

        Args:
            auto (bool, optional): запрос на включение извне. Defaults to False.
            ison (bool, optional): состояние ВКЛЮЧЕНО. Defaults to False. Hidden
            pt (int, optional): задержка отключения в сек. Defaults to 5.
            active (bool): Включена логика работы. Иначе out повторяет auto
        
        Outputs:
            out (bool) : если включение удалось повторяет auto
            power (bool) : управление включением конвейера
        """        
        self.pt = pt
        self.__auto = False
        self.ison = ison
        self.manual = False
        self.power = False
        self.out = False
        self.active = True
        self.lock = lock
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
                self.power = (self.__power( pt = pt*1000) or self.manual) and not self.lock
                self.out = self.__startup(  ) and self.__auto
            else:
                self.power = self.manual
                self.out = self.__auto 

# @sfc(inputs=['remote','rot','lock'],outputs=['out'],vars=['manual','rotating','active','pt'],hidden=['rot'],persistent=['active','pt'])
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
    @POU.init
    def __init__(self,remote: bool=False, rot:bool = False, lock:bool = False, ms: int = 2000,pt: int = 0 ) -> None:
        super().__init__()
        self.rot = rot
        self.out = False
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

    @sfcaction
    def main(self):
        """Определение налиция вращения двигателя
        """
        while True:
            last = self.rot
            if self.ms>0:
                for x in self.pause(self.ms):
                    self.auto( self.delay( pt = self.pt*1000) )
                    yield x
                    if self.rot!=last:
                        self.rotating = True
                        break
                    last = self.rot
                if last==self.rot:
                    self.rotating = False
            else:
                self.auto( self.delay( pt = self.pt*1000) )
                self.rotating = self.rot
            yield True
            
