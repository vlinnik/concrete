from pyplc.stl import *
from pyplc.utils.misc import TOF,TON

@stl(inputs=['auto','ison'],outputs=['out','power'],vars=['pt','manual'],persistent = ['pt'])
class Transport(STL):
    def __init__(self,auto:bool=False,ison:bool=False,pt:int=5):
        self.pt = pt
        self.auto = auto
        self.ison = ison
        self.manual = False
        self.power = False
        self.out = False
        self.__power = TOF(clk=lambda: self.auto, pt = pt*1000)
        self.__startup = TON(clk=lambda: self.ison, pt = 2000 )
    
    def __call__(self, pt: int = None ):
        with self:
            pt = self.overwrite('pt',pt)
            self.power = self.__power( pt = pt*1000) or self.manual
            self.out = self.__startup(  ) and self.auto
