from pyplc.stl import *
from pyplc.utils.misc import BLINK
from pyplc.utils.trig import TRIG
from concrete.weight import Weight
from concrete.container import Container
from concrete.dosator import Dosator

from pyplc.sfc import *

@sfc(inputs=['auto'],outputs=['q'],persistent=['auto'])
class Vibrator(SFC):
    def __init__(self, auto: bool = False,containers: list[Container]=None, weight : Weight = None):
        self.containers = containers
        self.weight = weight
        self.auto = auto
        self.q = False

    @sfcaction
    def main(self):
        if self.weight is None or self.containers is None or not self.auto: return

        clk = False #определим включение есть/нет
        for c in self.containers:
            clk = clk or c.out

        if not clk: #если нет включения ничего не делаем
            return
        
        #self.q = True   #после открытия делаем короткое включение
        
        while clk:
            before_m = self.weight.raw
            self.q = True
            for i in self.pause(1000):
                yield i
            self.q = False
            for i in self.pause(2000):
                yield i
            after_m = self.weight.raw
            if abs(before_m-after_m)>500:
                break
            
            clk = False #определим включение есть/нет
            for c in self.containers:
                clk = clk or c.out
        
    
@stl(inputs=['auto'],outputs=['q'],persistent=['auto'])
class _Vibrator(STL):
    def __init__(self,auto=False,containers: list[Container]=None, weight : Weight = None):
        self.containers = containers
        self.weight = weight
        self.auto = auto
        self.q = False
        self.blink = BLINK( t_on = 1000,t_off = 2000 )
        self.trig = TRIG( clk = lambda:self.blink.q )
        
    def __call__(self):
        if self.weight is None or self.containers is None: return
        with self:
            clk = False
            for c in self.containers:
                clk = clk or (c.out and self.weight.still)
            
            self.blink( enable = clk )
            self.trig( )
            
            if self.auto:
                for c in self.containers:
                    if self.trig.q and c.out : self.q = True
                    
            if self.trig.q and not self.blink.q: self.q = False
            
@stl(inputs=['auto'],outputs=['q'],persistent=['auto'])
class UnloadHelper(STL):
    def __init__(self,auto=False,dosator: Dosator=None, weight : Weight = None):
        self.dosator = dosator
        self.weight = weight
        self.auto = auto
        self.q = False
        self.blink = BLINK( t_on = 1000,t_off = 2000 )
        self.trig = TRIG( clk = lambda:self.blink.q )
        
    def __call__(self):
        if self.weight is None or self.dosator is None: return
        with self:
            clk = (self.dosator.out and self.weight.still and self.dosator.m>self.dosator.ignore)
            
            self.blink( enable = clk )
            self.trig( )
            
            if self.auto:
                if self.trig.q and self.dosator.out : self.q = True
                    
            if self.trig.q and not self.blink.q: self.q = False