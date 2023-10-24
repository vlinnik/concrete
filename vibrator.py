from pyplc.stl import *
from pyplc.utils.misc import BLINK
from pyplc.utils.trig import TRIG
from concrete.weight import Weight
from concrete.container import Container
from concrete.dosator import Dosator

from pyplc.sfc import *

# @sfc(inputs=['auto'],outputs=['q'],persistent=['auto'])
class Vibrator(SFC):
    auto = POU.input(False,persistent=True)
    q = POU.output(False)
    @POU.init
    def __init__(self, auto: bool = False,containers: list[Container]=None, weight : Weight = None):
        super( ).__init__( )
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
        
        while clk and self.auto:
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
        
            
# @sfc(inputs=['auto'],outputs=['q'],persistent=['auto'])
class UnloadHelper(SFC):
    auto = POU.input(False,persistent=True)
    q = POU.output(False)
    @POU.init
    def __init__(self,auto=False,dosator: Dosator=None, weight : Weight = None, point: int = None):
        super( ).__init__( )
        self.dosator = dosator
        self.weight = weight
        self.auto = auto
        self.q = False
        self.point = point

    @sfcaction
    def main(self):
        if self.weight is None or self.dosator is None or not self.auto: return

        if not self.dosator.out: #если нет включения ничего не делаем
            return
        
        while self.auto and self.dosator.out:
            if self.point is not None:
                while self.weight.m>self.point and self.dosator.out:
                    yield True
                if self.dosator.out:
                    self.q = True
                    for i in self.pause(500):
                        yield i
                    self.q = False
                for i in self.till(lambda: self.dosator.out):
                    yield i
            else:
                before_m = self.weight.raw
                for i in self.pause(3000):
                    yield i
                after_m = self.weight.raw
                if abs(before_m-after_m)<500:
                    self.q = True
                    for i in self.pause(500):
                        yield i
                    self.q = False
