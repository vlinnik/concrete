from pyplc.stl import *
from pyplc.utils.misc import TOF,TON

@stl(inputs=['ison'],outputs=['out','power'],vars=['pt','manual','active'],persistent = ['pt'],hidden=['ison','out'])
class Transport(STL):    
    """Управление транспортными конвейерами"""    
    def __init__(self,auto:bool=False,ison:bool=False,pt:int=5):
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
                self.power = self.__power( pt = pt*1000) or self.manual
                self.out = self.__startup(  ) and self.__auto
            else:
                self.out = self.__auto
